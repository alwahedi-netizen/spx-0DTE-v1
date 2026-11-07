"""L-2026-11-07-ETHBTCROT — original (RESEARCH.md §2b): ETH/BTC relative-trend
rotation between the two Schwab-tradeable crypto majors. Source: lab.

Ingredients: crypto momentum evidence (Liu, Tsyvinski & Wu, "Common Risk
Factors in Cryptocurrency", JF 2022 — cross-sectional crypto momentum; Liu &
Tsyvinski RFS 2021 — time-series momentum), restricted to the two coins with
US spot ETFs (IBIT/FBTC, ETHA) and CME futures, so it varies
I-2026-10-28-CRYPTOXS (rejected: alt survivorship + cannot short alts) by
using only two always-held majors and never shorting.

Rationale (written before any run): risk appetite inside crypto rotates —
in "alt seasons" flows move from BTC into higher-beta ETH for months, then
reverse as leverage unwinds. A slow relative-trend rule on the ETH/BTC ratio
rides those multi-month rotations while staying fully in crypto, so the
benchmark is BTC itself (pure relative value, no market-timing).
Caveat stated up front: ETH is the ex-post #2 survivor (selection bias), so
this can be PROMISING at best until tested on a point-in-time #2 coin.

RULE (fixed before any run):
  * Every Sunday close (UTC): ratio = ETH-USD / BTC-USD for each of the last
    140 days (20 weeks). If today's ratio > its 140-day average: hold 100% ETH
    for the next week; else 100% BTC.
  * Hold BTC until 140 days of both prices exist. Always fully invested.
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (a switch costs 2
units = 50bp). Start 2018-01-01 (ETH-USD on Yahoo from 2017-11).
Variants: 70, 105, 175 and 210-day ratio averages (±25%/±50%).
trials: 1 + 4 variants = 5 (new family)."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BTC, ETH = "BTC-USD", "ETH-USD"


def make(n=140, weekday=6):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"] = {BTC: 1.0}
        if i + 1 >= n and date.fromisoformat(dates[i]).weekday() == weekday:
            e, b = px[ETH][i - n + 1:i + 1], px[BTC][i - n + 1:i + 1]
            if None not in e and None not in b:
                ratio = [x / y for x, y in zip(e, b)]
                st["w"] = {ETH: 1.0} if ratio[-1] > sum(ratio) / n else {BTC: 1.0}
        return st["w"]
    return weights


weights = make()

VARIANTS = {f"sma{k}": make(n=k) for k in (70, 105, 175, 210)}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-07-ETHBTCROT", weights, [BTC, ETH], bench=BTC, start="2018-01-01",
        asset_class="crypto", trials=5, family="eth-btc-rotation", variants=VARIANTS,
        notes="lab original: weekly, hold ETH if ETH/BTC > its 140-day mean else BTC; 25bp; "
              "ETH is the ex-post #2 survivor (selection bias); vault sealed from 2024-11"),
        indent=1))
