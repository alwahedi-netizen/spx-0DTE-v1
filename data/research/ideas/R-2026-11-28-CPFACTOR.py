"""R-2026-11-28-CPFACTOR — the Cochrane-Piazzesi forward-rate factor times
Treasury duration (Cochrane & Piazzesi, "Bond Risk Premia", AER 95(1)
2005). Scripts I-2026-11-07-CPFACTOR (rejected 11-07 for lack of 1-5 year
zero-coupon yields; promote that row's id/phase, no second row).

SOURCE: https://www.johnhcochrane.com/s/cochrane_piazzesi_bond_risk_premia.pdf
Published headline (Fama-Bliss zeros, 1964-2003, monthly data, annual
holding period): ONE tent-shaped linear combination of the 1-year yield and
the 2-5 year one-year forwards forecasts the average one-year excess log
return of 2-5 year zeros with R^2 = 0.35 (Table 1; 0.32-0.37 per bond);
coefficients negative on the 1-year yield and the 5-year forward, positive
in the middle, peaking at the 3-year forward (approx. -2.14, 0.81, 3.00,
0.80, -2.08). Critique logged before any run: Hodrick & Tomunen (CFR 2021,
https://nowpublishers.com/article/Details/CFR-0107) and Thornton-Valente
(RFS 2012) find it fails RECURSIVE out-of-sample tests; smoothed curves
(GSW) are known to weaken the tent.

DATA UNLOCK: the Federal Reserve's Gurkaynak-Sack-Wright zero curve
(feds200628.csv, daily 1961-06+, SVENY01..05 continuously compounded zero
yields, %): https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
Cached per day in data/research/cache/fed_gsw_y1to5.json (git-ignored).

STEP 1 — REPLICATION (no evaluate call; printed, then gates step 2).
Month-end = the last GSW date of each month with all five yields. With
y(n) in %, log price p(n) = -n*y(n); forwards f(1) = y(1), f(n) = n*y(n) -
(n-1)*y(n-1); excess log return rx(n)_{t+12} = n*y(n)_t - (n-1)*y(n-1)_{t+12}
- y(1)_t (n = 2..5); target = mean over n. OLS of target on [1, f1..f5],
regressor months 1964-01..2002-12 (returns to 2003-12; the source's sample).
REPLICATION PASSES (fixed before any run; sign and rough size) when R^2 >=
0.175 (half the source's 0.35) AND the tent's signs hold: coefficient on
f1 < 0, on f3 > 0, on f5 < 0. Otherwise "harness/data suspect" (GSW
smoothing): step 2 does not run, no trial spent.
Printed, not gated: the recursive (expanding-window) out-of-sample R^2 vs
the expanding historical mean, forecasts 1985-01..2023-10 (returns realised
by 2024-10, development data only) — the critique's own test.

STEP 2 — ETF TEST (one evaluate call). HYPOTHESIS: if the CP factor
measures the bond risk premium in real time, owning intermediate Treasuries
only when its recursive forecast of the excess return is positive (T-bills
otherwise) beats holding IEF all the time on Sharpe.
RULE (fixed before any run):
  * Decision month m takes effect on the first trading day ON/AFTER the
    10th of m (weights at that close; held until the next decision). It
    uses only the GSW month-end curve of m-1 (dated <= the last business day
    of m-1, i.e. >= 10 calendar days old: the Fed posts the file with a lag).
  * gamma = OLS of the target on [1, f1..f5] over regressor months
    1964-01..(m-1 minus 12 months) (EXPANDING; only returns realised by the
    m-1 month-end). forecast = gamma . [1, f(m-1)].
  * forecast > 0 -> IEF 1.0, else T-bills (no position).
  * Before the first decision inside the sample, the decision of the month
    before applies (same rule, one month older curve).
Benchmark: IEF buy & hold. Costs 3bp. Start 2002-08-01 (IEF listed
2002-07-30). Includes 2008, 2013, 2020, 2022.
Variants (4): MEDIAN threshold (forecast > median of all earlier recursive
forecasts since 1984-01, not 0); ROLL240 (rolling 240-month estimation
window, not expanding); TLT instead of IEF; RX5 (forecast the 5-year bond's
own rx(5) with the same regressors, not the 2-5 average).
trials = 5 (new family R-2026-11-28-CPFACTOR; no earlier forward-rate run.
YCMOM, BONDCARRYX, CYCLEFAC are different signals in their own families).
Counter-evidence: the OOS critiques above; theme 4; CYCLEFAC FAIL (another
slope-type risk-premium signal, 2026-11-11).
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs IEF, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating IEF).
Learning criterion (shortlist, not a pass): printed recursive OOS R^2 > 0
AND Sharpe above IEF.
DATA TIMING: the signal at close i reads only GSW month-end curves at least
10 calendar days older than dates[i] and regression targets realised by
that curve's date — never the trade day or later; the weight decided at
close i earns close i -> close i+1. Caveat: the GSW file is today's vintage
(the Fed may re-fit history; revisions are rare and small).
"""
import bisect
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-28-CPFACTOR"
BENCH, LONG = "IEF", "TLT"
START = "2002-08-01"
GSW = "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"
FIRST = "1964-01"


