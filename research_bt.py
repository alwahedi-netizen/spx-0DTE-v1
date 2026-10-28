"""
research_bt.py — the one Phase-1 harness for the weekly research scan
=====================================================================
Every idea the weekly scan backtests goes through THIS file, so every verdict
in the research ledger means the same thing (RESEARCH.md §4). Stdlib only.

An idea is a function that, at each day's close, returns target weights:

    def weights(i, dates, px) -> {symbol: weight}

`px[sym][i]` is the adjusted close on `dates[i]` (None when missing). The
function can only read index <= i (reading ahead raises LookAheadError). The
weights decided at close i earn the move from close i to close i+1, charges `cost_bps` on every unit of turnover,
pays the T-bill rate on uninvested cash (1 - sum of |weights|, never negative),
and charges the T-bill rate on gross exposure above 1 (financing).

Verdict (RESEARCH.md §4):
  PASS       confidence >= 99% that the idea's Sharpe beats the benchmark's
             (Memmel-corrected Jobson-Korkie test), AND it beats the benchmark
             on Sharpe in the held-out last 30%, AND its net return > 0 there
  PROMISING  confidence >= 90% and the held-out Sharpe also beats the benchmark
  FAIL       anything else
Both PASS and PROMISING also need a full-period Sharpe at least 0.10 above the
benchmark's: the Jobson-Korkie test calls a near-copy of the benchmark with a
sliver of difference "significant", which is not an edge.

The benchmark is buy & hold of `bench` (or T-bill cash when bench is None, i.e.
a Sharpe-above-zero test). A trial-count note goes in every result: the scan
must report how many variants it ran, never just the best one.
"""

import json
import math
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE = BASE_DIR / "data" / "research" / "cache"
RESULTS = BASE_DIR / "data" / "research" / "results"
STRICT, LOOSE, OOS_FRAC = 0.99, 0.90, 0.30
MIN_SHARPE_GAIN = 0.10      # materiality: a near-copy of the benchmark is not an edge


# ── data ─────────────────────────────────────────────────────────────────────

def _fetch(sym):
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?period1=473385600&period2={int(time.time())}&interval=1d&events=div,split")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())["chart"]["result"][0]
    ts = res["timestamp"]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") \
        or res["indicators"]["quote"][0]["close"]
    return {datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"): a
            for t, a in zip(ts, adj) if a}


def prices(symbols, start="1990-01-01", fetch=None):
    """Adjusted closes on the union calendar of `symbols` (cached per day)."""
    fetch = fetch or _fetch
    CACHE.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = {}
    for s in symbols:
        f = CACHE / f"{s.replace('^', '_').replace('=', '_')}.json"
        if f.exists() and json.loads(f.read_text()).get("asof") == today:
            raw[s] = json.loads(f.read_text())["px"]
        else:
            raw[s] = fetch(s)
            f.write_text(json.dumps({"asof": today, "px": raw[s]}))
    dates = sorted({d for v in raw.values() for d in v if d >= start})
    return dates, {s: [raw[s].get(d) for d in dates] for s in symbols}


def tbill(dates, fetch=None):
    """Daily T-bill return per date (13-week ^IRX, carried forward)."""
    d2, p = prices(["^IRX"], "1985-01-01", fetch)
    irx = dict(zip(d2, p["^IRX"]))
    out, last = [], 0.0
    for d in dates:
        if irx.get(d) is not None:
            last = irx[d]
        out.append(last / 100 / 252)
    return out


# ── simulation ───────────────────────────────────────────────────────────────

class LookAheadError(Exception):
    pass


class _Past:
    """A price column the idea may read only up to today's index."""
    __slots__ = ("col", "clock")

    def __init__(self, col, clock):
        self.col, self.clock = col, clock

    def __len__(self):
        return self.clock[0] + 1

    def __getitem__(self, k):
        now = self.clock[0]
        if isinstance(k, slice):
            start, stop, step = k.indices(now + 1)
            return self.col[start:stop:step]
        if k < 0:
            k += now + 1
        if k > now or k < 0:
            raise LookAheadError(f"read index {k} on day {now}")
        return self.col[k]


