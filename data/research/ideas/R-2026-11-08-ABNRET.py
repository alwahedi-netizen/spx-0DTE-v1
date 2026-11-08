"""R-2026-11-08-ABNRET — step aside the day after a Bitcoin abnormal-return
day: Caporale & Plastun (2020), Financial Markets and Portfolio Management.

Source: "Momentum effects in the cryptocurrency market after one-day abnormal
returns", FMPM 34, 251-266 (2020), open access
  https://link.springer.com/10.1007/s11408-020-00357-1
  (working paper: https://www.brunel.ac.uk/economics-finance-and-accounting/research/pdf/1917-Oct-GMC-Momentum-effect-in-the-Cryptocurrency-Market-after-One-day-Abnormal-Returns.pdf)
Published (2015-01 -> 2019-09, hourly + daily, no costs): an abnormal day is
R_i > mean + k*sd (positive) or < mean - k*sd (negative), k = 2 for BTCUSD.
For BTC the NEXT day is weak after BOTH kinds: contrarian after positive
overreactions (sell at the open, 49 trades, 75% wins) and momentum after
negative ones (sell at the open). Both say: do not be long BTC the day after.

Varies nothing in the crypto ledger (first event-driven short-horizon rule);
cousin of I-2026-11-07-BTCCAL only in being a part-time-exposure rule.

Rationale (written before any run): overreaction days are liquidity events
(forced liquidations, leverage cascades); the following day carries the
unwind (reversal after melt-ups, continuation after liquidation cascades).
Being out ~6% of days costs little exposure if the effect is real.

RULE (fixed before any run):
  * Daily UTC close i: r_i = close_i / close_{i-1} - 1 (BTC trades 24/7, so
    close-to-close ~ the paper's open-to-close UTC day).
  * mean, sd = of the 365 daily returns ending at i-1 (the paper's averaging
    period n is not stated; we use a trailing year so it is point-in-time).
  * If |r_i - mean| > 2 * sd: T-bills from close i to close i+1. Else 100% BTC.
  * Before 366 closes: 100% BTC (benchmark-like warm-up).
  * Long-only simplification: the paper's trades are intraday shorts with
    11am / 4pm exits; we stand aside the whole next UTC day.
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto).
Variants: k = 1.5 / 2.5; window 180 / 730 days; positive-overreaction leg only.
trials: the paper chose k per coin from {1.5, 2} by sample size -> count 2, plus
1 + 5 variants = 8."""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(k=2.0, n=365, pos_only=False):
    def weights(i, dates, px):
        # stateless: nothing to reset at i == 0
        if i < n + 1:
            return {SYM: 1.0}
        cl = px[SYM][i - n - 1:i + 1]
        if None in cl:
            return {SYM: 1.0}
        r = [cl[j] / cl[j - 1] - 1 for j in range(1, len(cl))]
        hist, today = r[:-1], r[-1]
        m = sum(hist) / len(hist)
        sd = math.sqrt(sum((x - m) ** 2 for x in hist) / (len(hist) - 1))
        z = (today - m) / sd if sd > 0 else 0.0
        out = z > k if pos_only else abs(z) > k
        return {} if out else {SYM: 1.0}
    return weights


weights = make()

VARIANTS = {
    "k1.5": make(k=1.5),
    "k2.5": make(k=2.5),
    "n180": make(n=180),
    "n730": make(n=730),
    "positive_only": make(pos_only=True),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-08-ABNRET", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=8, family="btc-abnormal-day", variants=VARIANTS,
        notes="Caporale-Plastun FMPM 2020: T-bills the UTC day after a BTC return beyond mean +/- 2sd "
              "(trailing 365d), else 100% BTC; long-only daily simplification of intraday shorts; 25bp; "
              "vault sealed from 2024-11"),
        indent=1))
