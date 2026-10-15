"""
fx_lab.py — Logicon Capital · FX Lab: a Shine-style paper falsification test
=============================================================================
Owner go-ahead 2026-10-05. Question on trial: does ANY evidenced FX strategy
deserve real Logicon capital? Three lanes run frozen rules for 12 months on
virtual money; the deliverable is the verdict, not the P&L.

THE RULES BELOW ARE FROZEN (Shine discipline). Improvements are new lanes,
never edits to these three. Verdict date: 12 months after /api/fxlab/start.
A lane survives if net return > 0 AND Sharpe > 0.5 at verdict.

Universe: G10 currencies (USD numeraire; 9 USD pairs via Yahoo).

Lane CARRY   — month-start: rank G10 by policy rate. Long the top 3, short
               the bottom 3 (a USD slot means that side simply holds USD
               cash). Within each side, legs are inverse-vol weighted
               (63-day realized) and the side's notional equals NAV
               (gross ≈ 2× NAV).
Lane CARRY-V — identical, plus the trend veto: a leg whose direction
               disagrees with the sign of its currency's 12-month return
               vs USD sits that month in cash. No replacement.
Lane TSMOM   — each non-USD G10 currency: direction = sign of its 12-month
               return vs USD measured one month ago ('12-1'); legs
               inverse-vol weighted, gross capped at 2× NAV.
Lane TR30    — (added 2026-10-06, owner strategy, FROZEN) a DAILY overlay
               lane, separate from the monthly machinery: buy a currency
               when its USD price closes within 1% of the 30-bar high
               (fresh signal, LONG only), exit when it closes 15% below the
               peak since entry (trailing, no time limit). Slot = NAV/4,
               max 4 legs, one per currency. Runs off the 17:10 NAV job.

Costs: 4bp round-trip on traded notional (8bp for SEK/NOK legs), charged on
the delta at each rebalance. Valuation marks: Yahoo (same fallback source
Shine trusts). Policy rates are DATA, not code: seeded below, editable from
the lab page, snapshotted into every rebalance's order log. The lab does
not start until the owner confirms the rates and presses Start.

Storage: fxlab_* tables in data/labs/labs.sqlite (runtime; CSV export in git).
Scheduled (labs_runner): rebalance first weekday 07:15 ET monthly; NAV
snapshot 17:10 ET weekdays. Nothing here touches a broker — paper only.
"""

import json
import math
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Moved to the Paper Lab 2026-10-15 (from combo-trader-tv @ 315faef): rules
# verbatim; only the journal moved — out of the trader's logicon_journal
# into the lab's own DB, imported once by `labs_runner.py import`.
DB = BASE_DIR / "data" / "labs" / "labs.sqlite"

START_NAV = 10_000.0
LANES = ("CARRY", "CARRY-V", "TSMOM")
COST_RT = 0.0004
COST_RT_SCANDI = 0.0008
GROSS = 2.0
# TR30 (owner lane, 2026-10-06, FROZEN): buy within 1% of the 30-bar high
# of the currency's USD price, exit 15% below the peak close since entry
# (trailing). Backtest caveat, on the record: FX daily bars produced only
# 36 trades / −0.4% avg — this lane exists to settle it forward.
TR_LANE = "TR30"
TR_W, TR_BAND, TR_STOP = 30, 0.99, 0.85
TR_POS_FRAC = 0.25

# currency -> (yahoo pair, inverted?)  price-of-currency-in-USD = pair or 1/pair
PAIR = {"EUR": ("EURUSD", False), "GBP": ("GBPUSD", False),
        "AUD": ("AUDUSD", False), "NZD": ("NZDUSD", False),
        "JPY": ("USDJPY", True),  "CHF": ("USDCHF", True),
        "CAD": ("USDCAD", True),  "SEK": ("USDSEK", True),
        "NOK": ("USDNOK", True)}
G10 = ["USD"] + list(PAIR)

# SEED policy rates, % — as of 2026-10, UNVERIFIED: the lab page shows them
# red until the owner saves them once; Start is blocked until then.
SEED_RATES = {"USD": 4.00, "EUR": 2.15, "JPY": 1.00, "GBP": 3.75,
              "CHF": 0.25, "CAD": 2.50, "AUD": 3.60, "NZD": 3.00,
              "SEK": 2.00, "NOK": 4.00}