def simulate(weights_fn, dates, px, rf, cost_bps=5.0):
    """Daily net returns of the idea. Weights decided at close i earn i -> i+1.
    The idea sees prices only up to index i (reading ahead raises)."""
    clock = [0]
    view = {s: _Past(c, clock) for s, c in px.items()}
    rets, turnover, held = [], 0.0, {}
    for i in range(len(dates) - 1):
        clock[0] = i
        new = {s: w for s, w in (weights_fn(i, dates, view) or {}).items() if w}
        t = sum(abs(new.get(s, 0) - held.get(s, 0)) for s in set(new) | set(held))
        turnover += t
        r = 0.0
        for s, w in new.items():
            a, b = px[s][i], px[s][i + 1]
            if a and b:
                r += w * (b / a - 1)
        gross = sum(abs(w) for w in new.values())
        r += max(0.0, 1 - gross) * rf[i + 1] - max(0.0, gross - 1) * rf[i + 1]
        r -= t * cost_bps / 1e4
        # holdings drift to close i+1 (the base the next decision trades from)
        held = {}
        for s, w in new.items():
            a, b = px[s][i], px[s][i + 1]
            held[s] = w * (b / a) / (1 + r) if (a and b and 1 + r) else w
        rets.append(r)
    return rets, turnover


def bench_returns(bench, dates, px, rf):
    if bench is None:
        return [rf[i + 1] for i in range(len(dates) - 1)]
    out = []
    for i in range(len(dates) - 1):
        a, b = px[bench][i], px[bench][i + 1]
        out.append(b / a - 1 if a and b else 0.0)
    return out


# ── statistics ───────────────────────────────────────────────────────────────

def _mean(x):
    return sum(x) / len(x) if x else 0.0


def _sd(x):
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else 0.0


def sharpe(rets, rf):
    ex = [r - f for r, f in zip(rets, rf)]
    sd = _sd(ex)
    return _mean(ex) / sd * math.sqrt(252) if sd else 0.0


def cagr(rets):
    eq = 1.0
    for r in rets:
        eq *= 1 + r
    yrs = len(rets) / 252
    return eq ** (1 / yrs) - 1 if yrs > 0 and eq > 0 else -1.0


def max_dd(rets):
    eq = peak = 1.0
    dd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    return dd


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def sharpe_confidence(a, b, rf):
    """P(Sharpe(a) > Sharpe(b)) — Memmel (2003) corrected Jobson-Korkie, on
    daily excess returns. When b is cash (identical to rf), it reduces to the
    t-test of a's mean excess return."""
    xa = [r - f for r, f in zip(a, rf)]
    xb = [r - f for r, f in zip(b, rf)]
    n = len(xa)
    sa, sb = _sd(xa), _sd(xb)
    if n < 30 or not sa:
        return 0.5
    if not sb:                                   # benchmark is cash
        return _phi(_mean(xa) / sa * math.sqrt(n))
    ma, mb = _mean(xa), _mean(xb)
    rho = sum((u - ma) * (v - mb) for u, v in zip(xa, xb)) / ((n - 1) * sa * sb)
    s1, s2 = ma / sa, mb / sb
    var = (2 - 2 * rho + 0.5 * (s1 ** 2 + s2 ** 2 - 2 * s1 * s2 * rho ** 2)) / n
    return _phi((s1 - s2) / math.sqrt(var)) if var > 0 else 0.5


# ── one call per idea ────────────────────────────────────────────────────────

