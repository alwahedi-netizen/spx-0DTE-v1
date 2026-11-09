"""L-2026-11-08-BTC52WH — original (RESEARCH.md §2b): hold Bitcoin only while it
is within 25% of its 52-week (365-day) closing high; T-bills otherwise.
Designed 2026-11-08 (ledger row, rule fixed then); scripted 2026-11-09.

Canon: George & Hwang, "The 52-Week High and Momentum Investing", JF 2004,
https://doi.org/10.1111/j.1540-6261.2004.00695.x — investors anchor on the
52-week high, so nearness to it predicts continuation. Cross-sectional
commodity form already in the ledger as I-2026-11-08-CMD52WH (Bianchi-Drew-Fan).

Varies DD-2026-11-TREND (BTC SMA10 / MOM12, shortlist potential 5): same
risk-reducer driver (theme 10/16), different ANCHOR — distance from the high,
not from an average. Lessons used: weekly cadence (LTWEEK died on weekly
switching of a NOISY signal; this one moves slowly, so few switches);
all-or-nothing because the anchor is a regime test, not a strength score.

Rationale (written before any run): BTC's deep bears (2018 −84%, 2022 −77%)
all began with the price falling more than 25% off its high and staying
there; normal bull-market corrections mostly stop near 20-30%. An anchor on
the high exits earlier than a 10-month average in a crash that starts from a
spike top (the SMA lags far below a parabolic price). Counter-hypothesis:
the 25% line sits inside BTC's normal noise (May 2021 −50% within a bull,
2019-20 chop), so it whipsaws and only matches DD-TREND's crash cut at
higher cost. Judged mainly on risk-adjusted return / worst drop (theme 16).

RULE (fixed 2026-11-08 in the ledger, before any run):
  * Each Sunday UTC daily close i: H = max(close over the last 365 closes,
    incl. today). Weight = 1 (100% BTC) if close_i >= 0.75 x H, else 0
    (T-bills). Held until the next Sunday.
  * Before 365 closes exist (data start 2015-01-01 -> 2015-12-31): hold BTC,
    i.e. the benchmark — neutral, so the warm-up earns no free crash avoidance.
    (Scripting choice made 2026-11-09, stated here before any run.)
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (asset_class crypto).
Variants (ledger): band 20% / 30% / 35% off the high; 180-day high (25%).
trials: 1 + 4 variants + DD-2026-11-TREND's two BTC runs (same driver) = 7;
new family btc-52wh.
Caveat: BTC-USD is spot 24/7 with a 00:00 UTC close; IBIT trades US hours, so
a Sunday decision executes Monday (timing gap stated, not modelled)."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(band=0.25, window=365, weekday=6):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"] = 1.0               # warm-up = benchmark (neutral)
        if i >= window - 1 and date.fromisoformat(dates[i]).weekday() == weekday:
            win = [x for x in px[SYM][i - window + 1:i + 1] if x]
            c = px[SYM][i]
            if c and win:
                st["w"] = 1.0 if c >= (1 - band) * max(win) else 0.0
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "band20": make(band=0.20),
    "band30": make(band=0.30),
    "band35": make(band=0.35),
    "high180": make(window=180),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-08-BTC52WH", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=7, family="btc-52wh", variants=VARIANTS,
        notes="lab original (George-Hwang anchor, time-series): BTC only while close >= 75% of its "
              "365-day closing high, Sunday decision, T-bills otherwise; warm-up holds BTC (neutral); "
              "25bp; vault sealed from 2024-11"),
        indent=1))
