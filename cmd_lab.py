"""
cmd_lab.py — Logicon Capital · Commodities Lab: paper test of the star system
==============================================================================
Owner go-ahead 2026-10-05, after the backtests: the equity star system ported
to commodities kept its edge on DAILY bars, long side (futures +4.6%/trade vs
+1.0% random, t=+2.0; ETFs +2.0%, t=+1.2; hourly = zero; FX = negative).
This lab forward-tests exactly that finding on paper.

THE RULES BELOW ARE FROZEN (Shine discipline). Star lanes differ ONLY in exit:
  Lane H21 — exit 21 trading days after entry (the t=+2.0 backtest config)
  Lane H63 — exit 63 trading days after entry (higher mean, fatter tail)
  Lane TR30 (added 2026-10-06, owner strategy, its own entry rule) — buy when
  the close is within 1% of the 30-bar high, exit when the close drops 15%
  below the peak close since entry (trailing). No time limit.

Universe (Schwab-tradeable commodity ETFs — honest prices incl. roll drag):
  GLD SLV PPLT PALL CPER USO BNO UNG DBA DBB DBC GSG PDBC CORN WEAT SOYB CANE

Signal (daily closes, evaluated once per day after the close):
  the vol-scaled 5-star condition — 21-pt score (returns over 21/63/126/252/
  756/1260 bars vs thresholds scaled to each ETF's trailing 252-day vol,
  calibrated from the equity system's 35%-vol assumptions), grade A
  (within its vol-scaled 2%-equivalent of the 63-bar high, 3-bar return > 0,
  21-bar return above the A bar), and double-high stars (within the 1%-
  equivalents of BOTH the 63- and 126-bar highs, 1M > 0, 3D > 0). LONG ONLY.

Portfolio: $10,000 per lane · position = NAV/4 at entry (max 4 concurrent) ·
one open position per ETF per lane · entries at the signal day's close ·
6bp round-trip cost per trade · marks from Yahoo. Scheduled daily 17:15 ET
weekdays (labs_runner, in the Paper Lab). Nothing routes to a broker — paper only.
Verdict at 12 months: a lane survives if net > 0 AND profit factor > 1.3.
"""

import json
import math
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Moved to the Paper Lab 2026-10-15 (from combo-trader-tv @ 315faef): rules
# verbatim; only the journal moved — out of the trader's logicon_journal
# into the lab's own DB, imported once by `labs_runner.py import`.
DB = BASE_DIR / "data" / "labs" / "labs.sqlite"

ETFS = ["GLD", "SLV", "PPLT", "PALL", "CPER", "USO", "BNO", "UNG", "DBA",
        "DBB", "DBC", "GSG", "PDBC", "CORN", "WEAT", "SOYB", "CANE"]
LANES = {"H21": 21, "H63": 63}
# TR30 (owner lane, 2026-10-06, FROZEN): buy within 1% of the 30-bar high,
# exit 15% below the peak since entry — classic breakout trend-following.
# Backtest: profitable per-trade in every trending class (cmd ETFs +4.5%/tr,
# PF 1.68); the forward test judges it against the star lanes.
TR_LANE = "TR30"
TR_W, TR_BAND, TR_STOP = 30, 0.99, 0.85
ALL_LANES = list(LANES) + [TR_LANE]
START_NAV = 10_000.0
POS_FRAC = 0.25
COST_RT = 0.0006

WIN = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252, "3Y": 756, "5Y": 1260}
PTS = {"1M": 1, "3M": 2, "6M": 3, "1Y": 4, "3Y": 5, "5Y": 6}
THR = {"1M": .03, "3M": .10, "6M": .20, "1Y": .40, "3Y": 1.20, "5Y": 2.50}
EQV = 0.35
K = {p: THR[p] / (EQV * math.sqrt(WIN[p] / 252)) for p in WIN}
K_A1M = .10 / (EQV * math.sqrt(21 / 252))
K_D90A = .02 / (EQV * math.sqrt(63 / 252))
K_D90S = .01 / (EQV * math.sqrt(63 / 252))
K_D180S = .01 / (EQV * math.sqrt(126 / 252))
MIN_SCORE = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS cmdlab_state (lane TEXT PRIMARY KEY, cash REAL,
  started TEXT, last_run TEXT);
CREATE TABLE IF NOT EXISTS cmdlab_pos (lane TEXT, sym TEXT, qty REAL,
  entry_px REAL, entry_day TEXT, exit_after INTEGER, bars_held INTEGER,
  PRIMARY KEY (lane, sym));
CREATE TABLE IF NOT EXISTS cmdlab_trades (id INTEGER PRIMARY KEY AUTOINCREMENT,
  lane TEXT, sym TEXT, entry_day TEXT, entry_px REAL, exit_day TEXT,
  exit_px REAL, qty REAL, pnl REAL, pnl_pct REAL, note TEXT);
CREATE TABLE IF NOT EXISTS cmdlab_nav (day TEXT, lane TEXT, nav REAL,
  PRIMARY KEY (day, lane));
