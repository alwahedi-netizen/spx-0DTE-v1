"""R-2026-11-07-ZPBENS — volatility-sized Donchian ensemble on Bitcoin
(Zarattini, Pagani & Barbon, "Catching Crypto Trends: A Tactical Approach for
Bitcoin and Altcoins", Swiss Finance Institute RP 25-80, SSRN 2025;
https://econpapers.repec.org/RePEc:chf:rpseri:rp2580 ; rules as summarised by
CXO Advisory 2025-05-29:
https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/).

Source result: Bitcoin base case 2015 - Mar 2025, net CAGR ~18% for the
ensemble at 10bp, annualised alpha ~11% vs buy & hold; also tested at 25 and
50bp. Varies P-CRYPTO's TR30 (single 30-bar breakout, 15% trail, in paper)
and I-2026-10-28-TURTLE (rejected as the same driver): the difference that
matters is the ENSEMBLE of nine lookbacks (no single tuned window) plus
volatility-target sizing, which is the published configuration — testing it
tells us whether the ensemble+sizing adds anything over plain trend on BTC.

Rationale: crypto trends persist (trend-chasing retail flow, limited
arbitrage capital); averaging nine channel lengths diversifies the lookback
choice, and sizing to a fixed volatility keeps risk roughly constant.

RULE (fixed before any run), daily at the UTC close, for each lookback
n in {5, 10, 20, 30, 60, 90, 150, 250, 360} days:
  * Entry: flat and today's close > the highest close of the prior n days.
  * Trailing stop: on entry, and each day while long, stop = max(yesterday's
    stop, midpoint of the highest and lowest close of the last n days).
  * Exit: long and today's close < yesterday's stop.
  * Exposure = (number of lookbacks long) / 9.
  * Target weight = exposure x min(2.0, 25% / (stdev of last 90 daily returns
    x sqrt(365))). Leverage above 1 is financed at T-bills by the harness.
  * Implementation band: re-trade only when the target moves >= 0.10 from the
    current weight, or goes to/from zero (the source flags cost mitigation;
    the band is ours, stated here before the run).
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto). Schwab: CME BTC /
MBT futures (leverage) or IBIT/FBTC (cap 1.0 variant).
Variants: 20% and 30% vol target; leverage cap 1.0; short lookbacks only
(5-60); long lookbacks only (90-360).
trials: 1 + 5 variants + P-CRYPTO TR30 (same breakout family) = 7."""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"
LBS = (5, 10, 20, 30, 60, 90, 150, 250, 360)


def make(lbs=LBS, target=0.25, cap=2.0, vol_n=90, band=0.10):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(pos={n: False for n in lbs}, stop={n: None for n in lbs}, w=0.0)
        c = px[SYM][i]
        if not c:
            return {SYM: st["w"]} if st["w"] else {}
        for n in lbs:
            if i < n:
                continue
            prior = px[SYM][i - n:i]            # the n closes before today
            last = px[SYM][i - n + 1:i + 1]     # the n closes ending today
            if None in prior or None in last:
                continue
            mid = (max(last) + min(last)) / 2
            if st["pos"][n]:
                if c < st["stop"][n]:
                    st["pos"][n], st["stop"][n] = False, None
                else:
                    st["stop"][n] = max(st["stop"][n], mid)
            elif c > max(prior):
                st["pos"][n], st["stop"][n] = True, mid
        expo = sum(st["pos"].values()) / len(lbs)
        tgt = 0.0
        if expo and i > vol_n:
            cl = px[SYM][i - vol_n:i + 1]
            if None not in cl:
                r = [cl[k] / cl[k - 1] - 1 for k in range(1, len(cl))]
                m = sum(r) / len(r)
                sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(365)
                tgt = expo * min(cap, target / sd) if sd > 0 else 0.0
            else:
                tgt = st["w"]
        if (tgt == 0) != (st["w"] == 0) or abs(tgt - st["w"]) >= band:
            st["w"] = tgt
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "target20": make(target=0.20),
    "target30": make(target=0.30),
    "cap1": make(cap=1.0),
    "short_lbs": make(lbs=(5, 10, 20, 30, 60)),
    "long_lbs": make(lbs=(90, 150, 250, 360)),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-07-ZPBENS", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=7, family="crypto-breakout", variants=VARIANTS,
        notes="Zarattini-Pagani-Barbon: 9-lookback close-Donchian ensemble, midpoint trailing stop, "
              "25% vol target (90d), cap 2x, 0.10 trade band; 25bp; varies P-CRYPTO TR30"),
        indent=1))
