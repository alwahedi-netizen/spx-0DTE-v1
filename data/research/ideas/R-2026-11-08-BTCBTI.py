"""R-2026-11-08-BTCBTI — CoinDesk Bitcoin Trend Indicator (BTI) graded
exposure, as run live by the Global X Bitcoin Trend Strategy ETF (BTRN).

Sources:
  BTI methodology (CoinDesk Indices, now CF Benchmarks family):
    https://downloads.coindesk.com/cd3/CDI/Trend-Indicator-Methodology.pdf
  Allocation rule (Global X):
    https://www.globalxetfs.com/articles/product-research/introducing-the-global-x-bitcoin-trend-strategy-etf-btrn
No published backtest statistics (index provider + ETF issuer documents only).

Varies I-2026-11-07-BTCMARATIO (single short SMA, all-or-nothing, daily) and
R-2026-11-07-ZPBENS (9 breakout channels, vol-sized): four EXPONENTIAL
crossover pairs give a 5-step graded weight, rebalanced weekly with a 50%
turnover cap. Grading + cap is the issuer's answer to the cost problem that
killed LTWEEK (theme 5).

Rationale (written before any run): speed-diversified short/medium trend on
BTC (Man AHL / Monash: shorter lookbacks worked best in crypto) with partial
exposure in mixed states, so whipsaws cost a quarter of a switch, not a whole one.

RULE (fixed before any run; from the two documents):
  * Price x = BTC-USD daily close (the index uses 4 p.m. ET; Yahoo BTC-USD
    closes at 00:00 UTC — a stated difference).
  * For half-life h, lambda = 0.5^(1/h); MA_h,t = NF_h * sum_{k=0..179}
    (1-lambda) lambda^k x_{t-k}, NF_h = 1 / sum_{k=0..179} (1-lambda) lambda^k.
  * Pairs (short, long) half-lives: (1,5), (2.5,10), (5,20), (10,40) days.
    Component = +1 if MA_short >= MA_long else -1. BTI = mean of the 4 (-1..1).
  * Target weight = (BTI + 1) / 2 (BTI 1 -> 100% BTC, 0 -> 50%, -1 -> 0%).
  * Rebalance each Friday close (BTRN rebalances weekly; day not published);
    each rebalance moves at most 0.50 toward the target. Rest in T-bills.
  * Before 180 closes exist: T-bills.
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto).
Variants: Wednesday rebalance; no turnover cap; daily rebalance; half-lives
x1.5; half-lives x0.5.
trials: 1 + 5 variants = 6 (new family)."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"
WIN = 180
PAIRS = [(1, 5), (2.5, 10), (5, 20), (10, 40)]


def _ewma(xs, h):
    lam = 0.5 ** (1.0 / h)
    ws = [(1 - lam) * lam ** k for k in range(len(xs))]
    nf = 1.0 / sum(ws)
    return nf * sum(w * x for w, x in zip(ws, reversed(xs)))


def bti(xs, scale=1.0):
    comps = [1 if _ewma(xs, s * scale) >= _ewma(xs, l * scale) else -1 for s, l in PAIRS]
    return sum(comps) / len(comps)


def make(weekday=4, cap=0.50, daily=False, scale=1.0):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"] = 0.0
        d = date.fromisoformat(dates[i])
        if (daily or d.weekday() == weekday) and i >= WIN - 1:
            xs = px[SYM][i - WIN + 1:i + 1]
            if None not in xs:
                target = (bti(xs, scale) + 1) / 2
                step = target - st["w"]
                if cap is not None:
                    step = max(-cap, min(cap, step))
                st["w"] = st["w"] + step
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "wednesday": make(weekday=2),
    "no_cap": make(cap=None),
    "daily": make(daily=True),
    "halflife_x1.5": make(scale=1.5),
    "halflife_x0.5": make(scale=0.5),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-08-BTCBTI", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=6, family="btc-bti", variants=VARIANTS,
        notes="CoinDesk BTI (4 EWMA pairs, half-lives 1/5..10/40, 180-obs window) -> weight (BTI+1)/2, "
              "weekly Friday, 50% turnover cap (Global X BTRN rule); 25bp; vault sealed from 2024-11"),
        indent=1))
