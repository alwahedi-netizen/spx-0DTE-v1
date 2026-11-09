"""L-2026-11-09-FOMCMOVE — short the dollar on FOMC days ONLY when Treasury
implied volatility (MOVE) is above its 1-year norm (lab original, RESEARCH.md
§2b: conditioning a shortlist block on the regime its own source names).

VARIES: R-2026-11-07-FOMCUSD (potential 3; FAIL: Sharpe 0.18, held-out -0.49)
— same event, same basket, same date handling (imported unchanged), plus one
condition.

INGREDIENTS:
  * Mueller, Tahbaz-Salehi & Vedolin, "Exchange Rates and Monetary Policy
    Uncertainty", Journal of Finance 72(3), 2017
    (https://researchonline.lse.ac.uk/id/eprint/77256): the short-USD basket's
    FOMC-day excess return INCREASES with monetary-policy uncertainty, and the
    uncertainty proxies have no effect on non-announcement days; they read the
    return as compensation for bearing policy risk.
  * ^MOVE (ICE BofA 1-month Treasury option implied vol, Yahoo 2002-11+) as
    the uncertainty proxy (MTV use Treasury/Eurodollar implied vols of this
    kind; MOVE itself is the lab's choice).

RATIONALE (written before any run): FOMCUSD averaged the premium over calm and
uncertain meetings. If the premium is pay for bearing policy uncertainty,
holding the basket only into meetings when that uncertainty is priced high
should keep most of the return and drop most of the noise (fewer, better
trades). FOMCUSD's held-out failure (2018-24) is the test: post-2018 meetings
include both very high (2022) and very low (2019-21 ZIRP) MOVE regimes.

RULE (fixed before any run):
  * Days: exactly R-2026-11-07-FOMCUSD's primary rule (long an equal-weight
    basket of the 9 G10 currencies vs USD over the scheduled FOMC decision-
    day bar, Yahoo UK-summer-time label shift corrected; else T-bills).
  * Condition, read at the close BEFORE the decision-day bar: MOVE_i = last
    ^MOVE value at or before i; hold only if MOVE_i > mean of the last N = 252
    available ^MOVE values (incl. MOVE_i). Fewer than N values -> no trade.
  * Variants (norm length +-25% / +-50%): N = 126, 189, 315, 378.
Benchmark: T-bills. asset_class="fx" (2bp). Spot pairs (a one-day hold earns
no meaningful interest either way). Start 2004-01 as FOMCUSD; the harness
trims prices to the start date, so the 252-value MOVE norm warms up in 2004
and trades begin ~2005-01 (N378: ~2005-07).
FAMILY "fx-fomc-dollar" (FOMCUSD 5) -> trials 10.
EXPECTED WEAKNESS (on the record): ~4 trades a year; t >= 3 is out of reach
alone — judge it by portfolio.marginal against the book (theme 11).
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "fomcusd", Path(__file__).resolve().parent / "R-2026-11-07-FOMCUSD.py")
_fu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fu)

MOVE = "^MOVE"
SYMS = _fu.SYMS + [MOVE]


def make(norm_days=252):
    base = _fu.make([0])                         # stateless: FOMC-day basket or {}
    st = {"mv": [], "upto": -1}

    def weights(i, dates, px):
        if i == 0:
            st["mv"], st["upto"] = [], -1        # evaluate() re-simulates: start clean
        v = px[MOVE][i]
        if v and st["upto"] < i:
            st["mv"].append(v)
            st["upto"] = i
        w = base(i, dates, px)
        if not w:
            return {}
        mv = st["mv"]
        if len(mv) < norm_days:
            return {}
        cur = mv[-1]
        return w if cur > sum(mv[-norm_days:]) / norm_days else {}
    return weights


weights = make(252)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-09-FOMCMOVE", weights, SYMS, None, start="2004-01-01",
                    asset_class="fx", trials=10, family="fx-fomc-dollar",
                    variants={"N126": make(126), "N189": make(189), "N315": make(315), "N378": make(378)},
                    notes="FOMCUSD decision-day G10 basket vs USD, held only when ^MOVE > its trailing "
                          "252-value mean (MTV JF 2017: premium rises with policy uncertainty); else T-bills")
    print(json.dumps(r, indent=1))
