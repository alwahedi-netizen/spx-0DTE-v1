"""R-2026-11-09-BTCQQQGATE — Bitcoin's trend as a weekly risk gate for the
Nasdaq-100: hold QQQ only while BTC is above its 50-day SMA AND its 20-day
rate of change is positive; otherwise SHY.

Source: QuantConnect Research, "Bitcoin Regime Signal for Growth Equities"
(2026; backtest Jan 2014 -> Aug 2026; author field blank on the page),
https://www.quantconnect.com/research/21195/bitcoin-regime-signal-for-growth-equities/p1
Published result (no costs stated): Sharpe 0.838 vs QQQ 0.682 / SPY 0.564;
25-setting grid (SMA 30-70 step 10 x ROC 10-30 step 5): median 0.812,
23/25 beat QQQ; the SMA-70 column weakest (0.63-0.76). No CAGR/drawdown given.
The author frames it as a risk-reduction gate, not a return engine.
Rationale cited by the source: Faber 2007 (trend filter), Liu-Tsyvinski 2021
(BTC time-series momentum), Iyer 2022 (IMF: BTC spillovers explain 14-18% of
equity volatility since 2020); BTC trades 24/7 and the most speculative
cohort holds both, so it reads risk appetite first.

Varies (cross-asset, new direction): L-2026-11-08-BTCVIXGATE and
L-2026-11-07-BTCCORRSW used EQUITY signals to gate BTC (both FAIL). Here a
CRYPTO signal gates EQUITIES. The rule is judged on QQQ, so the benchmark is
QQQ (not BTC-USD — BTC is only the signal; holding QQQ vs a BTC benchmark
would be meaningless). Same signal family as I-2026-11-07-BTCMARATIO /
R-2026-11-08-BTCBTI (short BTC trend), applied to a different asset.

HARNESS GAP HANDLED EXPLICITLY (KNOWLEDGE theme 12: mixing 7-day crypto with
weekday calendars drops weekend returns): the traded universe is QQQ + SHY
only, so the calendar is the US trading calendar and no QQQ return is lost.
BTC-USD is loaded separately and read ONLY as a signal, with a strict
date < today filter: Yahoo's BTC-USD bar dated D closes 00:00 UTC on D+1
(19:00/20:00 ET on D, after QQQ's 16:00 close), so using bar D at QQQ's
close on D would be look-ahead. The latest usable BTC close on a Monday is
Sunday's bar (= the source's information set at Monday 8am ET). The vault
holds: the harness truncates the QQQ calendar before 2024-11 and BTC bars are
read only before the current QQQ date.

RULE (fixed before any run; source defaults):
  * Decision on the first US trading day of each ISO week (normally Monday),
    at the close (the source trades at Monday's open: we trade one session
    later — conservative), using BTC daily closes dated strictly before it.
  * ON if BTC last close > mean of its last 50 closes AND last close > the
    close 20 BTC-days earlier. ON -> 100% QQQ; OFF -> 100% SHY. Held all week.
  * Before 50 BTC closes exist: hold QQQ (the benchmark; neutral).
Benchmark = buy & hold QQQ. Costs 10bp per unit turnover (ETF trades; >=10bp
kept as the crypto-desk floor; the double-cost gate checks 20bp).
Factor gate forced on (ff5mom): it holds equities, so a known factor in
disguise (market timing of beta) must show.
Variants (inside the source's grid): SMA 30 / 70; ROC 10 / 30.
trials: the source's 25-setting grid (our 5 runs sit inside it) = 25;
family btc-signal-equity."""
import bisect
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

RISK, SAFE, SIG = "QQQ", "SHY", "BTC-USD"
_BTC = {}


def set_btc(dates, closes):
    """Signal series (sorted ISO dates, closes). Tests inject synthetic data."""
    pairs = [(d, c) for d, c in zip(dates, closes) if c]
    _BTC["d"] = [d for d, _ in pairs]
    _BTC["c"] = [c for _, c in pairs]


def _btc():
    if not _BTC:
        d, p = rb.prices([SIG], "2014-01-01")
        set_btc(d, p[SIG])
    return _BTC


def make(sma=50, roc=20):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st["hold"] = RISK           # warm-up = benchmark (neutral)
        new_week = i == 0 or (date.fromisoformat(dates[i]).isocalendar()[:2]
                              != date.fromisoformat(dates[i - 1]).isocalendar()[:2])
        if new_week:
            b = _btc()
            k = bisect.bisect_left(b["d"], dates[i])   # BTC bars dated < today only
            need = max(sma, roc + 1)
            if k >= need:
                xs = b["c"][k - need:k]
                last = xs[-1]
                on = last > sum(xs[-sma:]) / sma and last > xs[-1 - roc]
                st["hold"] = RISK if on else SAFE
        sym = st["hold"]
        if px[sym][i] is None:          # SHY/QQQ missing (should not happen 2015+)
            return {}
        return {sym: 1.0}
    return weights


weights = make()

VARIANTS = {
    "sma30": make(sma=30),
    "sma70": make(sma=70),
    "roc10": make(roc=10),
    "roc30": make(roc=30),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-09-BTCQQQGATE", weights, [RISK, SAFE], bench=RISK, start="2015-01-01",
        asset_class="crypto", cost_bps=10.0, factors="ff5mom", trials=25,
        family="btc-signal-equity", variants=VARIANTS,
        notes="QuantConnect 2026: QQQ while BTC > 50d SMA and 20d ROC > 0 (BTC bars dated < today only), "
              "else SHY; weekly first trading day, at the close; QQQ/SHY calendar only (no weekend-return "
              "loss); bench QQQ; 10bp; factor gate forced; vault sealed from 2024-11"),
        indent=1))
