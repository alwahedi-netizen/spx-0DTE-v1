"""R-2026-11-09-BMP4 — four-signal bond timing (Baltussen, Martens & Penninga).

SOURCE: Baltussen, Martens & Penninga, "Predicting Bond Returns: 70 Years of
International Evidence", Financial Analysts Journal 77(3), 2021, pp. 133-155
(doi 10.1080/0015198X.2021.1908775 ;
https://ideas.repec.org/a/taf/ufajxx/v77y2021i3p133-155.html ; summary with
signal definitions: https://evidenceinvestor.com/post/how-predictable-are-government-bond-returns).
Six countries, 1949-2019: four signals — yield spread (10y yield minus cash
rate), bond trend (sign of the past 12-month bond return), past 12-month
equity excess return, past 12-month commodity return — each predicts bond
excess returns; the equal-weighted combination has Sharpe 0.87 (0.73 post-
1980, 0.58 last decade), 0.71 net of costs; signals correlate ~6%.

VARIES: R-2026-11-07-CTH (Newfound carry-trend-hedge, graveyard FAIL at 92%
confidence, Sharpe 0.56 vs 0.39): same carry/trend/equity-hedge logic PLUS
the commodity (inflation-pressure) signal and an equal-weight SCALED position
instead of a majority vote. The commodity leg is the piece CTH lacked in
2022, when commodities ripped and bonds crashed.

RATIONALE (written before any run): bond excess returns are predictable
from (1) carry — a steep curve pays a term premium; (2) trend — rate moves
persist; (3) equity strength — risk appetite and growth push yields up;
(4) commodity strength — inflation pressure pushes yields up. They are
nearly uncorrelated, so their average is a steadier signal than any one.

RULE (fixed before any run), long-only (Schwab-tradeable), no leverage:
  * On the first trading day of each month, from the PREVIOUS close (the
    month-end), with L = 12 month-ends of lookback:
      s1 carry  : ^TNX - ^IRX > 0 (upward-sloping 10y vs 3-month)  -> bull
      s2 trend  : IEF total return over L months > T-bill return     -> bull
      s3 equity : SPY total return over L months <= T-bill return    -> bull
      s4 commod : DBC return over L months <= 0                      -> bull
    T-bill return = compounded daily ^IRX/100/252 (last valid print).
  * Hold IEF at weight (number of bull signals)/4, rest T-bills; bought at
    that day's close; held for the month (re-set to target daily).
  * Warm-up (fewer than L+1 month-ends of all inputs): IEF 1.0 (= bench).
Benchmark: IEF buy & hold. Costs 3bp. 2006-02+ (DBC inception 2006-02-03;
positions from 2007-03 — includes 2008 and 2022).
Variants: L = 9 and 15 months (scaled); L = 12 with all-in rules
"IEF 1.0 if >= 3 of 4 bull else T-bills" and "IEF 1.0 if >= 2 of 4".
trials = 10: own 5 + CTH's 5 (same carry/trend/equity-hedge hypothesis).
Family: own id.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-09-BMP4"
TNX, IRX, BOND, EQ, CMD = "^TNX", "^IRX", "IEF", "SPY", "DBC"


def make(lookback=12, mode="scaled"):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], tnx=None, irx=None, cash=1.0, w=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        elif dates[i][:7] != dates[i - 1][:7]:         # month-end = close i-1
            b, e, c = px[BOND][i - 1], px[EQ][i - 1], px[CMD][i - 1]
            st["me"].append((st["tnx"], st["irx"], b, e, c, st["cash"]))
            m = st["me"]
            if len(m) > lookback:
                now, then = m[-1], m[-1 - lookback]
                if all(x is not None for x in now + then):
                    cash_r = now[5] / then[5] - 1
                    bull = ((now[0] - now[1] > 0) +
                            (now[2] / then[2] - 1 > cash_r) +
                            (now[3] / then[3] - 1 <= cash_r) +
                            (now[4] / then[4] - 1 <= 0))
                    if mode == "scaled":
                        st["w"] = bull / 4.0
                    else:
                        st["w"] = 1.0 if bull >= mode else 0.0
        # today's close updates the state used by LATER decisions
        if px[TNX][i] is not None:
            st["tnx"] = px[TNX][i]
        if i > 0 and st["irx"] is not None:           # cash accrues daily at the
            st["cash"] *= 1 + st["irx"] / 100 / 252    # last valid bill yield
        if px[IRX][i] is not None:
            st["irx"] = px[IRX][i]
        w = 1.0 if st["w"] is None else st["w"]
        return {BOND: w} if (w and px[BOND][i]) else {}
    return weights


weights = make(12, "scaled")

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [TNX, IRX, BOND, EQ, CMD], BOND, start="2006-02-01",
                    asset_class="bonds", trials=10, family=ID,
                    variants={"L9": make(9, "scaled"), "L15": make(15, "scaled"),
                              "ALL3of4": make(12, 3), "ALL2of4": make(12, 2)},
                    notes="month-start: IEF weight = share of 4 bull signals (10y-3m slope > 0; IEF "
                          "12m > T-bills; SPY 12m <= T-bills; DBC 12m <= 0), rest T-bills; bench "
                          "IEF; 2006+; Baltussen-Martens-Penninga FAJ 2021; varies CTH")
    print(json.dumps(r, indent=1))
