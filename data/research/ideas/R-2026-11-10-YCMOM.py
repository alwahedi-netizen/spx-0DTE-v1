"""R-2026-11-10-YCMOM — yield-curve momentum: last month's Treasury excess
return decides next month's duration (Sihvonen, Review of Finance 2024).

SOURCE: Markus Sihvonen, "Yield Curve Momentum", Review of Finance 28(3),
May 2024, pp. 805-830 (https://econpapers.repec.org/RePEc:oup:revfin:v:28:y:2024:i:3:p:805-830 ;
author summary https://cepr.org/voxeu/columns/yield-curve-momentum-implications-theory-and-practice ;
Bank of Finland WP https://publications.bof.fi/handle/10024/48148).
Finding (1971-2019): the past MONTH's Treasury excess return predicts the
next month's, across maturities, strongest at short-to-intermediate
maturities. Returns after months with negative excess returns are close
to zero, so nearly all of the total bond excess return is earned in months
that follow a positive month. The effect does not last beyond one month.
Part of it is FOMC post-meeting drift. It holds after controlling for
current yields, so it is not carry/value in disguise.

RATIONALE (written before any run): level shocks (mostly policy news)
are absorbed slowly. Agents with complexity limits extrapolate only
short-term dependence (the author's model), so a rates move keeps going
for about a month. The rule owns duration only in the months after a
positive excess month, which should keep most of the bond premium while
holding IEF about 55-60% of the time. It is different from the ledger's
trend rules: DD-2026-11-TREND (10-mo SMA / 12-1) and TSMOMXMAT (best
maturity) use 6-12 month lookbacks that the paper finds carry no extra
signal; here the lookback is ONE month.

RULE (fixed before any run):
  * On the first trading day of each month, from the PREVIOUS close (the
    month-end): IEF's total return over the last month (month-end to
    month-end) minus the T-bill return over the same month (compounded
    daily from the last valid ^IRX print, /100/252). If that excess > 0,
    hold IEF for the month, else T-bills. Bought at that day's close.
  * Warm-up (fewer than 2 month-ends): IEF 1.0 (= bench).
Benchmark: IEF buy & hold. Costs 3bp. 2002-08+ (IEF inception 2002-07-30;
includes 2008, 2013, 2022).
Variants: lookback 2 and 3 months (the paper: no signal beyond 1, so these
should be weaker); raw IEF return > 0 (no T-bill hurdle); excess > +10bp.
trials = 5 (new family; the 12-month bond trend in DD-2026-11-TREND tests
a different horizon the paper rules out).
Check after the run: correlation with L-2026-11-08-TSYCAL (post-FOMC drift
overlap) and portfolio.marginal vs the shortlist book.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-10-YCMOM"
IRX, BOND = "^IRX", "IEF"


def make(lookback=1, hurdle="tbill", thr=0.0):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], irx=None, cash=1.0, w=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        elif dates[i][:7] != dates[i - 1][:7]:          # month-end = close i-1
            st["me"].append((px[BOND][i - 1], st["cash"]))
            m = st["me"]
            if len(m) > lookback:
                (b1, c1), (b0, c0) = m[-1], m[-1 - lookback]
                if b1 and b0:
                    ex = b1 / b0 - 1 - ((c1 / c0 - 1) if hurdle == "tbill" else 0.0)
                    st["w"] = 1.0 if ex > thr else 0.0
        # today's close feeds LATER decisions only
        if i > 0 and st["irx"] is not None:
            st["cash"] *= 1 + st["irx"] / 100 / 252
        if px[IRX][i] is not None:
            st["irx"] = px[IRX][i]
        w = 1.0 if st["w"] is None else st["w"]
        return {BOND: w} if (w and px[BOND][i]) else {}
    return weights


weights = make(1)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [IRX, BOND], BOND, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"LB2": make(2), "LB3": make(3),
                              "RAW0": make(1, "raw"), "THR10": make(1, "tbill", 0.001)},
                    notes="month-start: IEF if last month's IEF excess return over T-bills > 0, "
                          "else T-bills; bench IEF; 2002-08+; Sihvonen RoF 2024 yield-curve momentum")
    print(json.dumps(r, indent=1))
