"""
guru_lab.py — Logicon Capital · Gurus Lab: famous investors' 13F portfolios
==========================================================================
Owner 2026-11-14 ("create a section for gurus and stockrover portfolios in
our paper trade page so we can continue monitoring … see how stockrover is
showing performance too"). Two kinds of lanes, one performance engine:

  GURU lanes (public data) — a copy of each investor's 13F filing.
  STOCK ROVER lanes (private) — lists the owner pastes from Stock Rover.

THE GURU RULE (frozen; a change is a new lane):
  * Holdings = the filer's common-stock positions (13F "SHR") for a quarter,
    summed per ticker; the TOP 25 by reported value, weighted by that value.
  * A quarter becomes tradable 46 days after the quarter ends (the 13F
    deadline is 45 days) — the rebalance is the close of the first trading
    day on/after that date. Never earlier: no peeking at a filing before it
    was public.
  * Marks and fills at the day's dividend-adjusted close (Sharadar, through
    the data hub) · 5bp on traded notional · cash earns nothing · a stock
    whose prices stop (taken over, delisted) is turned into cash at its last
    close. $10,000 at each lane's first rebalance.
  * History from the first rebalance in 2014 is a POINT-IN-TIME BACKTEST
    (each quarter used only from its public date). From `paper_since` on the
    same rule runs forward as paper. Quarter targets are frozen the first time
    the lab sees them: later amendments never rewrite the past.
  Caveats shown on the page: 13F shows only US-listed longs (no shorts,
  options, cash or foreign shares) and is up to 4.5 months stale, so a copy is
  not the fund's real return; a filer that changed name is joined (Pershing).

STOCK ROVER lanes: the owner pastes a Stock Rover export (or "TICKER weight"
lines). Tracked FORWARD ONLY from the paste day (fills at that day's close);
a new paste of the same name is a rebalance. No backfill: a screen's list run
backwards is hindsight. PRIVATE: these lists are Stock Rover's content and
the owner's — they live only in the lab database (srlab_* tables are NOT in
labs_runner's CSV export, which the public repo commits).

Data: every price and filing comes from the estate data hub (LAB_DATA_URL,
"http://data.internal" inside the container — the Worker adds the service
pass). The price cache is its own SQLite file (never exported).
"""

import json
import math
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "data" / "labs" / "labs.sqlite"
CACHE_DB = BASE_DIR / "data" / "labs" / "guru_cache.sqlite"
ET = ZoneInfo("America/New_York")
DATA_URL = os.environ.get("LAB_DATA_URL", "http://data.internal")

START_NAV = 10_000.0
COST = 0.0005
TOP_N = 25
LAG_DAYS = 46
BACKTEST_FROM = "2014-01-01"
BENCH = "SPY"