SCHEMA = """
CREATE TABLE IF NOT EXISTS fxlab_state  (lane TEXT PRIMARY KEY, nav REAL,
  started TEXT, last_rebalance TEXT);
CREATE TABLE IF NOT EXISTS fxlab_rates  (ccy TEXT PRIMARY KEY, rate REAL,
  updated TEXT);
CREATE TABLE IF NOT EXISTS fxlab_pos    (lane TEXT, ccy TEXT, notional REAL,
  entry_px REAL, PRIMARY KEY (lane, ccy));
CREATE TABLE IF NOT EXISTS fxlab_orders (id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, lane TEXT, ccy TEXT, action TEXT, notional REAL, px REAL, note TEXT);
CREATE TABLE IF NOT EXISTS fxlab_nav    (day TEXT, lane TEXT, nav REAL,
  PRIMARY KEY (day, lane));
CREATE TABLE IF NOT EXISTS fxlab_trpos  (ccy TEXT PRIMARY KEY, qty REAL,
  entry_px REAL, entry_day TEXT, bars_held INTEGER, peak_px REAL);
"""


def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


# ── market data (Yahoo, UA required; same source family as Shine's fallback) ─
def _chart(sym, rng="1y", interval="1d"):
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}=X"
           f"?range={rng}&interval={interval}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    res = d["chart"]["result"][0]
    out = [c for c in res["indicators"]["quote"][0]["close"] if c]
    return out


def _ccy_series(ccy, rng="2y"):
    """Daily price of `ccy` in USD, oldest→newest."""
    pair, inv = PAIR[ccy]
    px = _chart(pair, rng=rng)
    return [1.0 / p for p in px] if inv else list(px)


def _last_px(series):
    return series[-1] if series else None


def _vol63(series):
    s = series[-64:]
    if len(s) < 30:
        return None
    lr = [math.log(s[i] / s[i - 1]) for i in range(1, len(s))]
    m = sum(lr) / len(lr)
    v = math.sqrt(sum((x - m) ** 2 for x in lr) / len(lr))
    return v * math.sqrt(252)


def _ret_12_1(series):
    """12-month return measured one month ago (the '12-1' convention)."""
    if len(series) < 274:
        return None
    return series[-22] / series[-274] - 1


def trail_signal(c):
    """TR30 entry: within 1% of the 30-bar high, FRESH (false yesterday)."""
    if len(c) < TR_W + 2:
        return False
    cond = c[-1] >= max(c[-TR_W:]) * TR_BAND
    prev = c[-2] >= max(c[-TR_W - 1:-1]) * TR_BAND
    return cond and not prev


# ── rates ────────────────────────────────────────────────────────────────────
def get_rates():
    with _db() as c:
        rows = {r["ccy"]: dict(r) for r in
                c.execute("SELECT * FROM fxlab_rates").fetchall()}
    out = {}
    for ccy in G10:
        if ccy in rows:
            out[ccy] = {"rate": rows[ccy]["rate"], "updated": rows[ccy]["updated"],
                        "verified": True}
        else:
            out[ccy] = {"rate": SEED_RATES[ccy], "updated": None, "verified": False}
    return out


def set_rates(body):
    n = 0
    with _db() as c:
        for ccy, rate in (body or {}).items():
            if ccy in G10:
                try:
                    c.execute("INSERT OR REPLACE INTO fxlab_rates VALUES (?,?,?)",
                              (ccy, float(rate),
                               datetime.now(timezone.utc).isoformat(timespec="seconds")))
                    n += 1
                except (TypeError, ValueError):
                    continue
    return n


def rates_verified():
    return all(v["verified"] for v in get_rates().values())


# ── target weights per lane (signed notional fractions of NAV) ──────────────
def _targets(lane, rates, vols, r121):
    tgt = {}
    if lane in ("CARRY", "CARRY-V"):
        ranked = sorted(G10, key=lambda x: -rates[x]["rate"])
        longs = [x for x in ranked[:3] if x != "USD"]
        shorts = [x for x in ranked[-3:] if x != "USD"]
        for side, sign in ((longs, 1), (shorts, -1)):
            ws = {c: 1.0 / vols[c] for c in side if vols.get(c)}
            tot = sum(ws.values())
            for c, w in ws.items():
                tgt[c] = sign * w / tot          # each side sums to 1.0 × NAV
        if lane == "CARRY-V":
            for c in list(tgt):
                r = r121.get(c)
                if r is None or (r > 0) != (tgt[c] > 0):
                    tgt[c] = 0.0                 # trend veto: sit in cash
    else:                                        # TSMOM 12-1
        ws = {}
        for c in PAIR:
            r = r121.get(c)
            v = vols.get(c)
            if r is None or not v:
                continue
            ws[c] = (1 if r > 0 else -1) / v
        tot = sum(abs(w) for w in ws.values())
        if tot > 0:
            for c, w in ws.items():
                tgt[c] = w / tot * GROSS
    return {c: w for c, w in tgt.items() if abs(w) > 1e-9}


