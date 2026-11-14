"""R-2026-11-14-KKLSEAS — seasonal variation in Treasury returns: high in
the autumn (peak October), low in the spring (trough April) (Kamstra,
Kramer & Levi, "Seasonal Variation in Treasury Returns", Critical Finance
Review 4(1) 2015). Scripts I-2026-11-11-KKLSEAS.

SOURCE: https://nowpublishers.com/article/Details/CFR-0021 ; summary
https://cxoadvisory.com/calendar-effects/mirror-image-seasonality-for-stocks-and-treasuries
Published headline (1952-2004, mid/long-term US Treasury indexes): mean
monthly returns vary by OVER 80bp from peak (October) to trough (April);
the cycle survives White's reality check and is not explained by
auctions, FOMC, macro seasonals, risk, weather or sentiment; a seasonal
risk-aversion proxy explains > 60% of it. Opposite in phase to equities.

STEP 1 — REPLICATION (no evaluate call; printed, then gates step 2).
Our data cannot reach 1952 with returns; FRED DGS10 (daily, 1962+) gives
month-end 10-year yields, so the replication runs on the source's
1962-01..2004-12 sub-period (43 of its 53 years). Monthly 10-year par-bond
return from month-end yields: r_m = y_{m-1}/12 - D*dy + 0.5*C*dy^2 with
the par bond's modified duration D and convexity C at y_{m-1}
(semiannual coupons); excess over TB3MS_{m-1}/1200 (FRED 3-month bill,
monthly). REPLICATION PASSES (fixed before any run) when mean excess
(October) - mean excess (April) >= 0.40% (half the paper's 80bp) AND the
August-January months average more than the February-July months.
Otherwise: "harness/data suspect", step 2 does not run (no trial spent).

STEP 2 — ETF TEST (one evaluate call). HYPOTHESIS: if the seasonal is a
risk-premium cycle (risk aversion rising into winter raises Treasury
demand), holding intermediate Treasuries in the half-year around the peak
(August-January) and short Treasuries in the trough half (February-July)
beats holding IEF all year on Sharpe, at 2 switches a year.
RULE (fixed before any run): weights at close i = IEF 1.0 if bar i+1
falls in August..January, else SHY 1.0 (calendar only).
Benchmark: IEF buy & hold. Costs 3bp. Start 2002-08-01 (IEF/SHY 2002-07).
Variants (4): long windows July-December, September-February,
August-December, September-January (neighbouring onsets/lengths).
trials = 5 (new family R-2026-11-14-KKLSEAS; the seasonal Treasury ideas
JKTLTSEAS, STASUMMER, TLTSKIP7 were never run). Not the spent L-TSYCAL
family (that one trades 3-day month-end/FOMC windows; this holds IEF for
six whole months). Counter-evidence logged before the run: STASUMMER
(Stock Trader's Almanac) claims the OPPOSITE half-year for long bonds;
theme 4 (published calendar effects decay).
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs IEF, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating IEF).
DATA TIMING: the trading rule reads no data at all, only the calendar
month of the next bar (the exchange calendar is known in advance); the
weight decided at close i earns close i -> close i+1. The step-1 yields
are used only in the event study, never in the trading rule.
FRED fredgraph.csv, default Python user-agent, cached per day in
data/research/cache/fred_<id>.json (git-ignored).
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-14-KKLSEAS"
BENCH, SHORT = "IEF", "SHY"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
MAIN = (8, 9, 10, 11, 12, 1)


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


def par_dur_conv(y, n=20):
    """Modified duration and convexity of a 10-year semiannual par bond at annual yield y."""
    h = y / 2
    cfs = [(k, y / 2 + (1 if k == n else 0)) for k in range(1, n + 1)]
    pv = [cf / (1 + h) ** k for k, cf in cfs]
    price = sum(pv)
    mac = sum((k / 2) * v for (k, _), v in zip(cfs, pv)) / price
    dmod = mac / (1 + h)
    conv = sum(cf * (k / 2) * ((k + 1) / 2) / (1 + h) ** (k + 2) for k, cf in cfs) / price
    return dmod, conv


def monthly_excess(lo="1962-01", hi="2004-12"):
    y = fred("DGS10")
    tb = {d[:7]: x for d, x in fred("TB3MS").items()}
    me = {}
    for d in sorted(y):
        me[d[:7]] = y[d] / 100          # last valid value of the month wins
    yms = sorted(me)
    out = []
    for a, b in zip(yms, yms[1:]):
        if not (lo <= b <= hi) or a not in tb:
            continue
        y0, dy = me[a], me[b] - me[a]
        dm, cv = par_dur_conv(y0)
        r = y0 / 12 - dm * dy + 0.5 * cv * dy * dy
        out.append((int(b[5:7]), r - tb[a] / 1200))
    return out


def replication():
    xs = monthly_excess()
    by = {m: [r for mm, r in xs if mm == m] for m in range(1, 13)}
    mean = {m: round(100 * sum(v) / len(v), 3) for m, v in by.items() if v}
    hi = [r for m, r in xs if m in MAIN]
    lo = [r for m, r in xs if m not in MAIN]
    spread = mean[10] - mean[4]
    half = 100 * (sum(hi) / len(hi) - sum(lo) / len(lo))
    return {"period": "1962-01..2004-12", "months": len(xs),
            "mean_excess_pct_by_month": mean, "oct_minus_apr_pct": round(spread, 3),
            "aug_jan_minus_feb_jul_pct_per_month": round(half, 3),
            "paper": "Oct-Apr > 0.80% (1952-2004)",
            "passes": bool(spread >= 0.40 and half > 0)}


def make(months=MAIN):
    months = set(months)

    def weights(i, dates, px):
        if i + 1 >= len(dates):
            return {}
        sym = BENCH if int(dates[i + 1][5:7]) in months else SHORT
        return {sym: 1.0} if px[sym][i] else {}
    return weights


weights = make()

if __name__ == "__main__":
    rep = replication()
    print(json.dumps({"replication": rep}, indent=1))
    if not rep["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "harness/data suspect: the KKL seasonal did not replicate on "
                                    "FRED 10-year returns 1962-2004 (pre-registered gate)"}, indent=1))
        sys.exit(0)
    r = rb.evaluate(ID, weights, [BENCH, SHORT], BENCH, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"JUL_DEC": make((7, 8, 9, 10, 11, 12)),
                              "SEP_FEB": make((9, 10, 11, 12, 1, 2)),
                              "AUG_DEC": make((8, 9, 10, 11, 12)),
                              "SEP_JAN": make((9, 10, 11, 12, 1))},
                    notes="IEF when the next bar is in Aug-Jan, else SHY; bench IEF; 2002-08+; "
                          "Kamstra-Kramer-Levi CFR 2015 Treasury seasonal; replication on FRED "
                          f"1962-2004 passed (Oct-Apr {rep['oct_minus_apr_pct']}%)")
    r["replication"] = rep
    print(json.dumps(r, indent=1))
