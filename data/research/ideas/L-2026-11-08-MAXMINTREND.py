"""L-2026-11-08-MAXMINTREND — original (RESEARCH.md §2b): Padysak-Vojtko's
Bitcoin MAX/MIN rule with the mean-reversion (10-day-low) leg taken ONLY
while BTC is in a long-term up-trend (last month-end close above its
10-month SMA). Designed 2026-11-08 (ledger row, rule fixed then); scripted
2026-11-09 on the lead's queue.

Ingredients: R-2026-11-08-BTCMAXMIN (FAIL: Sharpe 0.63 vs 0.92, held-out
−0.45, turnover ~86/yr) and DD-2026-11-TREND (shortlist potential 5). Source
of the MAX/MIN rule: https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/
and the 2024 revisit https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/
(MIN leg weakened out-of-sample 2022-24 — buying lows in a falling market).

PRE-REGISTERED EXPECTATION (written before any run, 2026-11-09): the ledger
row said "run only if the MIN leg's 2022-24 losses drive that FAIL". The
parent's MAX-only neighbour ALSO failed (robust share 0/4), and its turnover
alone costs ~20%/yr at 25bp, so the prior is weak: the trend gate removes the
bear-market MIN buys (the source's stated failure) and some turnover, but
not the MAX leg's daily switching. Run because the queue asked; a FAIL here
closes the btc-maxmin family for daily-cadence versions.

Rationale: buying capitulation lows is liquidity provision — paid in bull
regimes (dips get bought), punished in bears (lows lead to lower lows). The
regime gate is DD-TREND's monthly SMA10, a slow state the MIN leg cannot
whipsaw.

RULE (fixed 2026-11-08 in the ledger, before any run):
  * Month-end state: at each calendar month-end UTC close, trend ON if that
    close > mean of the last 10 month-end closes (incl. it). Before 10
    month-ends exist: trend OFF (MIN leg disabled).
  * Daily UTC close i: MAX = close_i >= max(last 10 closes incl. today);
    MIN = close_i <= min(same 10 closes).
  * Hold 100% BTC from close i to close i+1 if MAX, or if MIN AND trend ON;
    else T-bills.
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (asset_class crypto).
Variants: lookback 15 / 20 days; trend SMA 8 / 12 months.
trials: family btc-maxmin — the source's 15-setting grid (which contains
R-2026-11-08-BTCMAXMIN's 5 runs) + this run and its 4 variants = 20 (the
harness also floors it at the family's lifetime count)."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(n=10, sma_months=10):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(me=[], trend=False)
        d = date.fromisoformat(dates[i])
        c = px[SYM][i]
        if c and (d + timedelta(days=1)).month != d.month:
            st["me"].append(c)
            if len(st["me"]) >= sma_months:
                st["trend"] = c > sum(st["me"][-sma_months:]) / sma_months
        if i < n - 1:
            return {}
        win = px[SYM][i - n + 1:i + 1]
        if None in win:
            return {}
        hit_max = c >= max(win)
        hit_min = c <= min(win) and st["trend"]
        return {SYM: 1.0} if (hit_max or hit_min) else {}
    return weights


weights = make()

VARIANTS = {
    "n15": make(n=15),
    "n20": make(n=20),
    "sma8": make(sma_months=8),
    "sma12": make(sma_months=12),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-08-MAXMINTREND", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=20, family="btc-maxmin", variants=VARIANTS,
        notes="lab original: Padysak-Vojtko MAX (10-day high) always + MIN (10-day low) only when the last "
              "month-end close > 10-month SMA; 1-day hold; 25bp; prior weak (parent's MAX-only neighbour "
              "failed too); vault sealed from 2024-11"),
        indent=1))