def _mark_positions(c, lane, px):
    """Unrealized P&L of lane's open legs at prices px (ccy -> USD price)."""
    pnl = 0.0
    for r in c.execute("SELECT * FROM fxlab_pos WHERE lane=?", (lane,)):
        p = px.get(r["ccy"])
        if p and r["entry_px"]:
            pnl += r["notional"] * (p / r["entry_px"] - 1)
    return pnl


def rebalance(force=False):
    """Month-start rebalance of all lanes. Idempotent per calendar month."""
    if not rates_verified():
        return {"ok": False, "msg": "policy rates not confirmed — save them on the lab page first"}
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM fxlab_state")}
    if not st:
        return {"ok": False, "msg": "lab not started"}
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if not force and all((s.get("last_rebalance") or "").startswith(month)
                         for s in st.values()):
        return {"ok": True, "msg": f"already rebalanced for {month}"}

    series = {ccy: _ccy_series(ccy) for ccy in PAIR}
    px = {ccy: _last_px(s) for ccy, s in series.items()}
    vols = {ccy: _vol63(s) for ccy, s in series.items()}
    r121 = {ccy: _ret_12_1(s) for ccy, s in series.items()}
    rates = get_rates()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rates_note = " ".join(f"{k}:{v['rate']:g}" for k, v in rates.items())
    out = {}
    with _db() as c:
        for lane in LANES:
            nav = st[lane]["nav"] + _mark_positions(c, lane, px)   # realize
            tgt = _targets(lane, rates, vols, r121)
            old = {r["ccy"]: r["notional"] for r in
                   c.execute("SELECT * FROM fxlab_pos WHERE lane=?", (lane,))}
            cost = 0.0
            for ccy in set(old) | set(tgt):
                new_n = tgt.get(ccy, 0.0) * nav
                delta = abs(new_n - old.get(ccy, 0.0))
                rt = COST_RT_SCANDI if ccy in ("SEK", "NOK") else COST_RT
                cost += delta * rt / 2            # half-spread per side traded
            nav -= cost
            c.execute("DELETE FROM fxlab_pos WHERE lane=?", (lane,))
            for ccy, w in tgt.items():
                c.execute("INSERT INTO fxlab_pos VALUES (?,?,?,?)",
                          (lane, ccy, w * nav, px[ccy]))
                c.execute("INSERT INTO fxlab_orders (ts,lane,ccy,action,notional,px,note)"
                          " VALUES (?,?,?,?,?,?,?)",
                          (now, lane, ccy, "LONG" if w > 0 else "SHORT",
                           round(abs(w * nav), 2), px[ccy],
                           f"w={w:+.3f} vol={vols.get(ccy) or 0:.3f} "
                           f"r121={(r121.get(ccy) or 0)*100:+.1f}%"))
            c.execute("UPDATE fxlab_state SET nav=?, last_rebalance=? WHERE lane=?",
                      (round(nav, 2), now, lane))
            c.execute("INSERT OR REPLACE INTO fxlab_nav VALUES (?,?,?)",
                      (now[:10], lane, round(nav, 2)))
            out[lane] = {"nav": round(nav, 2), "legs": len(tgt),
                         "cost": round(cost, 2)}
        c.execute("INSERT INTO fxlab_orders (ts,lane,ccy,action,notional,px,note)"
                  " VALUES (?,?,?,?,?,?,?)",
                  (now, "ALL", "-", "REBALANCE", 0, 0, ("rates " + rates_note)[:200]))
    return {"ok": True, "month": month, "lanes": out}


def start():
    """Owner-confirmed start: initialize lanes and run the first rebalance."""
    if not rates_verified():
        return {"ok": False, "msg": "confirm the policy rates first (save them once)"}
    with _db() as c:
        if c.execute("SELECT COUNT(*) FROM fxlab_state").fetchone()[0]:
            return {"ok": False, "msg": "lab already started"}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for lane in LANES:
            c.execute("INSERT INTO fxlab_state VALUES (?,?,?,NULL)",
                      (lane, START_NAV, now))
    return rebalance(force=True)


