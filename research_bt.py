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

WORLD-CLASS GATES (owner 2026-11-07: "match what world class is doing") — a
PASS must ALSO clear every one of these (PROMISING needs gate 1):
  1. Deflated Sharpe Ratio >= 0.95 (Bailey & Lopez de Prado 2014) on the
     active returns, deflated for `trials` — the more variants were tried,
     the higher the bar. Lucky-best-of-N cannot pass.
  2. t-stat of the active mean >= 3.0 (Harvey, Liu & Zhu 2016: the hurdle
     for a new factor after 300+ published ones).
  3. Double costs: still beats the benchmark's Sharpe at 2x `cost_bps`.
  4. Robustness: if `variants` (neighbouring parameter settings) are given,
     >= 70% of them must also beat the benchmark's Sharpe. Variants count
     toward `trials`.
  5. Factor alpha (stocks): regressed on Fama-French 5 factors + momentum
     (Ken French daily library), the alpha's t-stat must be >= 2.0 — a
     repackaged known factor is not new alpha.
A gate that cannot be computed (no factor data, too short) is reported as
"n/a" and does not block, but the email must say so.

ORIGINAL RESEARCH SAFEGUARDS (owner 2026-11-07: "why limit to what is
published — combine or do variations"):
  * VAULT: data from VAULT_FROM on is hidden from every development run.
    evaluate(..., vault=True) runs ONE final exam on the full history; each
    idea gets exactly one (logged in results/vault_log.json; a second
    attempt raises VaultUsedError). Lab-generated ideas need a vault PASS
    before they are proposed for paper.
  * AUTOMATIC TRIALS: every saved run adds 1 + len(variants) to its
    `family` (default: the idea id) in results/trials.json, and the Deflated
    Sharpe uses the family's lifetime count — combinations and variations
    raise their own bar; nothing can under-report it.

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
DSR_MIN, HLZ_T, FACTOR_T, ROBUST_SHARE = 0.95, 3.0, 2.0, 0.70
VAULT_FROM = "2024-11-01"     # the last ~2 years: sealed from development


class VaultUsedError(Exception):
    pass


def _jload(name, default):
    f = RESULTS / name
    return json.loads(f.read_text()) if f.exists() else default


def _jsave(name, obj):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / name).write_text(json.dumps(obj, indent=1, sort_keys=True))
# realistic one-way cost per unit of turnover, by asset class (bps)
COST_BPS = {"stocks": 5.0, "etf": 3.0, "bonds": 3.0, "fx": 2.0,
            "futures": 2.0, "commodities": 5.0, "crypto": 25.0}
FF_URLS = {
    "ff5": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip",
}
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


# ── Sharadar: survivorship-free prices + point-in-time fundamentals ──────────
# Connected 2026-11-07 (owner: Full History Bundle). The key is NEVER in code:
# in the research environment the network proxy injects the `x-api-key`
# header for api.sharadar.com; SHARADAR_API_KEY (env) is an optional local
# override. Delisted names keep their final ticker (SVB -> SIVBQ).

import hashlib as _hl
import os as _os
import urllib.parse as _up

SHARADAR = "https://api.sharadar.com/v1.0/data/"


def _sh_fetch(table, params):
    q = dict(params, format="json")
    req = urllib.request.Request(SHARADAR + table + "?" + _up.urlencode(q),
                                 headers={"User-Agent": "logicon-research"})
    k = _os.environ.get("SHARADAR_API_KEY")
    if k:
        req.add_header("x-api-key", k)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read()).get("data") or []


