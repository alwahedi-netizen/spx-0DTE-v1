"""L-2026-11-08-BTCHOP3 — original (RESEARCH.md §2b): HOPTREND's 1/3/12-month
trend votes applied to Bitcoin alone, monthly, graded exposure. Source: lab.

Ingredients (KNOWLEDGE.md shortlist): R-2026-11-07-HOPTREND (potential 4: the
1/3/12-month vote book, corr -0.08 to the rest) and DD-2026-11-TREND
(potential 5; BTC SMA10 +43%/yr vs +42% with far shallower drops). Lessons
used: R-2026-11-07-LTWEEK died on weekly turnover (theme 5), so the fast
horizon here is 1 MONTH, sampled monthly; Man AHL / Monash 2023 (crypto trend
works best at shorter lookbacks) is why a 1- and 3-month vote is added to the
12-month one DD-TREND already used.

Rationale (written before any run): BTC trends at several speeds; one slow
filter (SMA10) is late into and out of the 2018/2022 bears and the 2019/2023
recoveries. Three equal votes give exposure in thirds, so a single horizon
flipping costs a third of a switch (cost-aware grading, as BTRN does weekly).
Counter-hypothesis: the 1-month vote just adds noise and the 12-month vote
does all the work (then this collapses to DD-TREND's BTC result).

RULE (fixed before any run):
  * At each calendar month-end UTC close t: for h in {1, 3, 12} months,
    vote_h = 1 if close_t > close at the month-end h months earlier, else 0.
  * Weight = (vote_1 + vote_3 + vote_12) / 3 of BTC; T-bills rest; held until
    the next month-end.
  * Before 13 month-ends exist: T-bills.
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto).
Variants: horizons (1,3,6); (1,6,12); (2,4,12); 12-month vote only (=DD-TREND
MOM12 without the skip month); majority vote (all-in when >= 2 of 3).
trials: 1 + 5 variants + DD-2026-11-TREND's two BTC runs + I-2026-11-07-TSMOMETF
idea (unrun) = 8."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(horizons=(1, 3, 12), majority=False):
    st = {}
    hmax = max(horizons)

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(me=[], w=0.0)
        d = date.fromisoformat(dates[i])
        c = px[SYM][i]
        if (d + timedelta(days=1)).month != d.month and c:
            st["me"].append(c)
            if len(st["me"]) > hmax:
                votes = sum(1 for h in horizons if c > st["me"][-1 - h])
                if majority:
                    st["w"] = 1.0 if votes * 2 > len(horizons) else 0.0
                else:
                    st["w"] = votes / len(horizons)
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "h1_3_6": make(horizons=(1, 3, 6)),
    "h1_6_12": make(horizons=(1, 6, 12)),
    "h2_4_12": make(horizons=(2, 4, 12)),
    "h12_only": make(horizons=(12,)),
    "majority": make(majority=True),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-08-BTCHOP3", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=8, family="btc-multihorizon-trend", variants=VARIANTS,
        notes="lab original: HOPTREND 1/3/12-month votes on BTC, weight = votes/3, month-end; 25bp; "
              "tests speed diversification vs DD-TREND's single SMA10; vault sealed from 2024-11"),
        indent=1))
