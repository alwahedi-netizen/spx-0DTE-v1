"""
alloc_lab.py — Logicon Capital · Allocations Lab: Phase-2 paper allocations
===========================================================================
Owner go-ahead 2026-10-28 ("Hedgefundie should roll, we need to test"), after
the research scan's allocation track passed it (RESEARCH.md §4b): 1986-2026 on
simulated 3x funds it beat the S&P 500 in 74% of rolling 20-year windows and
69.7% of 10-year windows; worst year 2022 (-64% vs -18%).

THE RULES BELOW ARE FROZEN (Shine discipline). New allocations are new lanes.
  Lane HFEA    — 55% UPRO (3x S&P 500) / 45% TMF (3x 20+yr Treasuries),
                 rebalanced back to 55/45 on the first pass of each quarter
  Lane SPY     — 100% SPY, the yardstick (same $, same costs, never rebalanced)
Added 2026-10-28 (owner "go", after the re-check of earlier lanes — both are
POST-HOC picks from 10 variants, which is exactly why they are on paper):
  Lane VMSPX15 — vol-managed S&P at 1.5x (Moreira & Muir 2017): on the first
                 pass of each month, SPY weight = 1.5 x min(1, 15% / 21-day
                 realized vol). Backtest 1986+: +12.9%/yr vs +10.9%, beat the
                 S&P in 80% of 10-yr and 100% of 20-yr windows, worst year -32%
  Lane RP2X    — risk parity at 2x: on the first pass of each month, weights
                 on SPY / TLT / GLD proportional to 1 / 63-day realized vol,
                 summing to 2.0. Backtest 2001+: +14.3%/yr vs +9.4%, Sharpe
                 0.78 vs 0.47, worst year -33%; FAILED the 10-yr check (lost
                 the latest decade) — on paper as the owner's choice
  Both new lanes keep a cash balance: positive cash earns the T-bill rate,
  borrowed cash (leverage) pays T-bill + 1%/yr — the backtest's terms.

$10,000 per lane · marks and fills at the day's close (Yahoo adjusted closes,
so distributions are counted) · 5bp on traded notional · daily pass 16:30 ET
weekdays (labs_runner) · paper only, nothing routes to a broker.

What paper is for here: an allocation's edge can't be proven in months. Paper
verifies the backtest's MODEL (real UPRO/TMF track the simulated 3x funds; the
monthly rules trade as designed) and gives the owner a live feel for the
swings before any real money. Phase-3 review: after 6 months, if a lane's real
return is within 3%/yr of its model for the same dates, it is eligible for a
small live allocation — owner's decision and size. There is no stop-loss: the
worst tested years are inside each lane's envelope.
"""

import json
import math
import sqlite3
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "data" / "labs" / "labs.sqlite"
ET = ZoneInfo("America/New_York")

STATIC = {"HFEA": {"UPRO": 0.55, "TMF": 0.45}, "SPY": {"SPY": 1.0}}
DYNAMIC = {"VMSPX15": ("SPY",), "RP2X": ("SPY", "TLT", "GLD")}
LANES = list(STATIC) + list(DYNAMIC)
REBALANCE = {"HFEA": "quarter", "SPY": None, "VMSPX15": "month", "RP2X": "month"}
FINANCED = {"VMSPX15", "RP2X"}          # cash earns T-bills / borrowing pays T-bills + 1%
VM_LEVER, VM_TARGET_VOL, VM_WIN = 1.5, 0.15, 21
RP_GROSS, RP_WIN = 2.0, 63
BORROW_SPREAD = 0.01
START_NAV = 10_000.0
COST = 0.0005                            # 5bp of traded notional
UNIVERSE = sorted({s for w in STATIC.values() for s in w} | {s for v in DYNAMIC.values() for s in v})