def sharadar(table, fetch=None, **params):
    """Rows of a Sharadar table (cached per day per query)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag = _hl.sha1(json.dumps([table, sorted(params.items())]).encode()).hexdigest()[:16]
    f = CACHE / f"sh_{table}_{tag}.json"
    if f.exists() and json.loads(f.read_text()).get("asof") == today:
        return json.loads(f.read_text())["rows"]
    rows = (fetch or _sh_fetch)(table, dict(params, limit=params.get("limit", 10000)))
    f.write_text(json.dumps({"asof": today, "rows": rows}))
    return rows


def sharadar_prices(tickers, start="1997-01-01", fetch=None):
    """Like prices(): adjusted closes (dividends + splits) on the union
    calendar, from Sharadar SEP — delisted tickers included."""
    raw = {}
    for t in tickers:
        rows = sharadar("stocks", fetch, ticker=t, fields="date,closeadj")
        raw[t] = {r["date"][:10]: r["closeadj"] for r in rows if r.get("closeadj")}
    dates = sorted({d for v in raw.values() for d in v if d >= start})
    return dates, {t: [raw[t].get(d) for d in dates] for t in tickers}


def sp500_history(fetch=None, first_year=1970, last_year=None):
    """Every S&P 500 membership row (snapshots + adds/removes), year by year
    (the API caps one call at 10,000 rows)."""
    last_year = last_year or datetime.now(timezone.utc).year
    rows = []
    for y in range(first_year, last_year + 1):
        rows += sharadar("sp500", fetch, **{"from": f"{y}-01-01", "to": f"{y}-12-31"})
    return rows


def sp500_members(asof, rows):
    """Point-in-time S&P 500 membership on `asof`: the latest snapshot
    ('historical'/'current') on or before it, then the adds/removes since."""
    snaps = sorted({r["date"][:10] for r in rows
                    if r["action"] in ("historical", "current") and r["date"][:10] <= asof})
    if not snaps:
        return set()
    base = snaps[-1]
    members = {r["ticker"] for r in rows
               if r["action"] in ("historical", "current") and r["date"][:10] == base}
    for r in sorted(rows, key=lambda r: r["date"]):
        d = r["date"][:10]
        if base < d <= asof:
            if r["action"] == "added":
                members.add(r["ticker"])
            elif r["action"] == "removed":
                members.discard(r["ticker"])
    return members


def fundamentals_pit(ticker, dimension="ARQ", fetch=None):
    """Point-in-time fundamentals: rows sorted by `date` (when the number
    became public). An idea at day D may only use rows with date <= D."""
    rows = sharadar("fundamentals", fetch, ticker=ticker, dimension=dimension)
    return sorted(rows, key=lambda r: r.get("date") or "")


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


# ── world-class statistics (2026-11-07) ─────────────────────────────────────
from statistics import NormalDist as _ND

_EULER = 0.5772156649015329


def _moments(x):
    n, m, sd = len(x), _mean(x), _sd(x)
    if n < 4 or not sd:
        return 0.0, 3.0
    skew = sum(((v - m) / sd) ** 3 for v in x) / n
    kurt = sum(((v - m) / sd) ** 4 for v in x) / n
    return skew, kurt


def deflated_sharpe(active, trials=1):
    """Bailey & Lopez de Prado (2014) DSR on per-period returns: the
    probability the true Sharpe exceeds the best Sharpe expected from
    `trials` skill-less tries, corrected for skew and fat tails."""
    n = len(active)
    sd = _sd(active)
    if n < 60 or not sd:
        return None
    sr = _mean(active) / sd
    skew, kurt = _moments(active)
    nd = _ND()
    t = max(1, int(trials))
    if t > 1:
        e_max = ((1 - _EULER) * nd.inv_cdf(1 - 1 / t)
                 + _EULER * nd.inv_cdf(1 - 1 / (t * math.e)))
        sr0 = math.sqrt(1 / (n - 1)) * e_max
    else:
        sr0 = 0.0
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return None
    return nd.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom))


def t_stat(x):
    sd = _sd(x)
    return _mean(x) / (sd / math.sqrt(len(x))) if sd and len(x) > 1 else 0.0


def _solve(a, b):
    """Gauss-Jordan solve a.x = b (small dense systems)."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-15:
            raise ValueError("singular")
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def ols(y, xs):
    """y = a + sum b_k x_k. Returns (coefs incl. intercept first, t-stats)."""
    n, k = len(y), len(xs) + 1
    X = [[1.0] + [x[i] for x in xs] for i in range(n)]
    xtx = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    xty = [sum(X[r][i] * y[r] for r in range(n)) for i in range(k)]
    beta = _solve(xtx, xty)
    resid = [y[r] - sum(beta[j] * X[r][j] for j in range(k)) for r in range(n)]
    s2 = sum(e * e for e in resid) / (n - k)
    inv = [_solve(xtx, [1.0 if i == j else 0.0 for i in range(k)]) for j in range(k)]
    se = [math.sqrt(max(s2 * inv[j][j], 0.0)) for j in range(k)]
    return beta, [b / e if e else 0.0 for b, e in zip(beta, se)]


def _ff_fetch(url):
    import io, zipfile
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    return z.read(z.namelist()[0]).decode("latin-1")


