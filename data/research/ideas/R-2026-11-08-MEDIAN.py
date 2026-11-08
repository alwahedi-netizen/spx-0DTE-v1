"""R-2026-11-08-MEDIAN — scripts the queued I-2026-11-07-MEDIAN (scored 71,
held by the 5-script cap on 2026-11-07).

SOURCE: "Duration Rotation in U.S. Treasury Fixed-Income ETFs: Evidence for
a 'Median' Strategy", FinTech (MDPI) 5(2):29, 2026,
https://www.mdpi.com/2674-1032/5/2/29 (full text 403 to the scan; rules from
the abstract, the review record and search summaries): six iShares Treasury
ETFs (SHV, SHY, IEI, IEF, TLH, TLT) ranked at the start of each half-year by
prior-period return into Winners / Median / Losers (two each); the MEDIAN
pair beat buy-and-hold (Bloomberg US Treasury TR) by ~162bp/yr 2007-2025
with lower drawdowns; walk-forward 2012-2025 picked Median in most periods;
winners were the WORST bucket.

RATIONALE: term-premium mean reversion across the curve — the maturity that
just won (rates moved hardest in its favour) tends to give some back, the
loser is the one the market is fleeing; the middle of the curve avoids both
extremes. Honest risk: "middle two" may simply be a duration-neutral copy of
IEI/IEF, which the 0.10 Sharpe-materiality gate will catch; the reviewer
criticised the in-sample choice of the semi-annual schedule.

RULE (fixed before any run):
  * Universe SHV, SHY, IEI, IEF, TLH, TLT.
  * On the first trading day of January and July (decided from closes up to
    the PREVIOUS close, i.e. the June/December month-end), rank by total
    return over the prior L = 6 month-ends (adjusted closes); hold ranks 3
    and 4 (of 6, highest return = rank 1) equally, bought at that close and
    left to drift for 6 months (weights reported as drifted, no interim
    rebalancing). Ties broken by ticker order.
  * Warm-up (until all six have L+1 month-end closes, i.e. Jan 2008): IEF.
Benchmark: IEF buy & hold (the class benchmark; the source used the
Bloomberg US Treasury TR index, for which GOVT only exists from 2012).
Costs 3bp. 2007-01+ (SHV/TLH inception 2007-01).
Variants (lookback neighbours, same schedule): L = 3, 4, 8, 9 months.
trials = 5 (I-2026-11-07-TSMOMXMAT, the winners leg, was never run).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-08-MEDIAN"
UNIV = ["SHV", "SHY", "IEI", "IEF", "TLH", "TLT"]
BENCH = "IEF"


def make(lookback=6, hold_ranks=(2, 3)):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], held=None, base=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
            return {BENCH: 1.0} if px[BENCH][0] else {}
        if dates[i][:7] != dates[i - 1][:7]:
            st["me"].append(i - 1)                 # previous day was a month-end
            if dates[i][5:7] in ("01", "07") and len(st["me"]) > lookback:
                j0, j1 = st["me"][-1 - lookback], st["me"][-1]
                rets = []
                for s in UNIV:
                    a, b = px[s][j0], px[s][j1]
                    if not (a and b and px[s][i]):
                        rets = None
                        break
                    rets.append((b / a - 1, s))
                if rets:
                    order = sorted(rets, key=lambda t: (-t[0], UNIV.index(t[1])))
                    st["held"] = [order[r][1] for r in hold_ranks]
                    st["base"] = {s: px[s][i] for s in st["held"]}
        if not st["held"]:
            return {BENCH: 1.0} if px[BENCH][i] else {}
        rel = {s: (px[s][i] / st["base"][s] if px[s][i] else 1.0) for s in st["held"]}
        tot = sum(rel.values())
        return {s: v / tot for s, v in rel.items()}
    return weights


weights = make(6)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, UNIV, BENCH, start="2007-01-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={f"L{m}": make(m) for m in (3, 4, 8, 9)},
                    notes="semi-annual (Jan/Jul): rank SHV/SHY/IEI/IEF/TLH/TLT by prior 6-month "
                          "return, hold ranks 3-4 equally, drift; bench IEF; 2007+; scripts "
                          "I-2026-11-07-MEDIAN")
    print(json.dumps(r, indent=1))