SCHEMA = """
CREATE TABLE IF NOT EXISTS alloclab_state (lane TEXT PRIMARY KEY, cash REAL,
  started TEXT, last_run TEXT, last_rebal TEXT);
CREATE TABLE IF NOT EXISTS alloclab_pos (lane TEXT, sym TEXT, qty REAL,
  last_px REAL, PRIMARY KEY (lane, sym));
CREATE TABLE IF NOT EXISTS alloclab_orders (id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT, lane TEXT, sym TEXT, qty REAL, px REAL, cost REAL, note TEXT);
CREATE TABLE IF NOT EXISTS alloclab_nav (day TEXT, lane TEXT, nav REAL,
  PRIMARY KEY (day, lane));
"""


def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:                                  # dynamic lanes record their latest targets
        c.execute("ALTER TABLE alloclab_state ADD COLUMN target TEXT")
    except sqlite3.OperationalError:
        pass
    return c


def _chart(sym, rng="5d"):
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())["chart"]["result"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") \
        or res["indicators"]["quote"][0]["close"]
    return [c for c in adj if c]


def _now():
    return datetime.now(timezone.utc).astimezone(ET)


def _period(day, kind):
    if kind == "quarter":
        return f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"
    return day[:7]                        # month


def _vol(closes):
    r = [math.log(closes[k] / closes[k - 1]) for k in range(1, len(closes))]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / len(r) * 252)


def target_weights(lane, hist):
    """Frozen target weights. `hist[sym]` = adjusted closes, oldest -> newest,
    ending at today's close."""
    if lane in STATIC:
        return dict(STATIC[lane])
    if lane == "VMSPX15":
        v = _vol(hist["SPY"][-(VM_WIN + 1):])
        return {"SPY": VM_LEVER * min(1.0, VM_TARGET_VOL / max(v, 1e-9))}
    if lane == "RP2X":
        iv = {s: 1 / max(_vol(hist[s][-(RP_WIN + 1):]), 1e-9) for s in DYNAMIC["RP2X"]}
        tot = sum(iv.values())
        return {s: RP_GROSS * x / tot for s, x in iv.items()}
    raise KeyError(lane)


def _trade_to(c, lane, day, nav, cash, px, target, note):
    """Move a lane to `target` weights of NAV at today's close; returns new cash."""
    held = {r["sym"]: r["qty"] for r in c.execute(
        "SELECT sym, qty FROM alloclab_pos WHERE lane=?", (lane,))}
    want = {s: nav * w / px[s] for s, w in target.items()}
    for s in sorted(set(held) | set(want)):
        dq = want.get(s, 0.0) - held.get(s, 0.0)
        if abs(dq * px[s]) < 0.01:
            continue
        fee = abs(dq) * px[s] * COST
        cash -= dq * px[s] + fee
        c.execute("INSERT INTO alloclab_orders (day,lane,sym,qty,px,cost,note) "
                  "VALUES (?,?,?,?,?,?,?)", (day, lane, s, round(dq, 6), px[s], round(fee, 2), note))
        c.execute("INSERT OR REPLACE INTO alloclab_pos (lane,sym,qty,last_px) VALUES (?,?,?,?)",
                  (lane, s, want.get(s, 0.0), px[s]))
    return cash


def _accrue(cash, last_run, day, rf_annual):
    """Interest on a financed lane's cash since its last pass (calendar days)."""
    if not last_run or cash == 0:
        return cash
    days = (date.fromisoformat(day) - date.fromisoformat(last_run)).days
    rate = rf_annual if cash > 0 else rf_annual + BORROW_SPREAD
    return cash * (1 + rate) ** (days / 365)


