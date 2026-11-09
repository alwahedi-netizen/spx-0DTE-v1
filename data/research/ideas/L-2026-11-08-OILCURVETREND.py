"""L-2026-11-08-OILCURVETREND — lab original (RESEARCH.md §2b), designed 2026-11-08,
scripted 2026-11-09 from the queue (ledger row keeps its id).

VARIES: L-2026-11-07-CARRYPROXY (potential 4: USO only while its 63-day return
beats USL's; +5.5%/yr vs USO -11.4%, worst drop -45% vs -98%, confidence 97.7%,
held-out Sharpe 0.65 vs 0.09; failed only DSR / t>=3). The ledger row said "run
only if the proxy shows signal" — it did (potential 4, 4 of 4 neighbours beat
USO), so the gate is met.

INGREDIENTS:
  * CARRYPROXY: Boons & Porras Prado, "Basis-Momentum", JF 74(1) 2019
    (https://ideas.repec.org/a/bla/jfinan/v74y2019i1p239-279.html) — USO-minus-USL
    return is a price-only proxy for the change in oil's curve slope.
  * DD-2026-11-TREND (potential 5): 10-month SMA trend cuts crashes everywhere;
    Moskowitz-Ooi-Pedersen (JFE 2012) time-series momentum in commodities.

RATIONALE (written before any run): CARRYPROXY's worst drop (-45%) came from
holding USO while the front was outrunning the ladder in a FALLING market
(curve tightening during a price slide, e.g. late 2008 / 2018 Q4 rebounds that
failed). Price trend and curve shape are different information: trend = what
prices did, curve = what physical tightness says. Requiring both to agree keeps
the curve signal's carry edge and adds the trend's crash cut (theme 1 x carry).
The cost: fewer months in the market, so the t-stat may fall.

RULE (fixed before any run; exactly the ledger row's stated rule):
  at each month-end close i:
    trend_on = USO close > mean of the last 10 month-end USO closes (incl. this one)
    curve_on = USO 63-day return > USL 63-day return
    hold 100% USO next month if trend_on AND curve_on, else T-bills
  (fewer than 10 month-ends, or USL missing -> T-bills)
Benchmark: buy & hold USO (single-commodity rule: the honest yardstick is the
instrument it times, as for CARRYPROXY; DBC would mix in 20 other commodities).
Costs 5bp. Start 2007-03-01 so the 10-month SMA is ready when USL's first 63-day
window completes (~2008-03); USL lists 2007-12.
Variants (neighbours): SMA 8 and 12 months; curve window 42 and 126 days.
FAMILY "L-2026-11-07-CARRYPROXY" (lifetime 5 before this run) -> trials 5 + 5 = 10.
Diagnostic (no extra verdict, no extra trial): Sharpe before/after 2020-04-01,
when USO changed its roll method (as in CARRYPROXY).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SPLIT = "2020-04-01"
START = "2007-03-01"


def make(n_months=10, lb=63):
    st = {"w": {}, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = {}, []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        u, l = px["USO"], px["USL"]
        if u[i]:
            st["me"].append(u[i])
        me = st["me"]
        trend_on = len(me) >= n_months and me[-1] > sum(me[-n_months:]) / n_months
        curve_on = (i >= lb and u[i] and u[i - lb] and l[i] and l[i - lb]
                    and u[i] / u[i - lb] > l[i] / l[i - lb])
        st["w"] = {"USO": 1.0} if (trend_on and curve_on) else {}
        return st["w"]
    return weights


weights = make()


def split_report(fn, start=START):
    """Diagnostic only: Sharpe/CAGR of the rule and of USO before/after SPLIT."""
    dates, px = rb.prices(["USO", "USL"], start)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(fn, dates, px, rf, 5.0)
    bret = rb.bench_returns("USO", dates, px, rf)
    out = {}
    for name, sel in (("pre", lambda d: d < SPLIT), ("post", lambda d: d >= SPLIT)):
        idx = [k for k in range(len(rets)) if sel(dates[k + 1])]
        r, b, f = [rets[k] for k in idx], [bret[k] for k in idx], [rf[k + 1] for k in idx]
        out[name] = {"days": len(idx), "idea_sharpe": round(rb.sharpe(r, f), 3),
                     "uso_sharpe": round(rb.sharpe(b, f), 3),
                     "idea_cagr": round(rb.cagr(r), 4), "uso_cagr": round(rb.cagr(b), 4)}
    return out


if __name__ == "__main__":
    variants = {"SMA8": make(8, 63), "SMA12": make(12, 63),
                "lb42": make(10, 42), "lb126": make(10, 126)}
    res = rb.evaluate("L-2026-11-08-OILCURVETREND", weights, ["USO", "USL"], "USO", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=10,
                      family="L-2026-11-07-CARRYPROXY", variants=variants,
                      notes="month-end: USO next month only if USO > 10-month SMA AND USO 63d return > "
                            "USL 63d return, else T-bills; bench USO; varies L-2026-11-07-CARRYPROXY "
                            "(adds trend gate); lab original; vault sealed")
    res["split_diagnostic_2020_04"] = split_report(weights)
    print(json.dumps(res, indent=1))