"""


def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:                      # TR30 migration: peak tracking for the trail
        c.execute("ALTER TABLE cmdlab_pos ADD COLUMN peak_px REAL")
    except sqlite3.OperationalError:
        pass
    return c


def _chart(sym, rng="6y"):
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    res = d["chart"]["result"][0]
    return [c for c in res["indicators"]["quote"][0]["close"] if c]


def _vol252(c):
    s = c[-253:]
    if len(s) < 60:
        return None
    lr = [math.log(s[i] / s[i - 1]) for i in range(1, len(s))]
    m = sum(lr) / len(lr)
    return math.sqrt(sum((x - m) ** 2 for x in lr) / len(lr)) * math.sqrt(252)


def star_signal(c):
    """The FROZEN vol-scaled 5-star long condition on daily closes
    (oldest→newest). Mirrors the backtest implementation exactly."""
    i = len(c) - 1
    if i < WIN["5Y"]:
        return False
    v = _vol252(c)
    if not v:
        return False
    thr = {p: K[p] * v * math.sqrt(WIN[p] / 252) for p in WIN}
    score = 0
    for p in WIN:
        past = c[i - WIN[p]]
        if past > 0 and c[i] / past - 1 > thr[p]:
            score += PTS[p]
    if score < MIN_SCORE:
        return False
    f = lambda k, w: -k * v * math.sqrt(w / 252)
    hi90 = max(c[i - 62:i + 1]); hi180 = max(c[i - 125:i + 1])
    d90 = c[i] / hi90 - 1; d180 = c[i] / hi180 - 1
    r3d = c[i] / c[i - 3] - 1; r1m = c[i] / c[i - 21] - 1
    if not (d90 > f(K_D90A, 63) and r3d > 0 and r1m > K_A1M * v * math.sqrt(21 / 252)):
        return False
    return (d90 > f(K_D90S, 63) and d180 > f(K_D180S, 126)
            and r1m > 0 and r3d > 0)


def trail_signal(c):
    """TR30 entry: within 1% of the 30-bar high, FRESH (false yesterday)."""
    if len(c) < TR_W + 2:
        return False
    cond = c[-1] >= max(c[-TR_W:]) * TR_BAND
    prev = c[-2] >= max(c[-TR_W - 1:-1]) * TR_BAND
    return cond and not prev


def start():
    with _db() as c:
        if c.execute("SELECT COUNT(*) FROM cmdlab_state").fetchone()[0]:
            return {"ok": False, "msg": "lab already started"}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for lane in ALL_LANES:
            c.execute("INSERT INTO cmdlab_state VALUES (?,?,?,NULL)",
                      (lane, START_NAV, now))
    return daily()


def daily():
    """One pass per trading day (17:15 ET): age/exit positions, scan for new
    5-star signals, enter while cash allows, snapshot NAV. Idempotent per day."""
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM cmdlab_state")}
        if st and TR_LANE not in st:
            # TR30 joined after the lab may have started — its own clock
            # begins now; the older lanes' history is untouched
            nw = datetime.now(timezone.utc).isoformat(timespec="seconds")
            c.execute("INSERT INTO cmdlab_state VALUES (?,?,?,NULL)",
                      (TR_LANE, START_NAV, nw))
            st[TR_LANE] = {"lane": TR_LANE, "cash": START_NAV,
                           "started": nw, "last_run": None}
    if not st:
        return {"ok": False, "msg": "lab not started"}
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if all((s.get("last_run") or "") >= day for s in st.values()):
        return {"ok": True, "msg": f"already ran for {day}"}

    series, fails = {}, []
    for sym in ETFS:
        try:
            series[sym] = _chart(sym)
        except Exception:
            fails.append(sym)
    px = {s: v[-1] for s, v in series.items() if v}
    sigs = [s for s, v in series.items() if star_signal(v)]
    tr_sigs = [s for s, v in series.items() if trail_signal(v)]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = {}
    with _db() as c:
        for lane in ALL_LANES:
            is_tr = lane == TR_LANE
            lane_sigs = tr_sigs if is_tr else sigs
            cash = st[lane]["cash"]
            pos = [dict(r) for r in c.execute(
                "SELECT * FROM cmdlab_pos WHERE lane=?", (lane,))]
            closed = opened = 0
            held_syms = set()
            for p in pos:
                sym = p["sym"]
                held_syms.add(sym)
                if sym not in px:        # no mark today — age it tomorrow
                    continue
                bars = p["bars_held"] + 1
                if is_tr:
                    peak = max(p.get("peak_px") or p["entry_px"], px[sym])
                    hit = px[sym] < peak * TR_STOP
                    note = f"trail exit · peak {peak:.2f} · held {bars} bars"
                else:
                    hit = bars >= p["exit_after"]
                    note = f"held {bars} bars"
                if hit:
                    proceeds = p["qty"] * px[sym] * (1 - COST_RT / 2)
                    pnl = proceeds - p["qty"] * p["entry_px"]
                    cash += proceeds
                    c.execute("INSERT INTO cmdlab_trades (lane,sym,entry_day,"
                              "entry_px,exit_day,exit_px,qty,pnl,pnl_pct,note)"
                              " VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (lane, sym, p["entry_day"], p["entry_px"], day,
                               px[sym], p["qty"], round(pnl, 2),
                               round((px[sym] / p["entry_px"] - 1) * 100, 2),
                               note))
                    c.execute("DELETE FROM cmdlab_pos WHERE lane=? AND sym=?",
                              (lane, sym))
                    held_syms.discard(sym)
                    closed += 1
                elif is_tr:
                    c.execute("UPDATE cmdlab_pos SET bars_held=?, peak_px=? "
                              "WHERE lane=? AND sym=?", (bars, peak, lane, sym))
                else:
                    c.execute("UPDATE cmdlab_pos SET bars_held=? "
                              "WHERE lane=? AND sym=?", (bars, lane, sym))
            # entries: fresh signals, one per ETF, while cash covers a slot
            nav_now = cash + sum(p2["qty"] * px.get(p2["sym"], p2["entry_px"])
                                 for p2 in [dict(r) for r in c.execute(
                                     "SELECT * FROM cmdlab_pos WHERE lane=?", (lane,))])
            slot = nav_now * POS_FRAC
            for sym in lane_sigs:
                if sym in held_syms or sym not in px:
                    continue
                if cash < slot * 0.98:
                    c.execute("INSERT INTO cmdlab_trades (lane,sym,entry_day,"
                              "entry_px,exit_day,exit_px,qty,pnl,pnl_pct,note)"
                              " VALUES (?,?,?,?,NULL,NULL,0,NULL,NULL,?)",
                              (lane, sym, day, px[sym],
                               "SKIPPED — fully invested"))
                    continue
                qty = slot * (1 - COST_RT / 2) / px[sym]
                cash -= slot
                c.execute("INSERT INTO cmdlab_pos (lane,sym,qty,entry_px,"
                          "entry_day,exit_after,bars_held,peak_px)"
                          " VALUES (?,?,?,?,?,?,0,?)",
                          (lane, sym, round(qty, 4), px[sym], day,
                           None if is_tr else LANES[lane],
                           px[sym] if is_tr else None))
                held_syms.add(sym)
                opened += 1
            nav = cash + sum(r2["qty"] * px.get(r2["sym"], r2["entry_px"])
                             for r2 in c.execute(
                                 "SELECT * FROM cmdlab_pos WHERE lane=?", (lane,)))
            c.execute("UPDATE cmdlab_state SET cash=?, last_run=? WHERE lane=?",
                      (round(cash, 2), now, lane))
            c.execute("INSERT OR REPLACE INTO cmdlab_nav VALUES (?,?,?)",
                      (day, lane, round(nav, 2)))
            out[lane] = {"nav": round(nav, 2), "opened": opened,
                         "closed": closed, "signals": lane_sigs}
    return {"ok": True, "day": day, "lanes": out,
            "signals": sigs, "tr_signals": tr_sigs, "data_fails": fails}


def status():
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM cmdlab_state")}
        pos = [dict(r) for r in c.execute(
            "SELECT * FROM cmdlab_pos ORDER BY lane, sym")]
        trades = [dict(r) for r in c.execute(
            "SELECT * FROM cmdlab_trades ORDER BY id DESC LIMIT 80")]
        hist = [dict(r) for r in c.execute("SELECT * FROM cmdlab_nav ORDER BY day")]
    px = {}
    for sym in {p["sym"] for p in pos}:
        try:
            px[sym] = _chart(sym, rng="5d")[-1]
        except Exception:
            px[sym] = None
    lanes = {}
    for lane in ALL_LANES:
        s = st.get(lane)
        if not s:
            lanes[lane] = {"nav": None, "ret_pct": None}
            continue
        nav = s["cash"] + sum(p["qty"] * (px.get(p["sym"]) or p["entry_px"])
                              for p in pos if p["lane"] == lane)
        lanes[lane] = {"nav": round(nav, 2),
                       "ret_pct": round(nav / START_NAV * 100 - 100, 2),
                       "cash": round(s["cash"], 2),
                       "started": s["started"], "last_run": s["last_run"]}
    for p in pos:
        p["last_px"] = px.get(p["sym"])
        p["pnl"] = (None if not p["last_px"] else
                    round(p["qty"] * (p["last_px"] - p["entry_px"]), 2))
    closed = [t for t in trades if t["exit_day"]]
    wins = sum(1 for t in closed if (t["pnl"] or 0) > 0)
    return {"ok": True, "started": bool(st), "lanes": lanes, "positions": pos,
            "trades": trades, "nav_history": hist, "start_nav": START_NAV,
            "closed_n": len(closed),
            "win_rate": round(100 * wins / len(closed), 1) if closed else None,
            "universe": ETFS}
