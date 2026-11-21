"""L-2026-11-21-TIPSSEAS — TIPS inflation-accrual seasonality (lab): own TIPS
in the months their principal accrues fastest, nominal Treasuries otherwise.
Scripts the bond desk's queued row I-2026-11-10-TIPSSEAS (same rule) as a
LAB test: its source (NISA TIPS primer 2021,
https://www.nisa.com/wp-content/uploads/2021/09/NISA_TIPS_Primer_2021-1-1.pdf)
describes the mechanism but publishes no backtest headline, so rule 1
(replicate a published result) cannot apply; the precondition below checks
the mechanism instead.

RATIONALE (written 2026-11-10, restated before any run): a TIPS bond's
principal is indexed to NON-seasonally-adjusted CPI-U with a ~3-month lag
(reference CPI on the 1st of month M = CPI of M-3, interpolated daily to
M-2), so the accrual earned in month M is CPI(M-2)/CPI(M-3) - 1. NSA CPI
rises fastest in January-May and is flat or falling in October-December,
so TIPS accrue most in March-July/August and least in December-February.
Nominal Treasuries accrue a smooth coupon. If real yields do not fully
offset the known seasonal (the primer says the market prices "most" of it;
long TIPS would need ~4bp of seasonal real-yield drift to offset it, and
breakeven quotes are not seasonally adjusted), holding TIP in the
high-accrual half-year and IEF in the low half beats holding IEF all year.
Expected size if unpriced: ~+0.15%/month over Mar-Aug, ~0.9%/yr active;
relative TIP-IEF volatility ~4%/yr, so t >= 3 is unlikely in 21 years —
this is a diversifier/learning test (the TIPS-vs-nominal seasonal is a new
driver in the book; INFLREG and CMDTRENDINFL switch on inflation TRENDS,
not the accrual calendar).
Counter-evidence logged before the run: the source's own "mostly priced"
remark; theme 4 (calendar effects decay); TIP's duration (~6.8y real) is
shorter than IEF's (~7.5y), so part of any result is a duration tilt.

PRECONDITION (no evaluate call; printed, gates the test): on PRE-SAMPLE
CPI data (1990-01 .. 2003-12, before TIP's history), the mean lagged NSA
accrual in Mar-Aug minus the mean in Sep-Feb must be >= 0.10% per month.
Otherwise the mechanism is absent and no trial is spent.
RULE (fixed before any run, as queued): weights at close i = TIP 1.0 if
bar i+1 falls in March..August, else IEF 1.0 (calendar only; 2 switches a
year). Benchmark: IEF buy & hold. Costs 3bp. Start 2004-01-01 (TIP listed
2003-12-05). Variants (4): windows Feb-Jul, Apr-Sep, Mar-Jun, Mar-Jul.
trials = 5 (new family L-2026-11-21-TIPSSEAS).
CONTROL (printed, not a test): TIP buy & hold and a static 50/50 TIP/IEF
through the same simulate(), so a duration/TIPS level effect is not
mistaken for the seasonal (theme 22).
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs IEF, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating IEF) AND a full-period
Sharpe above both controls. Learning criterion (shortlist only): positive
active return vs IEF in both halves.
DATA TIMING: the trading rule reads no data at all, only the calendar
month of the next bar; the weight decided at close i earns close i ->
close i+1. The CPI series is used only in the precondition, on months
before the test period (CPIAUCNS, FRED fredgraph.csv, default Python
user-agent, cached per day in data/research/cache/fred_<id>.json).
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-21-TIPSSEAS"
TIPS, NOM = "TIP", "IEF"
START = "2004-01-01"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
MAIN = (3, 4, 5, 6, 7, 8)


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


def precondition(lo="1990-01", hi="2003-12"):
    cpi = {d[:7]: x for d, x in fred("CPIAUCNS").items()}
    keys = sorted(cpi)
    idx = {k: n for n, k in enumerate(keys)}
    acc = {m: [] for m in range(1, 13)}
    for k in keys:
        if not (lo <= k <= hi):
            continue
        n = idx[k]
        if n < 3:
            continue
        acc[int(k[5:7])].append(cpi[keys[n - 2]] / cpi[keys[n - 3]] - 1)
    mean = {m: round(100 * sum(v) / len(v), 3) for m, v in acc.items() if v}
    hi_ = [x for m in MAIN for x in acc[m]]
    lo_ = [x for m in acc if m not in MAIN for x in acc[m]]
    gap = 100 * (sum(hi_) / len(hi_) - sum(lo_) / len(lo_))
    return {"period": f"{lo}..{hi}", "mean_accrual_pct_by_month_M": mean,
            "mar_aug_minus_sep_feb_pct_per_month": round(gap, 3), "passes": bool(gap >= 0.10)}


def make(months=MAIN):
    months = set(months)

    def weights(i, dates, px):
        if i + 1 >= len(dates):
            return {}
        sym = TIPS if int(dates[i + 1][5:7]) in months else NOM
        return {sym: 1.0} if px[sym][i] else {}
    return weights


weights = make()


def controls():
    dates, px = rb.prices([TIPS, NOM], START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    out = {}
    for name, w in (("tip_buy_hold", {TIPS: 1.0}), ("static_50_50", {TIPS: 0.5, NOM: 0.5})):
        r, _ = rb.simulate(lambda i, d, p, w=w: dict(w), dates, px, rf, 3.0)
        out[name] = {"cagr": round(rb.cagr(r), 4), "sharpe": round(rb.sharpe(r, rf[1:]), 3)}
    return out


if __name__ == "__main__":
    pre = precondition()
    print(json.dumps({"precondition": pre}, indent=1))
    if not pre["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "mechanism absent: pre-sample NSA CPI accrual seasonal "
                                    "below 0.10%/month (pre-registered)"}, indent=1))
        sys.exit(0)
    r = rb.evaluate(ID, weights, [TIPS, NOM], NOM, start=START,
                    asset_class="bonds", trials=5, family=ID,
                    variants={"FEB_JUL": make((2, 3, 4, 5, 6, 7)),
                              "APR_SEP": make((4, 5, 6, 7, 8, 9)),
                              "MAR_JUN": make((3, 4, 5, 6)),
                              "MAR_JUL": make((3, 4, 5, 6, 7))},
                    notes="TIP when the next bar is in Mar-Aug, else IEF; bench IEF; 2004+; lab: "
                          "TIPS NSA-CPI accrual seasonality (NISA primer mechanism); "
                          f"pre-sample accrual gap {pre['mar_aug_minus_sep_feb_pct_per_month']}%/mo")
    r["precondition"] = pre
    r["controls_not_tests"] = controls()
    print(json.dumps(r, indent=1))
