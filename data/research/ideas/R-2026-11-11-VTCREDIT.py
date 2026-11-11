"""R-2026-11-11-VTCREDIT — volatility-targeted high yield (Harvey, Hoyle,
Korgaonkar, Rattray, Sargaison & Van Hemert, "The Impact of Volatility
Targeting", JPM 45(1) 2018), scripted from the bond queue (I-2026-11-10-VTCREDIT).

SOURCE: https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf ;
summary https://quantpedia.com/the-impact-of-volatility-targeting-on-equities-bonds-commodities-and-currencies
Finding (60+ assets, 1926-2017): scaling exposure to a constant volatility
raises the Sharpe ratio of "risk assets" (equities AND credit) because their
volatility and returns are negatively related (leverage effect), and it does
NOT raise the Sharpe of government bonds or FX. It also cuts left-tail
events for every asset class.

VARIES: L-2026-11-07-VTBOND (vol-managed long Treasuries; the paper predicts
no gain there) and R-2026-10-28-VTSPYL (the same mechanism on the S&P,
shortlist 5). This applies it to the asset where the paper says it helps
and the bond desk has a sleeve: high yield (HYG).

RATIONALE (written before any run): high-yield volatility clusters, and
high-vol credit months have POOR risk-adjusted returns (2008 H2, 2015-16
energy, March 2020): spreads blow out while defaults are repriced. Cutting
HYG when its recent volatility is high, and levering it (up to 1.5x) in calm
carry regimes, should keep most of the credit premium with a smaller worst
drop and a better Sharpe than both HYG and AGG. Known failure: V-shaped
rebounds (April 2009, April 2020) arrive while estimated vol is still high,
so exposure is low exactly when credit rallies.

RULE (fixed before any run; the queue row's rule unchanged):
  * Each trading day, weights decided at close i from HYG daily returns
    through the PRIOR close (i-1): sigma = annualised EWMA stdev of HYG
    daily returns with a 20-trading-day half-life (lambda = 0.5**(1/20)),
    sqrt(252) annualisation, mean assumed 0 (RiskMetrics form).
  * HYG weight = min(CAP 1.5, TARGET 6% / sigma); the rest earns T-bills.
  * Warm-up: until 60 HYG daily returns exist, weight 0 (T-bills); the
    EWMA is seeded with the plain variance of those first 60 returns.
  * Financing: the harness charges T-bills on gross > 1. THIS SCRIPT ADDS
    SPREAD = 50bp/yr on gross above 1 (same wrapper as L-2026-11-10-RATESLEV,
    inside __main__ only and restored afterwards; the 2x-cost gate and every
    variant pay it). HYG has no liquid future, so >1x needs portfolio margin
    or a box-spread loan; a Schwab margin loan (T-bills + 3-6pp) is NOT
    assumed and would hurt.
Benchmark: AGG buy & hold (the bond desk's aggregate benchmark; HYG's own
buy & hold is reported in the notes for context by the lead if wanted).
Costs 3bp per unit of turnover (daily re-weighting; expect ~10-20 turns/yr).
Start 2007-04-01 (HYG listed 2007-04-11; includes 2008, 2011, 2015-16, 2020).
Variants (4): half-life 10 and 40 days; target 4% and 8%.
trials = 5 (new family; VTBOND was never run, VTSPYL is another asset).
DATA TIMING: Yahoo adjusted closes only; sigma uses closes through i-1 for a
trade at close i (one day more conservative than the harness requires). No
external series.
Check after the run: worst drop vs HYG's and AGG's, average weight, 2008 and
March-April 2020 separately, then L-2026-11-10-CREDITVT (EQCREDIT x this).
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-11-VTCREDIT"
HY, BENCH = "HYG", "AGG"
SPREAD = 0.005          # financing spread over T-bills on gross > 1, per year
WARM = 60


def make(half_life=20, target=0.06, cap=1.5):
    lam = 0.5 ** (1.0 / half_life)
    st = {}

    def reset():
        st.clear()
        st.update(rets=[], var=None, prev_px=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        # fold in the return i-2 -> i-1 so sigma uses closes through i-1 only
        if i >= 1:
            p = px[HY][i - 1]
            if p and st["prev_px"]:
                r = p / st["prev_px"] - 1
                st["rets"].append(r)
                if st["var"] is None:
                    if len(st["rets"]) == WARM:
                        st["var"] = sum(x * x for x in st["rets"]) / WARM
                else:
                    st["var"] = lam * st["var"] + (1 - lam) * r * r
            if p:
                st["prev_px"] = p
        if st["var"] is None or not px[HY][i] or st["var"] <= 0:
            return {}
        sigma = math.sqrt(st["var"] * 252)
        return {HY: min(cap, target / sigma)}
    return weights


weights = make(20, 0.06, 1.5)

_ORIG_SIM = rb.simulate


def spread_simulate(weights_fn, dates, px, rf, cost_bps=5.0):
    """rb.simulate plus SPREAD/yr on gross exposure above 1 (daily, /252)."""
    gross = {}

    def rec(i, d, p):
        w = weights_fn(i, d, p) or {}
        gross[i] = sum(abs(v) for v in w.values() if v)
        return w
    rets, turnover = _ORIG_SIM(rec, dates, px, rf, cost_bps)
    return [r - max(0.0, gross.get(i, 0.0) - 1) * SPREAD / 252
            for i, r in enumerate(rets)], turnover


if __name__ == "__main__":
    import json
    rb.simulate = spread_simulate
    try:
        r = rb.evaluate(ID, weights, [HY], BENCH, start="2007-04-01",
                        asset_class="bonds", trials=5, family=ID,
                        variants={"HL10": make(10, 0.06), "HL40": make(40, 0.06),
                                  "TGT4": make(20, 0.04), "TGT8": make(20, 0.08)},
                        notes="HYG weight = min(1.5, 6%/sigma), sigma = EWMA (20-day half-life) "
                              "annualised HYG vol through the prior close, rest T-bills; financing "
                              "T-bills + 50bp above 1x (script wrapper); bench AGG; 2007-04+")
    finally:
        rb.simulate = _ORIG_SIM
    print(json.dumps(r, indent=1))
