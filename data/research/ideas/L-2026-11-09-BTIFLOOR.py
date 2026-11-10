"""L-2026-11-09-BTIFLOOR — original (RESEARCH.md §2b), designed 2026-11-09
(ledger row, rule fixed then), scripted 2026-11-10: the CoinDesk Bitcoin
Trend Indicator's graded exposure, forced to zero whenever Bitcoin is more
than 25% below its 365-day closing high, trading only when the target moves
by at least 0.25 (a no-trade band).

Ingredients:
  * R-2026-11-08-BTCBTI (BTI, Global X BTRN rule): the only crypto rule that
    beat BTC on return — corrected (365-day annualisation, re-run
    2026-11-10): 79.0%/yr vs 73.3%, Sharpe 1.40 vs 1.12, worst drop -55%
    vs -83%; held-out Sharpe 0.39 vs 0.33. Methodology:
    https://downloads.coindesk.com/cd3/CDI/Trend-Indicator-Methodology.pdf
  * L-2026-11-08-BTC52WH (George-Hwang anchor, https://doi.org/10.1111/j.1540-6261.2004.00695.x):
    69.9%/yr vs 73.3%, Sharpe 1.25, worst drop -58%, held-out 0.76 vs 0.33,
    3 trades/yr.
  * No-trade band: Bysik-Slepaczuk 2026, https://arxiv.org/abs/2606.00060
    (trade only when the signal moves more than the cost threshold).
Ledger condition for running it ("only if the 52WH floor cuts the worst drop
at least as much as DD-TREND"): MET — BTC52WH -58% vs DD-TREND SMA10 on BTC
-72% (DD-2026-11-TREND result).

Rationale (from the 11-09 ledger row, before any run): BTI is fast (EWMA
half-lives 1-40 days) and graded; its losses come from fast V-reversals
and from staying half-in during slow bears. The 52-week-high floor is a
slow, different-anchor regime test that exits deep bears (2018, 2022)
before an average does. Stacking them: BTI decides how much in a healthy
market; the floor decides whether the market is healthy at all. The band
replaces BTI's 50% turnover cap as the cost control (fewer, larger trades).
Counter-hypothesis: both lag the same tops, so the floor adds nothing; the
band delays exits in fast crashes.

RULE (fixed in the 11-09 ledger; scripting choices stated here before any run):
  * BTI exactly as R-2026-11-08-BTCBTI: 4 EWMA pairs (half-lives 1/5,
    2.5/10, 5/20, 10/40 days) over the last 180 closes, component +1 if
    short >= long else -1, BTI = mean (-1..1).
  * Each Friday UTC daily close i: target = (BTI+1)/2 x [close_i >= 0.75 x
    max(last 365 closes incl. today)]. If |target - current| >= 0.25,
    trade to target; else hold. "current" = the drifted BTC weight.
    T-bills for the rest; weights drift between Fridays.
  * Warm-up (fewer than 365 closes; data start 2015-01-01, as BTI/52WH):
    hold 100% BTC = the benchmark (neutral, as BTC52WH).
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (asset_class crypto).
Variants: band 0.15 / 0.35; floor 20% / 30% off the high.
trials: BTI family 6 + BTC52WH family 7 (incl. DD-TREND's 2 BTC runs) + this
run's 5 = 18; family btc-bti (the stack inherits BTI's count, as the
ledger row said).
Caveat: BTC-USD closes 00:00 UTC; IBIT trades US hours (a Friday decision
executes the next US session — timing gap stated, not modelled)."""
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


def bti(xs):
    comps = [1 if _ewma(xs, s) >= _ewma(xs, l) else -1 for s, l in PAIRS]
    return sum(comps) / len(comps)


def make(band=0.25, floor=0.25, high_window=365, weekday=4):
    st = {}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"] = 1.0                 # warm-up = benchmark (neutral)
        else:                             # drift: BTC vs cash (cash ~0 over a day)
            a, b = px[SYM][i - 1], px[SYM][i]
            w = st["w"]
            if a and b and 0 < w < 1:
                g = w * b / a
                st["w"] = g / (g + 1 - w)
        if i >= high_window - 1 and date.fromisoformat(dates[i]).weekday() == weekday:
            xs = px[SYM][i - WIN + 1:i + 1]
            hist = [x for x in px[SYM][i - high_window + 1:i + 1] if x]
            c = px[SYM][i]
            if None not in xs and c and hist:
                ok = c >= (1 - floor) * max(hist)
                target = (bti(xs) + 1) / 2 if ok else 0.0
                if abs(target - st["w"]) >= band - 1e-12:
                    st["w"] = target
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "band15": make(band=0.15),
    "band35": make(band=0.35),
    "floor20": make(floor=0.20),
    "floor30": make(floor=0.30),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-09-BTIFLOOR", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=18, family="btc-bti", variants=VARIANTS,
        notes="lab original: BTI graded weight x [close >= 75% of 365-day high], Friday UTC close, "
              "trade only if the target moves >= 0.25 (no-trade band), weights drift; warm-up holds "
              "BTC (neutral); 25bp; vault sealed from 2024-11"),
        indent=1))
