"""R-2026-11-08-FEDCMD — commodities only in restrictive monetary-policy regimes.
Source: Jensen, Johnson & Mercer, "Efficient use of commodity futures in
diversified portfolios", Journal of Futures Markets 20(5), 2000
(https://ideas.repec.org/a/wly/jfutmk/v20y2000i5p489-506.html): commodity
futures earn high returns and deserve large weights when Fed policy is
restrictive, and little or none when it is expansive. Follow-ups by the same
group (Conover-Jensen-Johnson-Mercer; FAJ 2005 "Is Fed Policy Still Relevant
for Investors?", https://ideas.repec.org/a/taf/ufajxx/v61y2005i1p70-79.html)
confirm the regime split over 38 years; the effect is modest (~2.4%/yr).
Critique to watch: EFMA 2011 (https://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2011-Braga/papers/0169.pdf)
— the rule ignores the business-cycle stage.

VARIES nothing in the ledger (first monetary-policy-regime commodity rule; the
inflation-regime row L-2026-11-07-CMDTRENDINFL uses breakevens, a different
observable — rate direction is policy, breakevens are market inflation pricing).

Rationale: the Fed tightens late in the cycle when demand is strong and
inventories are low (backwardation: positive roll and spot premium); it eases
in slowdowns/crises when commodity demand collapses (2001, 2008, 2020).

RULE (fixed before any run). The papers classify by the direction of the most
recent Fed discount-rate change; we use the market's 13-week T-bill yield
(^IRX) as the free daily proxy, in quarter-point steps:
  at each month-end close i:
    chg = ^IRX[i] - ^IRX[i - 126]   (6-month change, percentage points)
    if chg >= +0.25: state = restrictive
    elif chg <= -0.25: state = expansive
    else: state unchanged (first state: restrictive iff chg > 0)
  hold 100% DBC next month if restrictive, else T-bills.
Benchmark: buy & hold DBC. Costs 5bp/unit turnover. History 2006-02 (DBC)
to the vault: includes the 2006 hikes, 2008 easing crash, 2015-19 and 2022-23
hiking cycles. Expectation stated before the run: only ~8-10 regime changes in
18 years, so t >= 3 is unlikely; the question is crash-avoidance + Sharpe.
Variants: lookback 63 / 252 days; step 0.10 / 0.50 pp. trials = 5.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb


def make(lb=126, step=0.25):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        y = px["^IRX"]
        if i >= lb and y[i] is not None and y[i - lb] is not None:
            chg = y[i] - y[i - lb]
            if chg >= step:
                st["state"] = "restrictive"
            elif chg <= -step:
                st["state"] = "expansive"
            elif "state" not in st:
                st["state"] = "restrictive" if chg > 0 else "expansive"
        st["w"] = {"DBC": 1.0} if st.get("state") == "restrictive" else {}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb63": make(63), "lb252": make(252), "step0.10": make(126, 0.10),
                "step0.50": make(126, 0.50)}
    res = rb.evaluate("R-2026-11-08-FEDCMD", weights, ["DBC", "^IRX"], "DBC", start="2005-06-01",
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="fed-policy-cmd", variants=variants,
                      notes="month-end: DBC next month while the Fed regime is restrictive (^IRX 6-month change "
                            ">= +0.25pp sets it, <= -0.25pp ends it), else T-bills; bench DBC; "
                            "Jensen-Johnson-Mercer 2000 with a T-bill-yield proxy for the discount rate")
    print(json.dumps(res, indent=1))
