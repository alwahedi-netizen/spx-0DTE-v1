"""
alloc_lab.py — Logicon Capital · Allocations Lab: Phase-2 paper allocations
===========================================================================
Owner go-ahead 2026-10-28 ("Hedgefundie should roll, we need to test"), after
the research scan's allocation track passed it (RESEARCH.md §4b): 1986-2026 on
simulated 3x funds it beat the S&P 500 in 74% of rolling 20-year windows and
69.7% of 10-year windows; worst year 2022 (-64% vs -18%).

THE RULES BELOW ARE FROZEN (Shine discipline). New allocations are new lanes.
  Lane HFEA  — 55% UPRO (3x S&P 500) / 45% TMF (3x 20+yr Treasuries),
               rebalanced back to 55/45 on the first run of each calendar quarter
  Lane SPY   — 100% SPY, the yardstick (same $, same costs, never rebalanced)

$10,000 per lane · marks and fills at the day's close (Yahoo adjusted closes,
so distributions are counted) · 5bp on traded notional · daily pass 16:30 ET
weekdays (labs_runner) · paper only, nothing routes to a broker.

What paper is for here: an allocation's edge can't be proven in months. Paper
verifies the backtest's MODEL — that real UPRO/TMF track the simulated 3x funds
(daily 3x minus financing and fees) — and gives the owner a live feel for the
swings before any real money. Phase-3 review: after 6 months, if HFEA's real
return is within 3%/yr of the model's for the same dates, it is eligible for a
small live allocation — owner's decision and size. There is no stop-loss: a
-60% year is inside the tested envelope (2022), and selling it would be a
different strategy.
"""

import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "data" / "labs" / "labs.sqlite"
ET = ZoneInfo("America/New_York")

LANES = {"HFEA": {"UPRO": 0.55, "TMF": 0.45}, "SPY": {"SPY": 1.0}}
REBALANCE = {"HFEA": True, "SPY": False}
START_NAV = 10_000.0
COST = 0.0005                      # 5bp of traded notional
UNIVERSE = sorted({s for w in LANES.values() for s in w})

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


def _quarter(day):
    return f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"


def _trade_to(c, lane, day, nav, cash, px, note):
    """Move a lane to its target weights at today's close; returns new cash."""
    held = {r["sym"]: r["qty"] for r in c.execute(
        "SELECT sym, qty FROM alloclab_pos WHERE lane=?", (lane,))}
    target = {s: nav * w / px[s] for s, w in LANES[lane].items()}
    for s in sorted(set(held) | set(target)):
        dq = target.get(s, 0.0) - held.get(s, 0.0)
        if abs(dq * px[s]) < 0.01:
            continue
        fee = abs(dq) * px[s] * COST
        cash -= dq * px[s] + fee
        c.execute("INSERT INTO alloclab_orders (day,lane,sym,qty,px,cost,note) "
                  "VALUES (?,?,?,?,?,?,?)", (day, lane, s, round(dq, 6), px[s], round(fee, 2), note))
        c.execute("INSERT OR REPLACE INTO alloclab_pos VALUES (?,?,?,?)",
                  (lane, s, target.get(s, 0.0), px[s]))
    return cash


def daily():
    """One pass per weekday after the close: start (first run), quarterly
    rebalance, mark-to-market. Idempotent per ET date."""
    now = _now()
    day = now.strftime("%Y-%m-%d")
    if now.weekday() >= 5:
        return {"ok": True, "msg": "weekend — no pass"}
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM alloclab_state")}
    if st and all((s.get("last_run") or "") >= day for s in st.values()):
        return {"ok": True, "msg": f"already ran for {day}"}
    px, fails = {}, []
    for s in UNIVERSE:
        try:
            px[s] = _chart(s)[-1]
        except Exception:
            fails.append(s)
    if fails:
        return {"ok": False, "msg": f"no price for {', '.join(fails)} — retry next window"}
    out = {}
    stamp = now.isoformat(timespec="seconds")
    with _db() as c:
        for lane in LANES:
            s = st.get(lane)
            if s is None:                  # owner go 2026-10-28: first pass starts the lane
                c.execute("INSERT INTO alloclab_state VALUES (?,?,?,NULL,NULL)",
                          (lane, START_NAV, stamp))
                s = {"cash": START_NAV, "last_rebal": None}
            cash = s["cash"]
            pos = {r["sym"]: r["qty"] for r in c.execute(
                "SELECT sym, qty FROM alloclab_pos WHERE lane=?", (lane,))}
            nav = cash + sum(q * px[sym] for sym, q in pos.items())
            q = _quarter(day)
            rebal = s["last_rebal"] is None or (REBALANCE[lane] and s["last_rebal"] != q)
            if rebal:
                cash = _trade_to(c, lane, day, nav, cash, px,
                                 "start" if s["last_rebal"] is None else f"rebalance {q}")
                c.execute("UPDATE alloclab_state SET last_rebal=? WHERE lane=?", (q, lane))
            for sym in pos:
                c.execute("UPDATE alloclab_pos SET last_px=? WHERE lane=? AND sym=?",
                          (px[sym], lane, sym))
            nav = cash + sum(r["qty"] * px[r["sym"]] for r in c.execute(
                "SELECT sym, qty FROM alloclab_pos WHERE lane=?", (lane,)))
            c.execute("UPDATE alloclab_state SET cash=?, last_run=? WHERE lane=?",
                      (round(cash, 4), day, lane))
            c.execute("INSERT OR REPLACE INTO alloclab_nav VALUES (?,?,?)",
                      (day, lane, round(nav, 2)))
            out[lane] = {"nav": round(nav, 2), "rebalanced": rebal}
    return {"ok": True, "day": day, "lanes": out, "px": px}


def status():
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM alloclab_state")}
        pos = [dict(r) for r in c.execute("SELECT * FROM alloclab_pos ORDER BY lane, sym")]
        orders = [dict(r) for r in c.execute(
            "SELECT * FROM alloclab_orders ORDER BY id DESC LIMIT 60")]
        hist = [dict(r) for r in c.execute("SELECT * FROM alloclab_nav ORDER BY day")]
    lanes = {}
    for lane, w in LANES.items():
        s = st.get(lane)
        if not s:
            lanes[lane] = {"nav": None, "ret_pct": None, "target": w}
            continue
        nav = s["cash"] + sum(p["qty"] * (p["last_px"] or 0) for p in pos if p["lane"] == lane)
        weights = {p["sym"]: round(p["qty"] * (p["last_px"] or 0) / nav, 4)
                   for p in pos if p["lane"] == lane and nav}
        lanes[lane] = {"nav": round(nav, 2), "ret_pct": round(nav / START_NAV * 100 - 100, 2),
                       "cash": round(s["cash"], 2), "started": s["started"],
                       "last_run": s["last_run"], "last_rebal": s["last_rebal"],
                       "target": w, "weights": weights}
    return {"ok": True, "started": bool(st), "lanes": lanes, "positions": pos,
            "orders": orders, "nav_history": hist, "start_nav": START_NAV}
