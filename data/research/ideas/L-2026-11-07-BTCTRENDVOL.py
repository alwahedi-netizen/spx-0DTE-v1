"""L-2026-11-07-BTCTRENDVOL — original (RESEARCH.md §2b): Bitcoin 10-month trend
filter x volatility-managed sizing. Source: lab.

Ingredients (KNOWLEDGE.md shortlist): DD-2026-11-TREND (potential 5,
risk-reducer; BTC SMA10 earned +43%/yr vs +42% buy & hold but with far
shallower drops) and R-2026-10-28-VTSPYL (potential 5; Moreira-Muir vol
management, PASS on the allocation track). Queued family L-TRENDLEV applied
to crypto.

Rationale (written before any run): trend removes BTC's long bear markets
(2018, 2022: -75 to -80%); volatility scaling removes the crash-spike weeks
inside up-trends (Moreira & Muir 2017: high recent vol predicts high future
vol but not higher return). Counter-hypothesis to be tested, not assumed:
Tripathi (Financial Economics Letters 5(2):53, 2026) finds BTC's trend
returns do not degrade in high-vol regimes, so de-levering on vol spikes may
cut BTC's best (positive-skew) weeks. The result tells us which holds.

RULE (fixed before any run):
  * Trend: at each calendar month-end close (UTC), trend is ON if the close is
    above the average of the last 10 month-end closes (incl. today); else OFF.
    Before 10 month-ends exist: OFF (cash).
  * Size: every Sunday close and every month-end close, if trend ON, weight =
    min(1.0, 50% / (stdev of the last 30 daily returns x sqrt(365))); if OFF, 0.
    50% is a round number below BTC's typical 60-80% realised vol, set the
    same way VTSPYL set 15% below the S&P's typical vol. No leverage (IBIT).
  * Weight held between update days; rest in T-bills.
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto).
Variants: vol target 40% / 60%; 60-day vol window; 8- and 12-month SMA.
trials: 1 + 5 variants + DD-2026-11-TREND's BTC SMA10 run = 7.
Known before the run (stated honestly): the unscaled SMA10 leg's full-period
result on BTC is already in the ledger (DD-2026-11-TREND)."""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(sma_m=10, target=0.50, vol_n=30, cap=1.0):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(me=[], on=False, w=0.0)
        d = date.fromisoformat(dates[i])
        month_end = (d + timedelta(days=1)).month != d.month
        c = px[SYM][i]
        if month_end and c:
            st["me"].append(c)
            st["on"] = len(st["me"]) >= sma_m and c > sum(st["me"][-sma_m:]) / sma_m
        if month_end or d.weekday() == 6:
            w = 0.0
            if st["on"] and i > vol_n:
                cl = px[SYM][i - vol_n:i + 1]
                if None not in cl:
                    r = [cl[k] / cl[k - 1] - 1 for k in range(1, len(cl))]
                    m = sum(r) / len(r)
                    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(365)
                    w = min(cap, target / sd) if sd > 0 else cap
                else:
                    w = st["w"]
            st["w"] = w
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "target40": make(target=0.40),
    "target60": make(target=0.60),
    "vol60": make(vol_n=60),
    "sma8": make(sma_m=8),
    "sma12": make(sma_m=12),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-07-BTCTRENDVOL", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=7, family="btc-trend-vol", variants=VARIANTS,
        notes="lab original: BTC month-end 10-mo SMA trend x min(1, 50%/30d vol) sized weekly; 25bp; "
              "tests Moreira-Muir vs Tripathi 2026 on BTC; vault sealed from 2024-11"),
        indent=1))
