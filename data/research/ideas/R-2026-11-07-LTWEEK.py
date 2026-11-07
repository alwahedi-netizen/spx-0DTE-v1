"""R-2026-11-07-LTWEEK — Bitcoin one-week time-series momentum (Liu & Tsyvinski,
"Risks and Returns of Cryptocurrency", Review of Financial Studies 34(6), 2021;
NBER w24877: https://www.nber.org/system/files/working_papers/w24877/w24877.pdf).

Source finding: Bitcoin's weekly return predicts the next 1-4 weeks (a one-sd
rise in this week's return -> +3.16% next week); top-quintile formation weeks
earn 11.2%/week vs 2.6% for the bottom quintile, also out of sample with
cutoffs set on the first two years (their Table 17). Weekly = Sunday 23:59:59
UTC to the next Sunday, which is exactly Yahoo's BTC-USD daily bar.

Rationale: crypto has no cash-flow anchor, so prices are set by learning and
trend-chasing flows (the paper's attention channel; Schmeling-Schrimpf-
Todorov's trend-chasers) — news diffuses over weeks, so recent winners keep
winning. This is a SHORT-horizon (1-week) trend, a different clock from the
monthly 10-month SMA / 12-1 rules already measured in DD-2026-11-TREND.

RULE (fixed before any run):
  * Every Sunday close (UTC), compute BTC's 7-day return (this Sunday's close /
    last Sunday's close - 1).
  * If > 0: hold 100% BTC for the next 7 days; else T-bills.
  * Weight is held unchanged between Sundays. Cash before the first signal.
Benchmark = buy & hold BTC-USD. Costs 25bp per unit turnover (asset_class
crypto). Schwab: IBIT/FBTC spot ETFs or CME BTC/MBT futures (a Sunday UTC
close maps to Monday's open for the ETF — a timing gap the red team must
check; CME micro futures trade Sunday evening ET).
Variants (neighbouring settings): 14-, 21- and 28-day formation windows (the
paper's 1-4 week horizons), Wednesday instead of Sunday rebalancing
(day-of-week robustness), and an expanding-median cutoff instead of zero
(closer to the paper's quintile sort, no look-ahead).
trials: 1 + 5 variants + DD-2026-11-TREND's BTC 12-1 run (same family of BTC
time-series momentum) + 1 for the source's own choice among daily/weekly
horizons = 8."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(lookback=7, weekday=6, cutoff="zero"):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(w={}, hist=[])
        if i >= lookback and date.fromisoformat(dates[i]).weekday() == weekday:
            a, b = px[SYM][i - lookback], px[SYM][i]
            if a and b:
                r = b / a - 1
                cut = 0.0
                if cutoff == "median" and len(st["hist"]) >= 52:
                    h = sorted(st["hist"])
                    cut = h[len(h) // 2]
                st["w"] = {SYM: 1.0} if r > cut else {}
                st["hist"].append(r)
        return st["w"]
    return weights


weights = make()

VARIANTS = {
    "lookback14": make(lookback=14),
    "lookback21": make(lookback=21),
    "lookback28": make(lookback=28),
    "wednesday": make(weekday=2),
    "median_cutoff": make(cutoff="median"),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-07-LTWEEK", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=8, family="crypto-tsmom", variants=VARIANTS,
        notes="Liu-Tsyvinski weekly TSMOM: hold BTC next week iff last Sunday-to-Sunday return > 0, "
              "else T-bills; 25bp; variants 14/21/28-day, Wednesday, expanding-median cutoff"),
        indent=1))
