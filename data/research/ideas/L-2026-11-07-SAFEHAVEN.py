"""L-2026-11-07-SAFEHAVEN — safe-haven currencies switched on by the equity trend
(lab original, RESEARCH.md §2b: cross-asset conditioning on a shortlist block).

INGREDIENTS:
  * DD-2026-11-TREND (shortlist, potential 5): S&P 500 below its 10-month SMA
    marks the bear markets that trend protection avoids.
  * Ranaldo & Söderlind, "Safe Haven Currencies", Review of Finance 14(3),
    2010 (https://econpapers.repec.org/RePEc:oup:revfin:v:14:y:2010:i:3:p:385-407;
    SNB WP 2007-17): the yen and Swiss franc gain vs USD when US stocks fall
    and FX volatility rises — the mirror of carry-trade losses.

RATIONALE (written before any run): the lab's equity book needs a sleeve that
EARNS in equity bear markets rather than merely sitting in cash. Safe-haven
currencies are bid when carry trades unwind and risk is cut, which is exactly
when the 10-month SMA is off. Holding them ONLY in that state avoids their
long negative-carry drift in calm years. Expected failure: a bear market
driven by rising US rates (2022), when the yen fell with stocks.

RULE (fixed before any run, trials=1 + 4 neighbours):
  * At each month-end close: if SPY's close is below the average of its last
    10 month-end closes -> hold FXY 50% + FXF 50% next month; else T-bills.
  * Before 10 month-ends of SPY exist, or if FXY/FXF has no price: T-bills.
  * Variants: SMA of 8, 9, 11, 12 month-ends.
Instruments: CurrencyShares FXY (yen, 2007-02+) and FXF (franc, 2006-06+),
Schwab-tradeable; both are deposit-backed, so their prices include the
(near-zero/negative) foreign deposit rate — a realistic carry cost.
Benchmark T-bills (a hedge sleeve judged on its own Sharpe; the portfolio
fit vs the equity book is the real question — run portfolio.marginal).
asset_class="fx", 2006-05+ (SPY warm-up; positions from 2007).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

HAVENS = ["FXY", "FXF"]
SYMS = HAVENS + ["SPY"]


def make(n_months=10):
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []      # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if px["SPY"][i]:
                st["me"].append(px["SPY"][i])
            me = st["me"]
            off = len(me) >= n_months and me[-1] < sum(me[-n_months:]) / n_months
            st["w"] = ({h: 1.0 / len(HAVENS) for h in HAVENS}
                       if off and all(px[h][i] for h in HAVENS) else {})
        return st["w"] or {}
    return weights


weights = make(10)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-07-SAFEHAVEN", weights, SYMS, None, start="2006-05-01",
                    asset_class="fx", trials=1, family="L-fx-safehaven",
                    variants={"SMA8": make(8), "SMA9": make(9), "SMA11": make(11), "SMA12": make(12)},
                    notes="FXY+FXF 50/50 only when SPY < 10-month SMA, else T-bills; monthly; 2006-05+ "
                          "(positions from 2007); lab original (DD-TREND x Ranaldo-Soderlind)")
    print(json.dumps(r, indent=1))