def daily():
    """One pass per weekday after the close: start lanes not yet started,
    accrue cash interest, rebalance on schedule, mark to market. Idempotent
    per ET date (and per lane: a lane that already ran today is skipped)."""
    now = _now()
    day = now.strftime("%Y-%m-%d")
    if now.weekday() >= 5:
        return {"ok": True, "msg": "weekend — no pass"}
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM alloclab_state")}
    todo = [l for l in LANES if (st.get(l, {}).get("last_run") or "") < day]
    if not todo:
        return {"ok": True, "msg": f"already ran for {day}"}
    hist, fails = {}, []
    for s in UNIVERSE:
        try:
            hist[s] = _chart(s, rng="6mo")
        except Exception:
            fails.append(s)
    rf = None
    try:
        rf = _chart("^IRX")[-1] / 100
    except Exception:
        if FINANCED & set(todo):          # only the financed lanes need the T-bill rate
            fails.append("^IRX")
    if fails or any(len(hist[s]) < RP_WIN + 1 for s in UNIVERSE):
        return {"ok": False, "msg": f"no prices for {', '.join(fails) or 'enough history'} — retry next window"}
    px = {s: h[-1] for s, h in hist.items()}
    out = {}
    with _db() as c:
        for lane in todo:
            s = st.get(lane)
            if s is None:                  # owner go 2026-10-28: first pass starts the lane
                c.execute("INSERT INTO alloclab_state (lane,cash,started,last_run,last_rebal) "
                          "VALUES (?,?,?,NULL,NULL)", (lane, START_NAV, now.isoformat(timespec="seconds")))
                s = {"cash": START_NAV, "last_rebal": None, "last_run": None}
            cash = s["cash"]
            if lane in FINANCED:
                cash = _accrue(cash, s["last_run"], day, rf)
            pos = {r["sym"]: r["qty"] for r in c.execute(
                "SELECT sym, qty FROM alloclab_pos WHERE lane=?", (lane,))}
            nav = cash + sum(q * px[sym] for sym, q in pos.items())
            kind = REBALANCE[lane]
            rebal = s["last_rebal"] is None or (kind and s["last_rebal"] != _period(day, kind))
            if rebal:
                tgt = target_weights(lane, hist)
                cash = _trade_to(c, lane, day, nav, cash, px, tgt,
                                 "start" if s["last_rebal"] is None else f"rebalance {_period(day, kind)}")
                c.execute("UPDATE alloclab_state SET last_rebal=?, target=? WHERE lane=?",
                          (_period(day, kind or "month"), json.dumps({k: round(v, 4) for k, v in tgt.items()}), lane))
            for sym in pos:
                c.execute("UPDATE alloclab_pos SET last_px=? WHERE lane=? AND sym=?",
                          (px[sym], lane, sym))
            nav = cash + sum(r["qty"] * px[r["sym"]] for r in c.execute(
                "SELECT sym, qty FROM alloclab_pos WHERE lane=?", (lane,)))
            c.execute("UPDATE alloclab_state SET cash=?, last_run=? WHERE lane=?",
                      (round(cash, 4), day, lane))
            c.execute("INSERT OR REPLACE INTO alloclab_nav VALUES (?,?,?)",
                      (day, lane, round(nav, 2)))
            out[lane] = {"nav": round(nav, 2), "rebalanced": bool(rebal)}
    return {"ok": True, "day": day, "lanes": out, "px": px, "rf": rf}


def status():
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM alloclab_state")}
        pos = [dict(r) for r in c.execute("SELECT * FROM alloclab_pos ORDER BY lane, sym")]
        orders = [dict(r) for r in c.execute(
            "SELECT * FROM alloclab_orders ORDER BY id DESC LIMIT 80")]
        hist = [dict(r) for r in c.execute("SELECT * FROM alloclab_nav ORDER BY day")]
    lanes = {}
    for lane in LANES:
        s = st.get(lane)
        static_t = STATIC.get(lane)
        if not s:
            lanes[lane] = {"nav": None, "ret_pct": None, "target": static_t or {}}
            continue
        nav = s["cash"] + sum(p["qty"] * (p["last_px"] or 0) for p in pos if p["lane"] == lane)
        weights = {p["sym"]: round(p["qty"] * (p["last_px"] or 0) / nav, 4)
                   for p in pos if p["lane"] == lane and nav}
        tgt = static_t or json.loads(s.get("target") or "{}")
        lanes[lane] = {"nav": round(nav, 2), "ret_pct": round(nav / START_NAV * 100 - 100, 2),
                       "cash": round(s["cash"], 2), "started": s["started"],
                       "last_run": s["last_run"], "last_rebal": s["last_rebal"],
                       "target": tgt, "weights": weights}
    return {"ok": True, "started": bool(st), "lanes": lanes, "positions": pos,
            "orders": orders, "nav_history": hist, "start_nav": START_NAV}