# key -> (label, person, filer ids in priority order)
GURUS = {
    "BUFFETT":      ("Warren Buffett — Berkshire Hathaway", "Warren Buffett", ["BERHAT"]),
    "DRUCKENMILLER": ("Stanley Druckenmiller — Duquesne Family Office", "Stanley Druckenmiller", ["DUQUES"]),
    "TEPPER":       ("David Tepper — Appaloosa", "David Tepper", ["APPALO"]),
    "ICAHN":        ("Carl Icahn — Icahn Capital", "Carl Icahn", ["ICAHCC"]),
    "ACKMAN":       ("Bill Ackman — Pershing Square", "Bill Ackman", ["PERSQU", "PERSQ1"]),
    "LOEB":         ("Daniel Loeb — Third Point", "Daniel Loeb", ["THIPOI"]),
    "EINHORN":      ("David Einhorn — Greenlight (DME Capital)", "David Einhorn", ["DMECAP"]),
    "LILU":         ("Li Lu — Himalaya Capital", "Li Lu", ["HIMALA"]),
    "HOHN":         ("Chris Hohn — TCI Fund Management", "Chris Hohn", ["TCIFUN"]),
    "NYGREN":       ("Bill Nygren — Oakmark (Harris Associates)", "Bill Nygren", ["HARSSO"]),
    "BERKOWITZ":    ("Bruce Berkowitz — Fairholme", "Bruce Berkowitz", ["FAIRHO"]),
    "LAWRENCE":     ("Bryan Lawrence — Oakcliff Capital", "Bryan Lawrence", ["OAKCCA"]),
    "GAYNER":       ("Thomas Gayner — Markel Group", "Thomas Gayner", ["MARKEL"]),
    "KANTESARIA":   ("Dev Kantesaria — Valley Forge Capital", "Dev Kantesaria", ["VALFOR"]),
    "CHOU":         ("Francis Chou — Chou Associates", "Francis Chou", ["CHOUAS"]),
    "GATES":        ("Bill Gates — Gates Foundation Trust", "Bill Gates", ["GATESF"]),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS gurulab_state (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS gurulab_targets (lane TEXT, quarter TEXT, known TEXT,
  sym TEXT, weight REAL, value REAL, frozen_at TEXT, PRIMARY KEY (lane, quarter, sym));
CREATE TABLE IF NOT EXISTS srlab_lanes (key TEXT PRIMARY KEY, name TEXT, created TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS srlab_targets (lane TEXT, known TEXT, sym TEXT, weight REAL,
  PRIMARY KEY (lane, known, sym));
"""
CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS px (sym TEXT, day TEXT, adj REAL, PRIMARY KEY (sym, day));
CREATE TABLE IF NOT EXISTS px_meta (sym TEXT PRIMARY KEY, first TEXT, through TEXT, checked TEXT, empty INTEGER);
"""

STATE = {"busy": False, "progress": "", "error": None, "last": None}
_LOCK = threading.Lock()
_MEMO = {"key": None, "sims": None}


def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _cache():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(CACHE_DB, timeout=30)
    c.executescript(CACHE_SCHEMA)
    return c


def _today():
    return datetime.now(timezone.utc).astimezone(ET).strftime("%Y-%m-%d")


def _add(day, n):
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


# ── data hub client ─────────────────────────────────────────────────────────

def _hub(cap, **params):
    """GET <hub>/v1/<cap> -> rows. GURU_SHARADAR_DIRECT=1 (local tests only,
    never in the container: it holds no vendor key) goes straight to Sharadar."""
    if os.environ.get("GURU_SHARADAR_DIRECT") == "1":
        return _direct(cap, **params)
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{DATA_URL}/v1/{cap}?{q}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.loads(r.read())
    return j.get("data") or []


def _direct(cap, **p):
    base = "https://api.sharadar.com/v1.0/data/"

    def get(table, q):
        out, off = [], 0
        while True:
            u = base + table + "?" + urllib.parse.urlencode({**q, "format": "json", "limit": 10000, "offset": off})
            with urllib.request.urlopen(u, timeout=120) as r:
                rows = json.loads(r.read()).get("data") or []
            out += rows
            off += 10000
            if len(rows) < 10000:
                return out
    if cap == "holdings_13f":
        q = {"investorid": p["investor"]}
        if p.get("from"):
            q["date.gte"] = p["from"]
        return [{"symbol": r["ticker"].replace(".", "-"), "date": r["date"][:10], "type": r["securitytype"],
                 "value": r["value"], "units": r["units"]} for r in get("holdings", q)]
    if cap == "bars_daily":
        q = {"ticker": p["symbol"].replace("-", ".")}
        if p.get("from"):
            q["date.gte"] = p["from"]
        rows = get("stocks", q) or get("funds", q)
        return sorted([{"date": r["date"][:10], "close": r["close"], "adj": r.get("closeadj")} for r in rows],
                      key=lambda r: r["date"])
    raise KeyError(cap)


# ── prices (cached) ─────────────────────────────────────────────────────────

def _fetch_px(sym, frm, today):
    rows = _hub("bars_daily", symbol=sym, **{"from": frm})
    good = [(sym, r["date"], float(r.get("adj") or r["close"])) for r in rows
            if (r.get("adj") or r.get("close"))]
    with _cache() as c:
        c.executemany("INSERT OR REPLACE INTO px VALUES (?,?,?)", good)
        first = c.execute("SELECT MIN(day), MAX(day) FROM px WHERE sym=?", (sym,)).fetchone()
        c.execute("INSERT OR REPLACE INTO px_meta VALUES (?,?,?,?,?)",
                  (sym, first[0], first[1], today, 0 if first[0] else 1))
    return len(good)


def ensure_prices(needs, today=None, log=None):
    """needs: {sym: first_day_needed}. Fetch what the cache lacks: a symbol
    never seen is fetched from its first day; a symbol already cached gets the
    days after its last bar (once per day). Dividend adjustment can rewrite old
    closes after a payout, so a cached symbol is refetched in full weekly."""
    today = today or _today()
    with _cache() as c:
        meta = {r[0]: r[1:] for r in c.execute("SELECT * FROM px_meta")}
    todo = []
    for sym, frm in needs.items():
        m = meta.get(sym)
        if not m:
            todo.append((sym, _add(frm, -10)))
            continue
        first, through, checked, empty = m
        if checked == today:
            continue
        stale_week = not checked or checked < _add(today, -7)
        if empty and not stale_week:
            continue
        if stale_week or (first and frm < first):
            todo.append((sym, _add(min(frm, first or frm), -10)))
        else:
            todo.append((sym, _add(through or frm, -7)))
    for i, (sym, frm) in enumerate(todo):
        if log:
            log(f"prices {i + 1}/{len(todo)} {sym}")
        try:
            _fetch_px(sym, frm, today)
        except Exception as e:                       # one bad ticker never stops the lab
            STATE["error"] = f"{sym}: {str(e)[:120]}"
    return len(todo)


def load_px(syms):
    out = {}
    with _cache() as c:
        for s in syms:
            rows = c.execute("SELECT day, adj FROM px WHERE sym=? ORDER BY day", (s,)).fetchall()
            out[s] = ([r[0] for r in rows], [r[1] for r in rows])
    return out


# ── targets ─────────────────────────────────────────────────────────────────

def quarter_targets(rows, top_n=TOP_N):
    """13F rows (one filer, many quarters) -> {quarter_end: [(sym, weight, value)]}."""
    by_q = {}
    for r in rows:
        if r.get("type") != "SHR" or not r.get("symbol") or not (r.get("value") or 0) > 0:
            continue
        q = by_q.setdefault(r["date"][:10], {})
        q[r["symbol"]] = q.get(r["symbol"], 0.0) + float(r["value"])
    out = {}
    for qd, vals in by_q.items():
        top = sorted(vals.items(), key=lambda kv: -kv[1])[:top_n]
        tot = sum(v for _, v in top)
        out[qd] = [(s, v / tot, v) for s, v in top] if tot > 0 else []
    return out


def known_day(quarter_end):
    return _add(quarter_end, LAG_DAYS)


def refresh_targets(today=None, log=None):
    """Pull each filer's 13F history through the hub and freeze any quarter
    the lab has not seen. Frozen quarters are never rewritten."""
    today = today or _today()
    with _db() as c:
        have = {(r["lane"], r["quarter"]) for r in c.execute("SELECT DISTINCT lane, quarter FROM gurulab_targets")}
    added = 0
    for key, (_, _, ids) in GURUS.items():
        if log:
            log(f"13F {key}")
        merged = {}
        for fid in ids:                              # earlier id wins a quarter both filed
            try:
                rows = _hub("holdings_13f", investor=fid, **{"from": _add(BACKTEST_FROM, -200)})
            except Exception as e:
                STATE["error"] = f"13F {fid}: {str(e)[:120]}"
                continue
            for qd, tg in quarter_targets(rows).items():
                merged.setdefault(qd, tg)
        new = [(qd, tg) for qd, tg in merged.items()
               if (key, qd) not in have and tg and known_day(qd) <= today]
        with _db() as c:
            for qd, tg in new:
                c.executemany("INSERT OR IGNORE INTO gurulab_targets VALUES (?,?,?,?,?,?,?)",
                              [(key, qd, known_day(qd), s, w, v, today) for s, w, v in tg])
        added += len(new)
    return added


def guru_schedule(c, key):
    rows = c.execute("SELECT quarter, known, sym, weight FROM gurulab_targets WHERE lane=? "
                     "ORDER BY quarter", (key,)).fetchall()
    sched = {}
    for r in rows:
        sched.setdefault((r["quarter"], r["known"]), {})[r["sym"]] = r["weight"]
    return [(known, w, q) for (q, known), w in sorted(sched.items()) if known >= BACKTEST_FROM]


def sr_schedule(c, key):
    rows = c.execute("SELECT known, sym, weight FROM srlab_targets WHERE lane=? ORDER BY known", (key,)).fetchall()
    sched = {}
    for r in rows:
        sched.setdefault(r["known"], {})[r["sym"]] = r["weight"]
    return [(k, w, k) for k, w in sorted(sched.items())]


# ── simulation ──────────────────────────────────────────────────────────────

def simulate(schedule, px, days, cost=COST, start_nav=START_NAV):
    """schedule: [(known_day, {sym: weight}, label)] sorted; px: {sym: (days, closes)};
    days: the trading calendar (benchmark days). Rebalance at the close of the
    first calendar day >= known_day. Returns {days, nav, rebal: [...], gains_by_day}.
    A symbol without a close on a day keeps its last close; after its final
    bar it is sold to cash at that close (taken over / delisted)."""
    if not schedule:
        return None
    ix = {s: dict(zip(d, cl)) for s, (d, cl) in px.items()}
    stale = _add(days[-1], -10) if days else ""
    # a symbol counts as GONE only if its prices stopped well before the
    # calendar ends (a late fetch is not a delisting)
    last_day = {s: (d[-1] if d and d[-1] < stale else None) for s, (d, _) in px.items()}
    first_reb = bisect_left(days, schedule[0][0])
    if first_reb >= len(days):
        return None
    qty, cash, nav_hist, out_days, rebals = {}, start_nav, [], [], []
    last_px = {}
    pos_gain = []                                   # per day: {sym: $ gain that day}
    si = 0
    for t in range(first_reb, len(days)):
        d = days[t]
        g = {}
        for s in list(qty):                         # mark
            p = ix.get(s, {}).get(d)
            if p is None:
                if last_day.get(s) and d > last_day[s]:      # gone: to cash at last close
                    cash += qty[s] * last_px[s]
                    del qty[s]
                    continue
                p = last_px[s]
            g[s] = qty[s] * (p - last_px[s])
            last_px[s] = p
        nav = cash + sum(q * last_px[s] for s, q in qty.items())
        while si < len(schedule) and schedule[si][0] <= d:
            known, tgt, label = schedule[si]
            si += 1
            if si < len(schedule) and schedule[si][0] <= d:
                continue                            # a later quarter is already public
            usable = {s: w for s, w in tgt.items() if ix.get(s, {}).get(d) is not None}
            tot = sum(usable.values())
            # size on NAV net of this trade's cost (two passes) so cash never goes below 0
            want = {s: nav * w / tot / ix[s][d] for s, w in usable.items()} if tot > 0 else {}
            turn0 = sum(abs(want.get(s, 0.0) - qty.get(s, 0.0)) * ix.get(s, {}).get(d, last_px.get(s, 0))
                        for s in set(qty) | set(want))
            want = {s: q * (1 - turn0 * cost / max(nav, 1e-9)) for s, q in want.items()}
            turn = 0.0
            for s in set(qty) | set(want):
                p = ix.get(s, {}).get(d, last_px.get(s))
                turn += abs(want.get(s, 0.0) - qty.get(s, 0.0)) * p
            fee = turn * cost
            cash = nav - fee - sum(q * ix[s][d] for s, q in want.items())
            qty = {s: q for s, q in want.items() if q > 0}
            for s in qty:
                last_px[s] = ix[s][d]
            nav = cash + sum(q * last_px[s] for s, q in qty.items())
            rebals.append({"day": d, "quarter": label, "n": len(qty), "skipped": len(tgt) - len(usable),
                           "turnover_pct": round(turn / max(nav, 1e-9) * 100, 1)})
            g["__cost"] = -fee
        out_days.append(d)
        nav_hist.append(nav)
        pos_gain.append(g)
    hold = {s: q * last_px[s] for s, q in qty.items()}
    return {"days": out_days, "nav": nav_hist, "rebal": rebals, "gains": pos_gain,
            "holdings": hold, "cash": cash, "last_px": dict(last_px)}


# ── metrics ─────────────────────────────────────────────────────────────────

RANGES = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "2Y": 730, "3Y": 1095, "5Y": 1826, "10Y": 3652}


def range_start(days, rng):
    end = days[-1]
    if rng == "ALL":
        return 0
    if rng == "YTD":
        return max(0, bisect_left(days, end[:4] + "-01-01") - 1)
    n = RANGES.get(rng, 1826)
    return max(0, bisect_right(days, _add(end, -n)) - 1)


def _rets(v):
    return [v[i] / v[i - 1] - 1 for i in range(1, len(v)) if v[i - 1]]


def metrics(nav, bench):
    """nav, bench: aligned daily values over the window."""
    if len(nav) < 3:
        return {}
    r, b = _rets(nav), _rets(bench)
    n = min(len(r), len(b))
    r, b = r[:n], b[:n]
    mr, mb = sum(r) / n, sum(b) / n
    vr = sum((x - mr) ** 2 for x in r) / max(1, n - 1)
    vb = sum((x - mb) ** 2 for x in b) / max(1, n - 1)
    cov = sum((x - mr) * (y - mb) for x, y in zip(r, b)) / max(1, n - 1)
    peak, mdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    yrs = n / 252
    twr = nav[-1] / nav[0] - 1
    btwr = bench[-1] / bench[0] - 1
    vol = math.sqrt(vr * 252)
    return {"twr": twr, "bench": btwr, "excess": twr - btwr,
            "cagr": (1 + twr) ** (1 / yrs) - 1 if yrs >= 1 else None,
            "bench_cagr": (1 + btwr) ** (1 / yrs) - 1 if yrs >= 1 else None,
            "vol": vol, "bench_vol": math.sqrt(vb * 252),
            "beta": cov / vb if vb else None,
            "corr": cov / math.sqrt(vr * vb) if vr and vb else None,
            "maxdd": mdd, "sharpe": (mr * 252) / vol if vol else None,
            "updays": sum(1 for x in r if x > 0) / n}


def period_table(days, nav, bench, kind):
    """Monthly ("M") or yearly ("Y") returns of nav and bench (aligned days)."""
    key = (lambda d: d[:7]) if kind == "M" else (lambda d: d[:4])
    out, prev_v, prev_b, cur = [], nav[0], bench[0], key(days[0])
    for i in range(1, len(days)):
        k = key(days[i])
        if k != cur:
            out.append({"p": cur, "r": nav[i - 1] / prev_v - 1, "b": bench[i - 1] / prev_b - 1})
            prev_v, prev_b, cur = nav[i - 1], bench[i - 1], k
    out.append({"p": cur, "r": nav[-1] / prev_v - 1, "b": bench[-1] / prev_b - 1, "partial": True})
    return out


# ── lanes ───────────────────────────────────────────────────────────────────

def _lanes(c):
    lanes = [{"key": k, "label": v[0], "person": v[1], "group": "guru"} for k, v in GURUS.items()]
    for r in c.execute("SELECT * FROM srlab_lanes ORDER BY created"):
        lanes.append({"key": r["key"], "label": r["name"], "person": "", "group": "stockrover",
                      "created": r["created"]})
    return lanes


def _state(c, k, default=None):
    r = c.execute("SELECT v FROM gurulab_state WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def _set_state(c, k, v):
    c.execute("INSERT OR REPLACE INTO gurulab_state VALUES (?,?)", (k, json.dumps(v)))


def run_all(today=None, log=None):
    """The daily pass: new filings, prices, then every lane's NAV. Safe to rerun."""
    today = today or _today()
    log = log or (lambda m: STATE.__setitem__("progress", m))
    added = refresh_targets(today, log)
    with _db() as c:
        needs = {BENCH: BACKTEST_FROM}
        for r in c.execute("SELECT sym, MIN(known) AS k FROM gurulab_targets GROUP BY sym"):
            needs[r["sym"]] = min(needs.get(r["sym"], r["k"]), r["k"])
        for r in c.execute("SELECT sym, MIN(known) AS k FROM srlab_targets GROUP BY sym"):
            needs[r["sym"]] = min(needs.get(r["sym"], r["k"]), r["k"])
        if _state(c, "paper_since") is None:
            _set_state(c, "paper_since", today)     # owner go 2026-11-14: paper from the first live pass
    # held now = in the latest quarter of some lane -> refreshed daily; others weekly
    fetched = ensure_prices(needs, today, log)
    _MEMO["key"] = None
    try:
        _sims()                                     # warm: the page opens without the ~5 s rebuild
    except Exception as e:
        STATE["error"] = f"build: {str(e)[:120]}"
    with _db() as c:
        _set_state(c, "last_run", {"day": today, "new_quarters": added, "prices_fetched": fetched,
                                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"ok": True, "day": today, "new_quarters": added, "prices_fetched": fetched}


def daily():
    """labs_runner entry: run in a thread (the first backfill takes minutes)."""
    if STATE["busy"]:
        return {"ok": True, "msg": "already running: " + STATE["progress"]}
    def go():
        with _LOCK:
            STATE.update(busy=True, error=None)
            try:
                STATE["last"] = run_all()
            except Exception as e:
                STATE["error"] = str(e)[:200]
            finally:
                STATE["busy"] = False
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True, "msg": "started"}


def _sims():
    with _db() as c, _cache() as cc:
        ver = (c.execute("SELECT COUNT(*), MAX(frozen_at) FROM gurulab_targets").fetchone()[:],
               c.execute("SELECT COUNT(*), MAX(known) FROM srlab_targets").fetchone()[:],
               cc.execute("SELECT MAX(checked), COUNT(*) FROM px_meta").fetchone()[:])
        if _MEMO["key"] == ver and _MEMO["sims"]:
            return _MEMO["sims"]
        lanes = _lanes(c)
        scheds = {l["key"]: (guru_schedule(c, l["key"]) if l["group"] == "guru" else sr_schedule(c, l["key"]))
                  for l in lanes}
        paper_since = _state(c, "paper_since")
        last_run = _state(c, "last_run")
    syms = {BENCH} | {s for sc in scheds.values() for _, w, _ in sc for s in w}
    px = load_px(syms)
    bdays, bpx = px[BENCH]
    sims = {}
    for l in lanes:
        sim = simulate(scheds[l["key"]], px, bdays) if bdays else None
        if sim:
            sim["sched"] = scheds[l["key"]]
        sims[l["key"]] = (l, sim)
    out = {"lanes": sims, "bdays": bdays, "bpx": bpx, "paper_since": paper_since, "last_run": last_run}
    _MEMO.update(key=ver, sims=out)
    return out


def _window(S, sim, rng):
    i0 = range_start(sim["days"], rng)
    days, nav = sim["days"][i0:], sim["nav"][i0:]
    bmap = dict(zip(S["bdays"], S["bpx"]))
    bench = [bmap[d] for d in days]
    return i0, days, nav, bench


def summary(rng="5Y"):
    S = _sims()
    rows = []
    for key, (l, sim) in S["lanes"].items():
        row = dict(l)
        if sim and len(sim["days"]) > 2:
            i0, days, nav, bench = _window(S, sim, rng)
            m = metrics(nav, bench)
            row.update({"start": sim["days"][0], "from": days[0], "to": days[-1],
                        "value": sim["nav"][-1], "n_hold": len(sim["holdings"]),
                        "last_quarter": sim["rebal"][-1]["quarter"] if sim["rebal"] else None,
                        "next_rebalance": _next_known(sim) if l["group"] == "guru" else None, **m,
                        "short_history": bool(rng in RANGES and
                                              days[0] > _add(S["bdays"][-1], -RANGES[rng] + 10))})
        else:
            row.update({"start": None, "pending": True})
        rows.append(row)
    bm = None
    if len(S["bdays"]) > 2:
        i0 = range_start(S["bdays"], rng)
        b = S["bpx"][i0:]
        bm = {"twr": b[-1] / b[0] - 1, **{k: v for k, v in metrics(b, b).items() if k in ("vol", "maxdd", "sharpe")}}
    return {"ok": True, "range": rng, "lanes": rows, "bench": bm, "paper_since": S["paper_since"],
            "last_run": S["last_run"], "busy": STATE["busy"], "progress": STATE["progress"],
            "error": STATE["error"], "asof": S["bdays"][-1] if S["bdays"] else None}


def _next_known(sim):
    """Public date of the next 13F quarter after the last one the lane holds."""
    sc = sim.get("sched") or []
    last = sc[-1][2] if sc else None
    if not last or not re.match(r"\d{4}-\d{2}-\d{2}$", last):
        return None
    y, m = int(last[:4]), int(last[5:7]) + 3
    if m > 12:
        y, m = y + 1, m - 12
    qe = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return known_day(qe.isoformat())


def _downsample(days, *series, maxn=900):
    if len(days) <= maxn:
        return days, series
    step = len(days) / maxn
    idx = sorted({int(i * step) for i in range(maxn)} | {len(days) - 1})
    return [days[i] for i in idx], tuple([s[i] for i in idx] for s in series)


def lane_detail(key, rng="5Y"):
    S = _sims()
    if key not in S["lanes"]:
        return {"ok": False, "msg": "unknown lane"}
    l, sim = S["lanes"][key]
    if not sim or len(sim["days"]) < 3:
        return {"ok": True, "lane": l, "pending": True,
                "msg": "waiting for prices — the lab's daily pass fills this in"}
    i0, days, nav, bench = _window(S, sim, rng)
    bmap = dict(zip(S["bdays"], S["bpx"]))
    full_bench = [bmap[d] for d in sim["days"]]
    m = metrics(nav, bench)
    peak, dd = nav[0], []
    for v in nav:
        peak = max(peak, v)
        dd.append(v / peak - 1)
    bn = [b / bench[0] * nav[0] for b in bench]
    dds, (navs, bns, dd_s) = _downsample(days, nav, bn, dd)
    # holdings detail over the window
    gains = {}
    for g in sim["gains"][i0 + 1:]:
        for s, v in g.items():
            gains[s] = gains.get(s, 0.0) + v
    total_gain = nav[-1] - nav[0]
    navnow = sim["nav"][-1]
    last_tgt = sim["sched"][-1][1] if sim["sched"] else {}
    hold_rows = []
    for s in sorted(set(sim["holdings"]) | {s for s in gains if s != "__cost"},
                    key=lambda s: -sim["holdings"].get(s, 0)):
        hold_rows.append({"sym": s, "value": sim["holdings"].get(s, 0.0),
                          "weight": sim["holdings"].get(s, 0.0) / navnow if navnow else 0,
                          "target": last_tgt.get(s), "gain": gains.get(s, 0.0),
                          "share_of_return": gains.get(s, 0.0) / total_gain if total_gain else None,
                          "closed": s not in sim["holdings"]})
    trailing = {}
    for r in ("1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "10Y"):
        j = range_start(sim["days"], r)
        if r in RANGES and sim["days"][0] > _add(sim["days"][-1], -RANGES[r] + 10):
            trailing[r] = None
            continue
        trailing[r] = {"r": sim["nav"][-1] / sim["nav"][j] - 1,
                       "b": bmap[sim["days"][-1]] / bmap[sim["days"][j]] - 1}
    return {"ok": True, "lane": l, "range": rng, "from": days[0], "to": days[-1],
            "start": sim["days"][0], "paper_since": S["paper_since"],
            "metrics": m, "value": navnow, "start_value": nav[0], "cash": sim["cash"],
            "series": {"days": dds, "nav": navs, "bench": bns, "dd": dd_s},
            "monthly": period_table(sim["days"], sim["nav"], full_bench, "M"),
            "yearly": period_table(sim["days"], sim["nav"], full_bench, "Y"),
            "holdings": hold_rows, "costs": -gains.get("__cost", 0.0),
            "trailing": trailing, "rebalances": sim["rebal"][-12:][::-1],
            "next_rebalance": _next_known(sim) if l["group"] == "guru" else None}


# ── Stock Rover lanes (private) ─────────────────────────────────────────────

def parse_list(text):
    """A Stock Rover export (CSV with a Ticker column, optional weight-like
    column) or plain lines "TICKER [weight]". Returns {sym: weight} summing to 1."""
    lines = [l for l in (text or "").replace("\r", "").split("\n") if l.strip()]
    if not lines:
        return {}
    import csv as _csv
    head = [h.strip().lower() for h in next(_csv.reader([lines[0]]))]
    out = {}
    if "ticker" in head or "symbol" in head:
        ti = head.index("ticker") if "ticker" in head else head.index("symbol")
        wi = next((i for i, h in enumerate(head) if any(k in h for k in ("% of end", "weight", "% of port", "allocation"))), None)
        if wi is None:
            wi = next((i for i, h in enumerate(head) if h.startswith("end value") or h == "value" or h == "market value"), None)
        for row in _csv.reader(lines[1:]):
            if len(row) <= ti:
                continue
            s = row[ti].strip().upper()
            if not re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", s) or s in ("CASH", "SUMMARY"):
                continue
            w = 1.0
            if wi is not None and wi < len(row):
                try:
                    w = float(re.sub(r"[^0-9.\-]", "", row[wi]) or "nan")
                except ValueError:
                    w = 1.0
                if not (w > 0):
                    continue
            out[s.replace(".", "-")] = out.get(s.replace(".", "-"), 0.0) + w
    else:
        for l in lines:
            parts = re.split(r"[\s,;\t]+", l.strip())
            s = parts[0].upper()
            if not re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", s) or s in ("CASH", "TICKER", "SYMBOL"):
                continue
            w = 1.0
            if len(parts) > 1:
                try:
                    w = float(parts[1].rstrip("%"))
                except ValueError:
                    w = 1.0
            if w > 0:
                out[s.replace(".", "-")] = out.get(s.replace(".", "-"), 0.0) + w
    tot = sum(out.values())
    return {s: w / tot for s, w in out.items()} if tot > 0 else {}


def sr_save(name, text, today=None):
    name = (name or "").strip()[:80]
    if not name:
        return {"ok": False, "msg": "give the portfolio a name"}
    w = parse_list(text)
    if not w:
        return {"ok": False, "msg": "no tickers found — paste the Stock Rover export or one ticker per line"}
    if len(w) > 200:
        return {"ok": False, "msg": "more than 200 tickers"}
    today = today or _today()
    key = "SR_" + re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:40]
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO srlab_lanes VALUES (?,?,?,?)",
                  (key, name, datetime.now(timezone.utc).isoformat(timespec="seconds"), ""))
        c.execute("DELETE FROM srlab_targets WHERE lane=? AND known=?", (key, today))
        c.executemany("INSERT INTO srlab_targets VALUES (?,?,?,?)", [(key, today, s, x) for s, x in w.items()])
    _MEMO["key"] = None
    return {"ok": True, "key": key, "n": len(w), "known": today,
            "msg": f"{name}: {len(w)} stocks saved — tracked from the close of {today} (or the next trading day)"}


def sr_delete(key):
    with _db() as c:
        c.execute("DELETE FROM srlab_targets WHERE lane=?", (key,))
        n = c.execute("DELETE FROM srlab_lanes WHERE key=?", (key,)).rowcount
    _MEMO["key"] = None
    return {"ok": bool(n)}


def status():
    try:
        return summary("5Y")
    except Exception as e:
        return {"ok": False, "msg": str(e)[:200]}