def gsw_yields():
    """{date: [y1..y5]} GSW zero yields in %, cached per day."""
    f = rb.CACHE / "fed_gsw_y1to5.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == today:
            return j["v"]
    req = urllib.request.Request(GSW, headers={"User-Agent": "Mozilla/5.0"})
    lines = urllib.request.urlopen(req, timeout=180).read().decode("utf-8", "replace").splitlines()
    k = next(n for n, ln in enumerate(lines) if ln.startswith("Date,"))
    head = lines[k].split(",")
    cols = [head.index(f"SVENY0{n}") for n in range(1, 6)]
    v = {}
    for ln in lines[k + 1:]:
        p = ln.split(",")
        if len(p) < len(head) or len(p[0]) != 10:
            continue
        try:
            ys = [float(p[c]) for c in cols]
        except ValueError:
            continue                    # NA
        v[p[0]] = ys
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": today, "v": v}))
    return v


def next_month(ym, k=1):
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


_M = {}


def table():
    """Month-end curve table: months, last date, regressors x, targets rx (avg, rx5)."""
    if _M:
        return _M
    v = gsw_yields()
    me = {}
    for d in sorted(v):
        me[d[:7]] = (d, v[d])           # last complete date of the month wins
    months = sorted(me)
    x, date = {}, {}
    for m in months:
        d, y = me[m]
        date[m] = d
        x[m] = [1.0, y[0]] + [n * y[n - 1] - (n - 1) * y[n - 2] for n in range(2, 6)]
    rx_avg, rx5 = {}, {}
    for m in months:
        m12 = next_month(m, 12)
        if m12 in me:
            y0, y12 = me[m][1], me[m12][1]
            rx = [n * y0[n - 1] - (n - 1) * y12[n - 2] - y0[0] for n in range(2, 6)]
            rx_avg[m], rx5[m] = sum(rx) / 4, rx[3]
    _M.update(months=months, date=date, x=x, rx={"avg": rx_avg, "rx5": rx5})
    return _M


def fit(lo, hi, target="avg"):
    """OLS of the target on [1, f1..f5] for regressor months lo..hi with a realised target."""
    t = table()
    ms = [m for m in t["months"] if lo <= m <= hi and m in t["rx"][target]]
    ys = [t["rx"][target][m] for m in ms]
    xs = [[t["x"][m][j] for m in ms] for j in range(1, 6)]
    beta, _ = rb.ols(ys, xs)
    fitted = [sum(b * t["x"][m][j] for j, b in enumerate(beta)) for m in ms]
    my = sum(ys) / len(ys)
    r2 = 1 - sum((a - b) ** 2 for a, b in zip(ys, fitted)) / sum((a - my) ** 2 for a in ys)
    return beta, r2, len(ms)