def evaluate(idea_id, weights_fn, symbols, bench=None, start="2000-01-01",
             cost_bps=5.0, trials=1, notes="", fetch=None, save=True):
    """Backtest one idea and write data/research/results/<idea_id>.json."""
    syms = sorted(set(symbols) | ({bench} if bench else set()))
    dates, px = prices(syms, start, fetch)
    rf = tbill(dates, fetch)
    rets, turnover = simulate(weights_fn, dates, px, rf, cost_bps)
    bret = bench_returns(bench, dates, px, rf)
    rf1 = rf[1:]
    cut = int(len(rets) * (1 - OOS_FRAC))
    conf = sharpe_confidence(rets, bret, rf1)
    oos_s, oos_b = sharpe(rets[cut:], rf1[cut:]), sharpe(bret[cut:], rf1[cut:])
    full_s, full_b = sharpe(rets, rf1), sharpe(bret, rf1)
    material = full_s - full_b >= MIN_SHARPE_GAIN
    oos_ok = oos_s > oos_b and cagr(rets[cut:]) > 0 and material
    verdict = ("PASS" if conf >= STRICT and oos_ok else
               "PROMISING" if conf >= LOOSE and oos_ok else "FAIL")
    out = {
        "idea": idea_id, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": [dates[0], dates[-1]], "bench": bench or "T-bills",
        "cost_bps": cost_bps, "trials": trials, "notes": notes,
        "idea_cagr": round(cagr(rets), 4), "bench_cagr": round(cagr(bret), 4),
        "idea_sharpe": round(full_s, 3), "bench_sharpe": round(full_b, 3),
        "idea_maxdd": round(max_dd(rets), 4), "bench_maxdd": round(max_dd(bret), 4),
        "turnover_per_year": round(turnover / (len(rets) / 252), 2),
        "confidence": round(conf, 4),
        "oos_from": dates[cut + 1], "oos_idea_sharpe": round(oos_s, 3),
        "oos_bench_sharpe": round(oos_b, 3), "oos_idea_cagr": round(cagr(rets[cut:]), 4),
        "verdict": verdict,
    }
    if save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{idea_id}.json").write_text(json.dumps(out, indent=1))
    return out


# ── allocation track (owner 2026-10-28) ─────────────────────────────────────
# Buy-and-hold allocations (e.g. leveraged 55/45) trade a few times a year and
# can never reach 99% confidence on a lifetime of data, so they are judged on
# what the owner cares about: does it beat the benchmark over long holding
# periods? Rolling 10-year windows first; if those pass, 20-year windows.

# Revised 2026-10-28 by the owner after HFEA's first result (69.7% of 10-year
# windows vs a 70% bar): 20 years is the primary horizon for an allocation,
# 10 years is a "mostly beats it" sanity check. Applies to every idea from now.
ALLOC_WIN_SHARE = {10: 0.60, 20: 0.70}
ALLOC_MIN_WINDOWS = 12      # a horizon needs >= 12 monthly window starts


def rolling_windows(rets, bret, years, step=21):
    """CAGR of idea and benchmark over every `years`-long window (monthly steps)."""
    n = int(years * 252)
    out = []
    for s in range(0, len(rets) - n + 1, step):
        out.append((s, cagr(rets[s:s + n]), cagr(bret[s:s + n])))
    if len(rets) >= n and (not out or out[-1][0] != len(rets) - n):
        s = len(rets) - n                       # always include the latest window
        out.append((s, cagr(rets[s:]), cagr(bret[s:])))
    return out


