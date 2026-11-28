"""R-2026-11-28-FFDEF — the default spread forecasts corporate-bond returns
(Fama & French, "Business conditions and expected returns on stocks and
bonds", JFE 25(1) 1989). Scripts the bond queue row I-2026-11-11-FFDEF
(same rule; promote that row's id/phase, no second row).

SOURCE: https://doi.org/10.1016/0304-405X(89)90095-0 (Fama-French 1989).
Published headline (1927-1987, Ibbotson-style bond portfolios): expected
excess returns on long-term bonds contain a risk premium tied to longer-term
business conditions; the default spread (Baa minus Aaa yield) tracks it and
forecasts excess bond returns POSITIVELY (high spread = poor conditions =
high expected return), and "the variation through time in this premium is
stronger for low-grade bonds than for high-grade bonds" (abstract).

WHY NOW (round 1 skipped it, 2026-11-14): no corporate-bond RETURN series
before 1985 is in our data. Unlock: monthly par-bond returns built from
Moody's Baa and Aaa yields (FRED BAA/AAA, 1919+), the same yield-to-return
method the league accepted for KKLSEAS's replication on FRED Treasuries.

STEP 1 — REPLICATION (no evaluate call; printed, then gates step 2).
Monthly Baa and Aaa long-bond returns from Moody's monthly yields:
r_m = y_{m-1}/12 - D*dy + 0.5*C*dy^2, D/C = modified duration/convexity of a
20-year semiannual par bond at y_{m-1} (Moody's long-term corporates are
20-30y bonds); excess over TB3MS_{m-1}/1200 (FRED 3-month bill, 1934+).
Regression: next-12-month excess return (sum of months m+1..m+12) on DEF at
month m-1 (BAA-AAA, percentage points), monthly overlapping, Newey-West
(18 lags) t. DEF is lagged one extra month because Moody's monthly yields
are MONTHLY AVERAGES: month m+1's return (avg m -> avg m+1) must not share
days with the predictor's averaging month. Sample: return months
1934-02..1987-12 (54 of the source's 61 years; bills start 1934).
REPLICATION PASSES (fixed before any run; sign and rough size, matched to
the source's own claims, theme 33) when the Baa slope is > 0 with NW t >=
1.5 AND the Baa slope exceeds the Aaa slope (premium stronger for low
grade). Otherwise "harness/data suspect": step 2 does not run, no trial.
Printed, not gated: the same regressions on 1988-01..2024-10 (post-
publication, development data only).

STEP 2 — ETF TEST (one evaluate call). HYPOTHESIS: when the default spread
is wider than its own 5-year norm, the credit premium is high, so holding
investment-grade corporates (LQD) instead of duration-similar Treasuries
(IEF) earns it; when spreads are tight, Treasuries lose little and avoid
spread-widening losses. LQD vs IEF isolates CREDIT (the term premium is held
in both states) — stricter than F-F's excess-over-bills headline, and the
right question after GPRS (NBER w35578: recent corporate excess returns
mostly reflect the term premium).
RULE (fixed before any run, as queued):
  * Decision on the first trading day of each month (held all month); at
    that close i: spread = DBAA - DAAA (FRED daily Moody's, pp), the latest
    value dated strictly before dates[i-1] (the previous trading day).
  * Norm = mean of the month-end spreads (last daily value of each month)
    of the WIN = 60 months before the previous month (all strictly before
    dates[i-1]).
  * spread > norm + THR (THR = 0) -> LQD 1.0, else IEF 1.0.
  * First, partial month of the sample (no previous trading day): cash.
Benchmark: AGG buy & hold (as queued). Costs 3bp. Start 2003-10-01 (AGG
listed 2003-09-29). Daily DBAA starts 1986-01, so the 60- and 120-month
norms exist from the start. Includes 2008, 2013, 2020, 2022.
Variants (4, as queued): WIN 36 and 120; HYG instead of LQD (LQD until HYG
lists, 2007-04); THR = +0.25pp.
trials = 10 floor: FFTERM's 5 (same paper, same "F-F business conditions
time credit" question, term spread instead of default spread) + this run's
5. Own family "R-2026-11-28-FFDEF".
Counter-evidence logged before any run: FFTERM FAIL (2026-11-11); theme 4
(published effects decay); a level rule buys widening spreads too early
(2008 Q3-Q4); GPRS (credit premium mostly term).
CONTROL (printed, not a test, no evaluate call): LQD and IEF buy & hold and
the share of months in LQD, through rb.simulate on the same dates.
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs AGG, held-out win, DSR >= 0.95 at the trial
count, t >= 3, double costs, >= 70% of the 4 neighbours beating AGG).
Learning criterion (shortlist, not a pass): Sharpe above BOTH LQD and IEF
buy & hold (the switch adds something beyond owning either).
DATA TIMING: the step-2 signal reads FRED daily Moody's yields dated
strictly before the previous trading day (Moody's daily values are public
the next morning; one extra day of margin) — never the trade day; the
weight decided at close i earns close i -> close i+1, held for the month.
Step-1 FRED monthly data is used only in the event study, never in the
trading rule. FRED fredgraph.csv, default Python user-agent, cached per day
in data/research/cache/fred_<id>.json (git-ignored).
"""
import bisect
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-28-FFDEF"
BENCH, CREDIT, TSY, HY = "AGG", "LQD", "IEF", "HYG"
START = "2003-10-01"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def fred(sid):
    """FRED series as {date: float}, cached per day (default urllib agent)."""
    f = rb.CACHE / f"fred_{sid}.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == today:
            return j["v"]
    rows = urllib.request.urlopen(FRED + sid, timeout=60).read().decode().strip().splitlines()[1:]
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": today, "v": v}))
    return v