_FC = {}


def forecast(m_curve, target="avg", roll=None):
    """Recursive forecast made with the month-end curve of m_curve (only realised targets)."""
    key = (m_curve, target, roll)
    if key not in _FC:
        t = table()
        hi = next_month(m_curve, -12)   # target of month hi is realised at m_curve's end
        lo = FIRST if roll is None else max(FIRST, next_month(hi, -(roll - 1)))
        beta, _, _ = fit(lo, hi, target)
        _FC[key] = sum(b * xv for b, xv in zip(beta, t["x"][m_curve]))
    return _FC[key]


def replication():
    beta, r2, n = fit(FIRST, "2002-12")
    names = ["const", "f1_y1", "f2", "f3", "f4", "f5"]
    ok = r2 >= 0.175 and beta[1] < 0 and beta[3] > 0 and beta[5] < 0
    # critique's test (printed, not gated): recursive OOS R^2 vs expanding mean
    t = table()
    num = den = 0.0
    m = "1985-01"
    while m <= "2023-10":
        if m in t["rx"]["avg"] and m in t["x"]:
            hist = [t["rx"]["avg"][k] for k in t["months"]
                    if FIRST <= k <= next_month(m, -12) and k in t["rx"]["avg"]]
            actual = t["rx"]["avg"][m]
            num += (actual - forecast(m)) ** 2
            den += (actual - sum(hist) / len(hist)) ** 2
        m = next_month(m)
    return {"period": "regressor months 1964-01..2002-12 (GSW zeros)", "n": n,
            "gamma": {k: round(b, 3) for k, b in zip(names, beta)}, "r2": round(r2, 3),
            "paper": "R2 0.35; gamma approx -2.14, 0.81, 3.00, 0.80, -2.08 (f1..f5)",
            "oos_r2_recursive_1985_2023_10_not_gated": round(1 - num / den, 3) if den else None,
            "passes": bool(ok)}


def decision_month(day):
    """Month whose decision governs bar `day`: from the 10th on, this month; before, the last."""
    return day[:7] if int(day[8:10]) >= 10 else next_month(day[:7], -1)


def make(sym=BENCH, target="avg", roll=None, median=False):
    t = {}

    def signal(m):
        if m not in t:
            curve = next_month(m, -1)
            tab = table()
            if curve not in tab["x"]:
                t[m] = False
            else:
                fc = forecast(curve, target, roll)
                if median:
                    past, k = [], "1984-01"
                    while k < curve:
                        if k in tab["x"]:
                            past.append(forecast(k, target, roll))
                        k = next_month(k)
                    past.sort()
                    thr = past[len(past) // 2] if past else 0.0
                else:
                    thr = 0.0
                t[m] = fc > thr
        return t[m]

    def weights(i, dates, px):
        return {sym: 1.0} if signal(decision_month(dates[i])) and px[sym][i] else {}
    return weights


weights = make()


if __name__ == "__main__":
    rep = replication()
    print(json.dumps({"replication": rep}, indent=1))
    if not rep["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "harness/data suspect: the Cochrane-Piazzesi factor did not "
                                    "replicate on GSW zeros 1964-2003 (pre-registered gate); "
                                    "no trial spent"}, indent=1))
        sys.exit(0)
    r = rb.evaluate(ID, weights, [BENCH, LONG], BENCH, start=START,
                    asset_class="bonds", trials=5, family=ID,
                    variants={"median": make(median=True), "roll240": make(roll=240),
                              "tlt": make(sym=LONG), "rx5": make(target="rx5")},
                    notes="From the 10th of each month: expanding-window Cochrane-Piazzesi "
                          "forecast (GSW 1-5y forwards, prior month-end curve, realised targets "
                          "only) > 0 -> IEF, else T-bills; bench IEF; 2002-08+; replication on "
                          f"GSW 1964-2003 passed (R2 {rep['r2']})")
    r["replication"] = rep
    print(json.dumps(r, indent=1))