def tr_daily():
    """TR30 owner lane — one pass per weekday, driven by the 17:10 NAV job.
    Keeps its own cash/positions (fxlab_state.nav = cash for this lane;
    last_rebalance doubles as last-run date). Idempotent per day."""
    with _db() as c:
        if not c.execute("SELECT COUNT(*) FROM fxlab_state WHERE lane IN (?,?,?)",
                         LANES).fetchone()[0]:
            return {"ok": False, "msg": "lab not started"}
        row = c.execute("SELECT * FROM fxlab_state WHERE lane=?",
                        (TR_LANE,)).fetchone()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if row:
            cash, last_run = row["nav"], row["last_rebalance"]
        else:
            # TR30 joined after the lab started — its own clock begins now
            c.execute("INSERT INTO fxlab_state VALUES (?,?,?,NULL)",
                      (TR_LANE, START_NAV, now))
            cash, last_run = START_NAV, None
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if (last_run or "") >= day:
        return {"ok": True, "msg": f"TR30 already ran for {day}"}

    series, fails = {}, []
    for ccy in PAIR:
        try:
            series[ccy] = _ccy_series(ccy, rng="1y")
        except Exception:
            fails.append(ccy)
    px = {k: v[-1] for k, v in series.items() if v}
    sigs = [k for k, v in series.items() if trail_signal(v)]
    closed = opened = 0
    with _db() as c:
        pos = [dict(r) for r in c.execute("SELECT * FROM fxlab_trpos")]
        held = set()
        for p in pos:
            ccy = p["ccy"]
            held.add(ccy)
            if ccy not in px:            # no mark today — age it tomorrow
                continue
            bars = p["bars_held"] + 1
            peak = max(p["peak_px"] or p["entry_px"], px[ccy])
            rt = COST_RT_SCANDI if ccy in ("SEK", "NOK") else COST_RT
            if px[ccy] < peak * TR_STOP:
                proceeds = p["qty"] * px[ccy] * (1 - rt / 2)
                pnl = proceeds - p["qty"] * p["entry_px"]
                cash += proceeds
                c.execute("INSERT INTO fxlab_orders (ts,lane,ccy,action,"
                          "notional,px,note) VALUES (?,?,?,?,?,?,?)",
                          (now, TR_LANE, ccy, "EXIT", round(proceeds, 2),
                           px[ccy],
                           f"trail exit · peak {peak:.4f} · held {bars} bars"
                           f" · pnl {pnl:+.2f}"
                           f" ({(px[ccy] / p['entry_px'] - 1) * 100:+.2f}%)"))
                c.execute("DELETE FROM fxlab_trpos WHERE ccy=?", (ccy,))
                held.discard(ccy)
                closed += 1
            else:
                c.execute("UPDATE fxlab_trpos SET bars_held=?, peak_px=? "
                          "WHERE ccy=?", (bars, peak, ccy))
        # entries: fresh signals, one leg per currency, while cash covers
        nav_now = cash + sum(p2["qty"] * px.get(p2["ccy"], p2["entry_px"])
                             for p2 in [dict(r) for r in
                                        c.execute("SELECT * FROM fxlab_trpos")])
        slot = nav_now * TR_POS_FRAC
        for ccy in sigs:
            if ccy in held or ccy not in px:
                continue
            if cash < slot * 0.98:
                c.execute("INSERT INTO fxlab_orders (ts,lane,ccy,action,"
                          "notional,px,note) VALUES (?,?,?,?,?,?,?)",
                          (now, TR_LANE, ccy, "SKIP", 0, px[ccy],
                           "signal skipped — fully invested"))
                continue
            rt = COST_RT_SCANDI if ccy in ("SEK", "NOK") else COST_RT
            qty = slot * (1 - rt / 2) / px[ccy]
            cash -= slot
            c.execute("INSERT INTO fxlab_trpos VALUES (?,?,?,?,0,?)",
                      (ccy, round(qty, 4), px[ccy], day, px[ccy]))
            c.execute("INSERT INTO fxlab_orders (ts,lane,ccy,action,"
                      "notional,px,note) VALUES (?,?,?,?,?,?,?)",
                      (now, TR_LANE, ccy, "LONG", round(slot, 2), px[ccy],
                       f"TR30 entry · within 1% of {TR_W}-bar high"))
            held.add(ccy)
            opened += 1
        nav = cash + sum(r2["qty"] * px.get(r2["ccy"], r2["entry_px"])
                         for r2 in c.execute("SELECT * FROM fxlab_trpos"))
        c.execute("UPDATE fxlab_state SET nav=?, last_rebalance=? WHERE lane=?",
                  (round(cash, 2), now, TR_LANE))
        c.execute("INSERT OR REPLACE INTO fxlab_nav VALUES (?,?,?)",
                  (day, TR_LANE, round(nav, 2)))
    return {"ok": True, "day": day, "nav": round(nav, 2), "opened": opened,
            "closed": closed, "signals": sigs, "data_fails": fails}