# ── step 1: replication ──────────────────────────────────────────────────────

def par_dur_conv(y, n=40):
    """Modified duration and convexity of a semiannual par bond with n coupons at annual yield y."""
    h = y / 2
    cfs = [(k, y / 2 + (1 if k == n else 0)) for k in range(1, n + 1)]
    pv = [cf / (1 + h) ** k for k, cf in cfs]
    price = sum(pv)
    mac = sum((k / 2) * v for (k, _), v in zip(cfs, pv)) / price
    conv = sum(cf * (k / 2) * ((k + 1) / 2) / (1 + h) ** (k + 2) for k, cf in cfs) / price
    return mac / (1 + h), conv


def monthly(sid):
    """FRED monthly series as {YYYY-MM: value}."""
    return {d[:7]: x for d, x in fred(sid).items()}


def next_month(ym, k=1):
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def excess_returns(yld, tb):
    """{month b: par-bond excess return over month a=b-1}, yields in percent."""
    out = {}
    for a in sorted(yld):
        b = next_month(a)
        if b in yld and a in tb:
            y0, dy = yld[a] / 100, (yld[b] - yld[a]) / 100
            dm, cv = par_dur_conv(y0)
            out[b] = y0 / 12 - dm * dy + 0.5 * cv * dy * dy - tb[a] / 1200
    return out


def nw_slope(y, x, lags=18):
    """OLS y = a + b x; returns (b, Newey-West t of b, R^2)."""
    n = len(y)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((u - mx) * (v - my) for u, v in zip(x, y)) / sxx
    a = my - b * mx
    e = [v - a - b * u for u, v in zip(x, y)]
    z = [(u - mx) * ei for u, ei in zip(x, e)]
    s = sum(v * v for v in z)
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        s += 2 * w * sum(z[t] * z[t - L] for t in range(L, n))
    se = math.sqrt(s) / sxx
    sst = sum((v - my) ** 2 for v in y)
    return b, (b / se if se else 0.0), 1 - sum(v * v for v in e) / sst


def regress(lo, hi, baa, aaa, rb_, ra_):
    """Annual-horizon regressions for return months lo..hi (inclusive)."""
    out = {}
    for name, r in (("baa", rb_), ("aaa", ra_)):
        ys, xs = [], []
        m = next_month(lo, -1)          # first window starts at month m+1 = lo
        while next_month(m, 12) <= hi:
            win = [next_month(m, k) for k in range(1, 13)]
            p = next_month(m, -1)
            if all(w in r for w in win) and p in baa and p in aaa:
                ys.append(100 * sum(r[w] for w in win))
                xs.append(baa[p] - aaa[p])
            m = next_month(m)
        b, t, r2 = nw_slope(ys, xs)
        out[name] = {"slope_pct_per_pp": round(b, 3), "nw_t": round(t, 2),
                     "r2": round(r2, 3), "n": len(ys)}
    return out


