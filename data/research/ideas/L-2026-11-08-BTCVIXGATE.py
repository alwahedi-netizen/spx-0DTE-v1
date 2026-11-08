"""L-2026-11-08-BTCVIXGATE — original (RESEARCH.md §2b): step out of Bitcoin
during equity fear spikes (VIX well above its own recent mean). Source: lab.

Ingredients / evidence:
  * Jo, Park & Shefrin, "Bitcoin and Sentiment" (summary:
    https://quantpedia.com/?p=847): sentiment Granger-causes BTC returns and a
    lagged rise in VIX goes with lower BTC returns (2010-2018).
  * I-2026-11-07-CONTAGION (Dyer-Guest): post-ETF, BTC moves with US stocks.
  * R-2026-11-07-CORRACC (shortlist 4): an equity-stress signal as a risk gate.
Varies L-2026-11-07-BTCCORRSW (FAIL, potential 0), which gated BTC on the
20/60-day BTC-SPY correlation: noisy, needed two estimated correlations. Fix:
use the equity market's own fear gauge, one ratio, no correlation estimate.
Theme 12: VIX is a SIGNAL only; the book holds only BTC (7-day calendar).

Rationale (written before any run): BTC is a high-sentiment-beta asset; VIX
spikes mark forced de-leveraging across risk assets (Mar 2020, May 2022,
Aug 2024) and BTC, levered and 24/7, is sold first. The gate is off ~85-90% of
days, so it should keep most of BTC's drift. Counter-hypothesis: BTC's own
crashes (Terra, FTX, 2018) are idiosyncratic and VIX misses them — then this
is a near-copy of buy & hold and fails the materiality bar.

RULE (fixed before any run):
  * At each BTC UTC close i, v = the latest ^VIX close on or before date i
    (the 16:15 ET VIX close precedes BTC's 00:00 UTC close of the same date;
    weekends carry Friday's value).
  * m = mean of the last 60 VIX closes up to and including v (trading days).
  * If v > 1.20 * m: T-bills from close i to i+1; else 100% BTC.
  * Before 60 VIX closes exist: 100% BTC.
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto).
Variants: ratio 1.10 / 1.30; mean window 30 / 120 VIX days.
trials: 1 + 4 variants + L-2026-11-07-BTCCORRSW family's 6 lifetime runs
(same hypothesis: equity stress gates BTC) = 11; family shared with BTCCORRSW
so the Deflated-Sharpe bar keeps rising."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"
VIX = "^VIX"


def make(ratio=1.20, n=60):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st["vix"] = []
        v = px[VIX][i]
        if v:
            st["vix"].append(v)         # one entry per VIX trading day, never ahead of i
        if len(st["vix"]) < n:
            return {SYM: 1.0}
        last = st["vix"][-n:]
        m = sum(last) / n
        return {} if st["vix"][-1] > ratio * m else {SYM: 1.0}
    return weights


weights = make()

VARIANTS = {
    "ratio1.10": make(ratio=1.10),
    "ratio1.30": make(ratio=1.30),
    "n30": make(n=30),
    "n120": make(n=120),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-08-BTCVIXGATE", weights, [SYM, VIX], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=11, family="crypto-corr-switch", variants=VARIANTS,
        notes="lab original: T-bills while latest VIX close > 1.2x its 60-day mean, else 100% BTC; VIX signal "
              "only (BTC is the only holding); shares family with BTCCORRSW; 25bp; vault sealed from 2024-11"),
        indent=1))