def snapshot_nav():
    """Daily NAV mark (17:10 ET weekdays)."""
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM fxlab_state")}
        if not st:
            return {"ok": False, "msg": "lab not started"}
        px = {}
        for ccy in PAIR:
            try:
                px[ccy] = _last_px(_chart(PAIR[ccy][0], rng="5d"))
                if PAIR[ccy][1] and px[ccy]:
                    px[ccy] = 1.0 / px[ccy]
            except Exception:
                px[ccy] = None
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out = {}
        for lane in LANES:
            nav = st[lane]["nav"] + _mark_positions(c, lane, px)
            c.execute("INSERT OR REPLACE INTO fxlab_nav VALUES (?,?,?)",
                      (day, lane, round(nav, 2)))
            out[lane] = round(nav, 2)
    try:                                 # TR30 daily pass rides this job
        tr = tr_daily()
        if tr.get("ok") and tr.get("nav") is not None:
            out[TR_LANE] = tr["nav"]
    except Exception as e:
        tr = {"ok": False, "msg": str(e)[:120]}
    return {"ok": True, "navs": out, "tr30": tr}


def status():
    with _db() as c:
        st = {r["lane"]: dict(r) for r in c.execute("SELECT * FROM fxlab_state")}
        pos = [dict(r) for r in c.execute("SELECT * FROM fxlab_pos ORDER BY lane, ccy")]
        trpos = [dict(r) for r in c.execute("SELECT * FROM fxlab_trpos ORDER BY ccy")]
        orders = [dict(r) for r in c.execute(
            "SELECT * FROM fxlab_orders ORDER BY id DESC LIMIT 60")]
        hist = [dict(r) for r in c.execute(
            "SELECT * FROM fxlab_nav ORDER BY day")]
        # live marks for display (best-effort; stale legs show entry px)
        px = {}
        for ccy in {p["ccy"] for p in pos} | {p["ccy"] for p in trpos}:
            try:
                px[ccy] = _last_px(_chart(PAIR[ccy][0], rng="5d"))
                if PAIR[ccy][1] and px[ccy]:
                    px[ccy] = 1.0 / px[ccy]
            except Exception:
                px[ccy] = None
        lanes = {}
        for lane in LANES:
            base = st.get(lane, {}).get("nav")
            lanes[lane] = {
                "started": st.get(lane, {}).get("started"),
                "last_rebalance": st.get(lane, {}).get("last_rebalance"),
                "nav": None if base is None else
                       round(base + _mark_positions(c, lane, px), 2),
                "ret_pct": None if base is None else round(
                    (base + _mark_positions(c, lane, px)) / START_NAV * 100 - 100, 2),
            }
        trs = st.get(TR_LANE)
        if trs:
            trnav = trs["nav"] + sum(p["qty"] * (px.get(p["ccy"]) or p["entry_px"])
                                     for p in trpos)
            lanes[TR_LANE] = {"started": trs["started"],
                              "last_rebalance": trs["last_rebalance"],
                              "nav": round(trnav, 2),
                              "ret_pct": round(trnav / START_NAV * 100 - 100, 2)}
    for p in pos:
        p["last_px"] = px.get(p["ccy"])
        p["pnl"] = (None if not (p["last_px"] and p["entry_px"]) else
                    round(p["notional"] * (p["last_px"] / p["entry_px"] - 1), 2))
    for p in trpos:                      # TR30 legs join the same table
        lp = px.get(p["ccy"])
        pos.append({"lane": TR_LANE, "ccy": p["ccy"],
                    "notional": round(p["qty"] * p["entry_px"], 2),
                    "entry_px": p["entry_px"], "last_px": lp,
                    "pnl": None if not lp else
                           round(p["qty"] * (lp - p["entry_px"]), 2),
                    "entry_day": p["entry_day"], "bars_held": p["bars_held"],
                    "peak_px": p["peak_px"]})
    return {"ok": True, "started": bool(st), "lanes": lanes, "positions": pos,
            "orders": orders, "nav_history": hist, "rates": get_rates(),
            "rates_verified": rates_verified(), "start_nav": START_NAV}