def ff_factors(fetch=None):
    """{YYYY-MM-DD: {Mkt-RF, SMB, HML, RMW, CMA, Mom}} daily decimals (cached)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    f = CACHE / "ff5mom.json"
    if f.exists() and json.loads(f.read_text()).get("asof") == today:
        return json.loads(f.read_text())["f"]
    fetch = fetch or _ff_fetch
    out = {}
    for key in ("ff5", "mom"):
        head = None
        for line in fetch(FF_URLS[key]).splitlines():
            cells = [c.strip() for c in line.split(",")]
            if not cells[0]:
                head = [c for c in cells[1:]]
                continue
            if head and cells[0].isdigit() and len(cells[0]) == 8:
                d = f"{cells[0][:4]}-{cells[0][4:6]}-{cells[0][6:]}"
                row = out.setdefault(d, {})
                for h, v in zip(head, cells[1:]):
                    try:
                        row[h.strip()] = float(v) / 100
                    except ValueError:
                        pass
            elif head and cells[0] and not cells[0].isdigit():
                head = None
    f.write_text(json.dumps({"asof": today, "f": out}))
    return out


def factor_alpha(rets, rf, dates, factors):
    """Annualised alpha + t-stat of the idea's excess returns on FF5+Mom."""
    names = ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom")
    y, cols = [], [[] for _ in names]
    for r, f, d in zip(rets, rf, dates):
        row = factors.get(d)
        if row and all(k in row for k in names):
            y.append(r - f)
            for c, k in zip(cols, names):
                c.append(row[k])
    if len(y) < 500:
        return None
    beta, ts = ols(y, cols)
    return {"alpha_ann": round(beta[0] * 252, 4), "alpha_t": round(ts[0], 2),
            "loadings": {k: round(b, 2) for k, b in zip(names, beta[1:])}, "days": len(y)}


# ── potential rating: what a FAILED idea can still teach (owner 2026-11-07) ──
# "Even if the idea fails today, qualify it as a shortlisted idea that has
# potential — combine it later into our own proprietary system." The verdict
# says whether an idea stands alone; the potential says whether it is a
# useful BUILDING BLOCK. Suggested automatically here; the run confirms it
# with a written reason in data/research/learnings.csv.

def _sh(x):
    sd = _sd(x)
    return _mean(x) / sd * math.sqrt(252) if sd and len(x) > 20 else 0.0


def _corr(a, b):
    ma, mb, sa, sb = _mean(a), _mean(b), _sd(a), _sd(b)
    if not sa or not sb or len(a) < 3:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / ((len(a) - 1) * sa * sb)


def traits(rets, bret, rf, bench_px=None):
    """Behaviour of an idea beyond its verdict: diversification, drawdown
    cut, regime split (benchmark above/below its 200-day average), early vs
    late half, best and worst 5-year stretch — plus a suggested potential."""
    active = [a - b for a, b in zip(rets, bret)]
    t = {"corr_to_bench": round(_corr(rets, bret), 2)}
    bdd, idd = max_dd(bret), max_dd(rets)
    t["dd_cut"] = round(1 - idd / bdd, 2) if bdd < 0 else None
    t["sharpe_ratio_vs_bench"] = round(sharpe(rets, rf) / sharpe(bret, rf), 2) if sharpe(bret, rf) > 0 else None
    h = len(active) // 2
    t["active_sharpe_first_half"] = round(_sh(active[:h]), 2)
    t["active_sharpe_second_half"] = round(_sh(active[h:]), 2)
    if bench_px and len(bench_px) >= len(rets) + 1:
        up, dn = [], []
        for i, a in enumerate(active):
            w = [p for p in bench_px[max(0, i - 199):i + 1] if p]
            if len(w) >= 150 and bench_px[i]:
                (up if bench_px[i] >= sum(w) / len(w) else dn).append(a)
        t["active_sharpe_bench_uptrend"] = round(_sh(up), 2) if len(up) > 250 else None
        t["active_sharpe_bench_downtrend"] = round(_sh(dn), 2) if len(dn) > 250 else None
    win = 252 * 5
    if len(active) > win + 252:
        rolls = [_sh(active[s:s + win]) for s in range(0, len(active) - win, 63)]
        t["best_5y_active_sharpe"], t["worst_5y_active_sharpe"] = round(max(rolls), 2), round(min(rolls), 2)
    blocks, score = [], 0
    regime = [v for k, v in t.items() if k.startswith(("active_sharpe_bench", "best_5y")) and v is not None]
    if any(v >= 0.5 for v in regime) or t["active_sharpe_first_half"] >= 0.5 or t["active_sharpe_second_half"] >= 0.5:
        blocks.append("conditional-edge"); score += 1
    bs, isr = sharpe(bret, rf), sharpe(rets, rf)
    keeps_quality = isr >= 0.8 * bs if bs > 0 else isr >= bs
    if t["dd_cut"] is not None and t["dd_cut"] >= 0.3 and keeps_quality:
        blocks.append("risk-reducer"); score += 1
    if abs(t["corr_to_bench"]) <= 0.3 and sharpe(rets, rf) > 0:
        blocks.append("diversifier"); score += 1
    if _sh(active) > 0:
        score += 1
    if t["active_sharpe_second_half"] > 0:
        score += 1
    t["building_blocks"] = blocks
    t["potential_suggested"] = score          # 0-5; the run confirms with a reason
    return t


# ── one call per idea ────────────────────────────────────────────────────────

