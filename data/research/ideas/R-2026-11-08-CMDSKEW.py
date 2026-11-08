"""R-2026-11-08-CMDSKEW — commodity skewness premium, long-only ETF form.
PROMOTES ledger row I-2026-11-07-CMDSKEW (same mechanism, queued for a test
slot yesterday; update that row, do not add a second one).

Source: Fernandez-Perez, Frijns, Fuertes & Miffre, "The skewness of commodity
futures returns", Journal of Banking & Finance 86, 2018
(https://openaccess.city.ac.uk/id/eprint/17843/): sorting 27 commodity futures
on the skewness of their past 12 months of daily returns, long the most
negatively skewed / short the most positively skewed earns ~8%/yr, not
explained by backwardation, momentum, hedging pressure or liquidity.
Independent practitioner replication: QuantSeeker, "Skewness as a Commodity
Signal" (Aug 2025, https://www.quantseeker.com/p/skewness-as-a-commodity-signal):
Sharpe 0.5-0.75 after costs on 25 futures. Quantpedia screener entry:
https://quantpedia.com/strategies/skewness-effect-in-commodities

Rationale: investors overpay for lottery-like (positively skewed) contracts
and hedgers pay to offload crash risk; negatively skewed contracts carry a
premium (selective hedging / skewness preference, Barberis-Huang).

RULE (fixed before any run; the ledger row's proposed long-only form):
  universe: CANE CPER CORN GLD PALL PPLT SLV SOYB USO WEAT (the 10 single-
            commodity ETFs of R-2026-11-07-CMDXSMOM; eligible once 253 closes,
            >= 95% present)
  at each month-end close: skewness of each ETF's last 252 daily returns;
  hold the 3 LOWEST-skew ETFs, 1/3 each, next month; T-bills if < 3 eligible.
Benchmark: buy & hold DBC. Costs 5bp/unit turnover. History 2011-10+ (CANE,
SOYB, WEAT, CPER), signals from ~2012-11: no 2008 in the sample (caveat).
Known weakness stated before the run: long-only drops the short (lottery) leg
where much of the premium sits, and 10 names make the ranks noisy.
Variants: lookback 126 / 189 / 315 days; hold 2 / 4 lowest. trials = 6.
"""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

UNIV = ["CANE", "CPER", "CORN", "GLD", "PALL", "PPLT", "SLV", "SOYB", "USO", "WEAT"]


def _skew(col, i, n):
    r = []
    for k in range(i - n + 1, i + 1):
        a, b = col[k - 1], col[k]
        if a and b:
            r.append(b / a - 1)
    if len(r) < n * 0.95:
        return None
    m = sum(r) / len(r)
    s2 = sum((x - m) ** 2 for x in r) / len(r)
    if s2 <= 0:
        return None
    return (sum((x - m) ** 3 for x in r) / len(r)) / s2 ** 1.5


def make(lb=252, top=3):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        sk = {}
        for s in UNIV:
            col = px[s]
            if i < lb + 1 or not col[i]:
                continue
            v = _skew(col, i, lb)
            if v is not None and not math.isnan(v):
                sk[s] = v
        if len(sk) < top:
            st["w"] = {}
        else:
            pick = sorted(sk, key=lambda s: (sk[s], s))[:top]
            st["w"] = {s: 1.0 / top for s in pick}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb126": make(126), "lb189": make(189), "lb315": make(315),
                "top2": make(252, 2), "top4": make(252, 4)}
    res = rb.evaluate("R-2026-11-08-CMDSKEW", weights, UNIV, "DBC", start="2011-09-01",
                      cost_bps=5.0, asset_class="commodities", trials=6,
                      family="cmd-skew", variants=variants,
                      notes="month-end: hold the 3 lowest-skew (252d daily returns) of 10 commodity ETFs, 1/3 each; "
                            "bench DBC; long-only form of Fernandez-Perez et al. 2018; 2011-10+ (no 2008); "
                            "promotes I-2026-11-07-CMDSKEW")
    print(json.dumps(res, indent=1))
