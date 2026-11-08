"""L-2026-11-08-HAVENRATES — safe-haven currencies only in FALLING-YIELD equity
bear markets (lab original, RESEARCH.md §2b: variation of a shortlist block
that failed for a stated, fixable reason).

VARIES: L-2026-11-07-SAFEHAVEN (shortlist, potential 4; FAIL: Sharpe 0.10 vs 0,
held-out -0.09). Its learnings row: "works in risk-off bear markets with falling
US yields (2008, 2020); fails in rate-driven bear markets when the yen falls
with stocks (2022)". The fix adds exactly that condition, nothing else.

INGREDIENTS:
  * DD-2026-11-TREND (potential 5): SPY below its 10-month SMA = bear state.
  * Bond trend as the yield-direction gauge: IEF above its own 10-month SMA
    means intermediate yields are falling (same SMA rule, DD-TREND bonds leg).
  * Ranaldo & Soderlind, "Safe Haven Currencies", Review of Finance 2010
    (https://econpapers.repec.org/RePEc:oup:revfin:v:14:y:2010:i:3:p:385-407):
    JPY/CHF gain when US stocks fall AND US bond prices rise.

RATIONALE (written before any run): yen and franc are havens because carry
trades funded in them unwind in flight-to-quality episodes — which are also
the episodes when Treasuries rally. When stocks fall because US rates rise
(2022), the rate gap widens in the dollar's favour and the havens lose. The
bond-trend condition separates the two kinds of bear market.

RULE (fixed before any run):
  * At each month-end close: bear = SPY < mean of its last N month-end closes;
    rally = IEF > mean of its last N month-end closes. N = 10.
  * If bear AND rally -> FXY 50% + FXF 50% next month; else T-bills.
  * Before N month-ends exist, or if FXY/FXF has no price: T-bills.
  * Variants (same N on both legs): 8, 9, 11, 12.
Instruments: CurrencyShares FXY / FXF (deposit-backed, Schwab-tradeable), SPY,
IEF (signal only). Benchmark T-bills. asset_class="fx" (2bp). Start 2006-05.
FAMILY "L-fx-safehaven" (SAFEHAVEN ran 5) -> honest trials 10. Overfitting
note: the extra condition was chosen after seeing SAFEHAVEN's 2022 failure —
the shared family and the vault are the guard; judge by portfolio.marginal.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

HAVENS = ["FXY", "FXF"]
SYMS = HAVENS + ["SPY", "IEF"]


def make(n_months=10):
    st = {"w": None, "spy": [], "ief": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["spy"], st["ief"] = None, [], []   # evaluate() re-simulates
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if px["SPY"][i]:
                st["spy"].append(px["SPY"][i])
            if px["IEF"][i]:
                st["ief"].append(px["IEF"][i])
            s, b = st["spy"], st["ief"]
            bear = len(s) >= n_months and s[-1] < sum(s[-n_months:]) / n_months
            rally = len(b) >= n_months and b[-1] > sum(b[-n_months:]) / n_months
            st["w"] = ({h: 1.0 / len(HAVENS) for h in HAVENS}
                       if bear and rally and all(px[h][i] for h in HAVENS) else {})
        return st["w"] or {}
    return weights


weights = make(10)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-08-HAVENRATES", weights, SYMS, None, start="2006-05-01",
                    asset_class="fx", trials=10, family="L-fx-safehaven",
                    variants={"SMA8": make(8), "SMA9": make(9), "SMA11": make(11), "SMA12": make(12)},
                    notes="FXY+FXF 50/50 only when SPY < 10-mo SMA AND IEF > 10-mo SMA (falling-yield bear), "
                          "else T-bills; monthly; varies L-2026-11-07-SAFEHAVEN (fix for 2022)")
    print(json.dumps(r, indent=1))