def replication():
    baa, aaa, tb = monthly("BAA"), monthly("AAA"), monthly("TB3MS")
    rbaa, raaa = excess_returns(baa, tb), excess_returns(aaa, tb)
    src = regress("1934-02", "1987-12", baa, aaa, rbaa, raaa)
    post = regress("1988-01", "2024-10", baa, aaa, rbaa, raaa)
    ok = (src["baa"]["slope_pct_per_pp"] > 0 and src["baa"]["nw_t"] >= 1.5
          and src["baa"]["slope_pct_per_pp"] > src["aaa"]["slope_pct_per_pp"])
    return {"period": "return months 1934-02..1987-12, 12-month horizon, DEF(m-1)",
            "source_period": src, "post_publication_1988_2024_10_not_gated": post,
            "paper": "DEF forecasts excess bond returns positively; stronger for low grade",
            "passes": bool(ok)}


# ── step 2: ETF rule ─────────────────────────────────────────────────────────

_SPREAD = {}


def spread_series():
    """Sorted (dates, spreads in pp) of DBAA - DAAA, both printed."""
    if not _SPREAD:
        b, a = fred("DBAA"), fred("DAAA")
        ds = sorted(d for d in b if d in a)
        _SPREAD["d"] = ds
        _SPREAD["s"] = [b[d] - a[d] for d in ds]
        me = {}
        for d, s in zip(ds, _SPREAD["s"]):
            me[d[:7]] = s               # last value of the month wins
        _SPREAD["me"] = me
    return _SPREAD


def make(win=60, thr=0.0, credit=CREDIT):
    state = {}

    def decide(cutoff):
        sp = spread_series()
        k = bisect.bisect_left(sp["d"], cutoff)        # values dated < cutoff
        if k == 0:
            return None
        cur = sp["s"][k - 1]
        prev_m = cutoff[:7]                             # the previous trading day's month
        months = [m for m in sorted(sp["me"]) if m < prev_m][-win:]
        if len(months) < win:
            return None
        norm = sum(sp["me"][m] for m in months) / win
        return "C" if cur > norm + thr else "T"

    def weights(i, dates, px):
        m = dates[i][:7]
        if m not in state:
            # first bar of this month in the sample decides it; the first,
            # partial month of the sample has no previous bar -> cash
            state[m] = decide(dates[i - 1]) if i >= 1 and dates[i - 1][:7] != m else None
        s = state[m]
        if s is None:
            return {}
        if s == "C":
            sym = credit
            if credit == HY and not px[HY][i]:
                sym = CREDIT                            # LQD until HYG lists (2007-04)
        else:
            sym = TSY
        return {sym: 1.0} if px[sym][i] else {}
    return weights


weights = make()


def control():
    dates, px = rb.prices([CREDIT, TSY, BENCH], START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    out = {}
    for sym in (CREDIT, TSY):
        r, _ = rb.simulate(lambda i, d, p, s=sym: {s: 1.0}, dates, px, rf, 3.0)
        out[f"{sym}_buyhold"] = {"cagr": round(rb.cagr(r), 4), "sharpe": round(rb.sharpe(r, rf[1:]), 3),
                                 "maxdd": round(rb.max_dd(r), 4)}
    fn = make()
    held = {}
    for i in range(len(dates)):
        w = fn(i, dates, px)
        if w:
            held[dates[i][:7]] = next(iter(w))
    out["share_of_months_in_LQD"] = round(sum(1 for v in held.values() if v == CREDIT) / max(len(held), 1), 3)
    out["months"] = len(held)
    return out


if __name__ == "__main__":
    rep = replication()
    print(json.dumps({"replication": rep}, indent=1))
    if not rep["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "harness/data suspect: Fama-French 1989 default-spread "
                                    "prediction did not replicate on Moody's-yield par-bond "
                                    "returns 1934-1987 (pre-registered gate); no trial spent"},
                         indent=1))
        sys.exit(0)
    r = rb.evaluate(ID, weights, [CREDIT, TSY, HY], BENCH, start=START,
                    asset_class="bonds", trials=10, family=ID,
                    variants={"win36": make(win=36), "win120": make(win=120),
                              "hyg": make(credit=HY), "thr25": make(thr=0.25)},
                    notes="First trading day of the month: DBAA-DAAA (dated before the previous "
                          "trading day) above its 60-month-end mean -> LQD, else IEF; bench AGG; "
                          "2003-10+; Fama-French 1989 default spread; replication on Moody's-yield "
                          "par-bond returns 1934-1987 passed "
                          f"(Baa slope {rep['source_period']['baa']['slope_pct_per_pp']}, "
                          f"t {rep['source_period']['baa']['nw_t']})")
    r["replication"] = rep
    r["control_not_test"] = control()
    print(json.dumps(r, indent=1))