def evaluate(idea_id, weights_fn, symbols, bench=None, start="2000-01-01",
             cost_bps=None, trials=1, notes="", fetch=None, save=True,
             asset_class=None, variants=None, factors=None, ff_fetch=None,
             family=None, vault=False, source="yahoo"):
    """Backtest one idea and write data/research/results/<idea_id>.json.
    asset_class sets the default cost (COST_BPS) and turns on the factor-alpha
    gate for "stocks"; variants = {name: weights_fn} neighbouring settings
    (robustness gate, counted in trials); factors = "ff5mom" forces/None
    leaves the factor gate to asset_class."""
    if cost_bps is None:
        cost_bps = COST_BPS.get(asset_class or "", 5.0)
    variants = variants or {}
    family = family or idea_id
    if vault:
        vlog = _jload("vault_log.json", {})
        if family in vlog:
            raise VaultUsedError(f"{family} already took its vault test on {vlog[family]}")
    fam = _jload("trials.json", {})
    trials = max(int(trials or 1), 1 + len(variants), fam.get(family, 0) + 1 + len(variants))
    syms = sorted(set(symbols) | ({bench} if bench else set()))
    if source == "sharadar":
        # stocks from Sharadar (survivorship-free); a fund/ETF benchmark
        # still comes from Yahoo and is aligned onto the stock calendar
        sd, spx = sharadar_prices([x for x in syms if x != bench], start, fetch)
        if bench:
            bd, bp = prices([bench], start)
            bmap = dict(zip(bd, bp[bench]))
            spx[bench] = [bmap.get(d) for d in sd]
        dates, px = sd, spx
    else:
        dates, px = prices(syms, start, fetch)
    if not vault:                              # development never sees the vault
        keep = sum(1 for d in dates if d < VAULT_FROM)
        dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
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
    # ── world-class gates ──
    active = [a - b for a, b in zip(rets, bret)]
    dsr = deflated_sharpe(active, trials)
    tval = t_stat(active)
    r2x, _ = simulate(weights_fn, dates, px, rf, cost_bps * 2)
    double_ok = sharpe(r2x, rf1) > full_b
    robust = None
    if variants:
        wins = 0
        for fn in variants.values():
            vr, _ = simulate(fn, dates, px, rf, cost_bps)
            wins += sharpe(vr, rf1) > full_b
        robust = wins / len(variants)
    fa = None
    if factors == "ff5mom" or (factors is None and asset_class == "stocks"):
        try:
            fa = factor_alpha(rets, rf1, dates[1:], ff_factors(ff_fetch))
        except Exception as e:  # noqa: BLE001 — reported, never blocks
            fa = {"error": str(e)[:120]}
    gates = {
        "deflated_sharpe": "n/a" if dsr is None else ("ok" if dsr >= DSR_MIN else "FAIL"),
        "t_stat_3": "ok" if tval >= HLZ_T else "FAIL",
        "double_costs": "ok" if double_ok else "FAIL",
        "robustness": "n/a" if robust is None else ("ok" if robust >= ROBUST_SHARE else "FAIL"),
        "factor_alpha": ("n/a" if not fa or "alpha_t" not in fa
                         else "ok" if fa["alpha_t"] >= FACTOR_T else "FAIL"),
    }
    if verdict == "PASS" and any(v == "FAIL" for v in gates.values()):
        verdict = "PROMISING" if gates["deflated_sharpe"] != "FAIL" else "FAIL"
    if verdict == "PROMISING" and gates["deflated_sharpe"] == "FAIL":
        verdict = "FAIL"
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
        "asset_class": asset_class,
        "deflated_sharpe": None if dsr is None else round(dsr, 4),
        "active_t": round(tval, 2),
        "sharpe_2x_costs": round(sharpe(r2x, rf1), 3),
        "robust_share": None if robust is None else round(robust, 2),
        "variants": len(variants),
        "factor_alpha": fa,
        "gates": gates,
        "traits": traits(rets, bret, rf1, px.get(bench) if bench else None),
        "data_source": source, "survivorship_free": source == "sharadar",
        "family": family, "vault": ("VAULT TEST (full history, one-time)" if vault
                                    else f"sealed from {VAULT_FROM}"),
    }
    if save and out["traits"].get("potential_suggested", 0) >= 3:
        # shortlist candidates keep their monthly returns for portfolio work
        import portfolio
        portfolio.save_series(idea_id, portfolio.monthly(dates[1:], rets),
                              {"verdict": verdict, "bench": bench or "T-bills", "family": family})
    if save:
        fam[family] = fam.get(family, 0) + 1 + len(variants)
        _jsave("trials.json", fam)
        if vault:
            vlog = _jload("vault_log.json", {})
            vlog[family] = out["run"]
            _jsave("vault_log.json", vlog)
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
