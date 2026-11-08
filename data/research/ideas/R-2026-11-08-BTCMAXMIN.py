"""R-2026-11-08-BTCMAXMIN — Bitcoin at a local maximum (trend) or local minimum
(mean reversion): Padysak & Vojtko (Quantpedia 2022), revisited 2024.

Sources:
  https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/
  https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/
Published result (Gemini daily, 2015-11 -> 2022-02, gross of costs): MAX+MIN
combined 98.4%/yr at 47.8% vol, max drawdown -37.7% vs BTC -83.7% at 74.4% vol;
10-day lookback best in-sample; the 2024 revisit (out-of-sample 2022-02 ->
2024-08) says MAX held up across 10-50 days, MIN weakened. No costs modelled.

Varies R-2026-11-07-ZPBENS / P-CRYPTO TR30 (breakout): those enter on a
breakout and trail a stop for weeks; this re-decides EVERY day (hold only the
day after a fresh 10-day extreme) and adds a mean-reversion leg at 10-day lows.
The MIN leg is a different driver (reversal) from anything in the crypto ledger.

Rationale (written before any run): short-horizon herding/attention after new
highs (Liu-Tsyvinski's 1-week momentum is the peer-reviewed cousin) plus
liquidity-provision rebounds after local capitulation lows. Two mutually
exclusive states, so the book is in BTC only ~30-40% of days.

RULE (fixed before any run; the source's formulas are images, so the reading
below is ours and stated plainly):
  * At each daily UTC close i, MAX = close_i >= max(close_{i-9..i}) (today is
    the highest close of the last 10 incl. today); MIN = close_i <= min of the
    same 10 closes.
  * If MAX or MIN: hold 100% BTC from close i to close i+1; else T-bills.
  * Before 10 closes exist: T-bills.
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (asset_class crypto).
Variants (neighbours): lookback 15 / 20 / 30 days; MAX-only at 10 days.
trials: the source's published grid is 5 lookbacks x {MAX, MIN, combined} = 15;
we pass 15 (our 5 runs sit inside that grid).
Known caveat: daily re-decision = high turnover (expect 60-100 one-way units a
year x 25bp); IBIT trades only US hours, so a UTC-close daily rule needs CME
micro futures or accepts a timing gap."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(n=10, use_max=True, use_min=True):
    def weights(i, dates, px):
        # stateless: nothing to reset at i == 0
        if i < n - 1:
            return {}
        win = px[SYM][i - n + 1:i + 1]
        if None in win:
            return {}
        c = win[-1]
        hit = (use_max and c >= max(win)) or (use_min and c <= min(win))
        return {SYM: 1.0} if hit else {}
    return weights


weights = make()

VARIANTS = {
    "n15": make(n=15),
    "n20": make(n=20),
    "n30": make(n=30),
    "max_only10": make(use_min=False),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-08-BTCMAXMIN", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=15, family="btc-maxmin", variants=VARIANTS,
        notes="Padysak-Vojtko (Quantpedia 2022/2024): hold BTC next day iff close is the 10-day max "
              "or 10-day min (incl. today); else T-bills; 25bp; source gross of costs; vault sealed from 2024-11"),
        indent=1))