def horizon_check(rets, bret, dates, years):
    w = rolling_windows(rets, bret, years)
    if len(w) < ALLOC_MIN_WINDOWS:
        return {"years": years, "windows": len(w), "status": "INSUFFICIENT"}
    ex = sorted(a - b for _, a, b in w)
    share = sum(1 for _, a, b in w if a > b) / len(w)
    s_last, a_last, b_last = w[-1]
    worst = min(w, key=lambda x: x[1])
    ok = share >= ALLOC_WIN_SHARE[years] and ex[len(ex) // 2] > 0 and a_last > b_last
    return {"years": years, "windows": len(w), "share_beating": round(share, 3),
            "median_excess_cagr": round(ex[len(ex) // 2], 4),
            "worst_window_excess_cagr": round(ex[0], 4),
            "latest_window": [dates[s_last + 1], dates[-1]],
            "latest_idea_cagr": round(a_last, 4), "latest_bench_cagr": round(b_last, 4),
            "worst_window_idea_cagr": round(worst[1], 4),
            "worst_window_start": dates[worst[0] + 1],
            "status": "PASS" if ok else "FAIL"}


def calendar_years(rets, bret, dates):
    yr = {}
    for i, d in enumerate(dates[1:]):
        a = yr.setdefault(d[:4], [1.0, 1.0])
        a[0] *= 1 + rets[i]
        a[1] *= 1 + bret[i]
    return {y: [round(a - 1, 4), round(b - 1, 4)] for y, (a, b) in sorted(yr.items())}


def evaluate_allocation(idea_id, weights_fn, symbols, bench, start="1986-01-01",
                        cost_bps=5.0, trials=1, notes="", fetch=None, save=True):
    """Allocation-track verdict: PASS when rolling 10-year AND 20-year windows
    both pass; PROMISING when 10-year passes but 20-year history is too short;
    FAIL otherwise. A window horizon passes when the idea beats the benchmark
    in enough windows, the median window beats it, and the latest window
    beats it. Window share bars: 60% for 10 years, 70% for 20 years
    (ALLOC_WIN_SHARE). The worst calendar year is reported for the owner."""
    syms = sorted(set(symbols) | {bench})
    dates, px = prices(syms, start, fetch)
    rf = tbill(dates, fetch)
    rets, turnover = simulate(weights_fn, dates, px, rf, cost_bps)
    bret = bench_returns(bench, dates, px, rf)
    h10 = horizon_check(rets, bret, dates, 10)
    h20 = horizon_check(rets, bret, dates, 20) if h10["status"] == "PASS" else \
        {"years": 20, "status": "NOT RUN (10-year failed)"}
    verdict = ("PASS" if h10["status"] == "PASS" and h20["status"] == "PASS" else
               "PROMISING" if h10["status"] == "PASS" and h20["status"] == "INSUFFICIENT" else
               "FAIL")
    years = calendar_years(rets, bret, dates)
    worst_y = min(years, key=lambda y: years[y][0])
    rf1 = rf[1:]
    out = {
        "idea": idea_id, "track": "allocation",
        "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": [dates[0], dates[-1]], "bench": bench, "cost_bps": cost_bps,
        "trials": trials, "notes": notes,
        "idea_cagr": round(cagr(rets), 4), "bench_cagr": round(cagr(bret), 4),
        "idea_sharpe": round(sharpe(rets, rf1), 3), "bench_sharpe": round(sharpe(bret, rf1), 3),
        "idea_maxdd": round(max_dd(rets), 4), "bench_maxdd": round(max_dd(bret), 4),
        "turnover_per_year": round(turnover / (len(rets) / 252), 2),
        "confidence": round(sharpe_confidence(rets, bret, rf1), 4),
        "years_beating_bench": f"{sum(1 for a, b in years.values() if a > b)}/{len(years)}",
        "worst_year": [worst_y] + years[worst_y],
        "h10": h10, "h20": h20, "calendar_years": years, "verdict": verdict,
    }
    cut = int(len(rets) * (1 - OOS_FRAC))
    out.update(oos_from=dates[cut + 1], oos_idea_sharpe=round(sharpe(rets[cut:], rf1[cut:]), 3),
               oos_bench_sharpe=round(sharpe(bret[cut:], rf1[cut:]), 3))
    if save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{idea_id}.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    # smoke run: 10-month SMA timing on SPY vs buy & hold (a known benchmark idea)
    def sma10(i, dates, px):
        c = [x for x in px["SPY"][max(0, i - 209):i + 1] if x]
        return {"SPY": 1.0} if len(c) >= 200 and c[-1] > sum(c) / len(c) else {}
    print(json.dumps(evaluate("SMOKE-SMA200", sma10, ["SPY"], "SPY", save=False), indent=1))
