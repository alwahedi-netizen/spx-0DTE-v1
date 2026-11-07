"""R-2026-11-07-GOLDTSY — gold held only when gold AND Treasuries both have
positive 12-month momentum (Quantpedia, Dujava, 2026-01-04, "Cross-Asset
Price-Based Regimes for Gold":
https://quantpedia.com/cross-asset-price-based-regimes-for-gold/).

Rationale: positive Treasury momentum = falling yields (easing / growth
scare), the macro state in which gold's opportunity cost falls and haven
demand rises; gold momentum alone is noisier. The source reports the joint
state adds predictive power beyond gold's own past return and that only the
(gold up, Treasuries up) state is reliably good for gold.

RULE (fixed before any run; the source's final amended rule):
  at each month-end close compute the trailing 252-day total return of GLD and
  of IEF; if BOTH are > 0 hold 100% GLD next month, else T-bills.
Benchmark: buy & hold GLD. Costs 5bp/unit turnover. GLD from 2004-11 -> first
signal 2005-12; development data 2005-2024 includes 2008 and the 2013 crash.
The source's history (1969-2025) used reconstructed gold/Treasury series; we
test the ETF form only. trials = 16: the source looked at 1/3/6/12-month
windows across four regime states before settling on 12 months; the
variants (6/9/15/18 months) are its neighbours.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb


def make(lookback=252):
    st = {}

    def mom(col, i):
        if i < lookback or not col[i] or not col[i - lookback]:
            return None
        return col[i] / col[i - lookback] - 1

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            g, t = mom(px["GLD"], i), mom(px["IEF"], i)
            st["w"] = {"GLD": 1.0} if (g is not None and t is not None and g > 0 and t > 0) else {}
        return st.get("w", {})
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb126": make(126), "lb189": make(189), "lb315": make(315), "lb378": make(378)}
    res = rb.evaluate("R-2026-11-07-GOLDTSY", weights, ["GLD", "IEF"], "GLD", start="2004-12-01",
                      cost_bps=5.0, asset_class="commodities", trials=16,
                      family="gold-treasury-momentum", variants=variants,
                      notes="GLD next month only if GLD and IEF 12-month returns both > 0, else T-bills; "
                            "bench GLD; Quantpedia 2026-01-04 final rule; ETF form 2005+")
    print(json.dumps(res, indent=1))
