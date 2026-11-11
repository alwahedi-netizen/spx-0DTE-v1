"""R-2026-11-11-AGSKEW — the commodity skewness premium, agriculture only
(long-only ETF form). PROMOTES ledger row I-2026-11-10-AGSKEW (exact id
checked; update that row's id/phase, do not add a second row). Same family
as R-2026-11-08-CMDSKEW ("cmd-skew"): it is the same hypothesis on a
restricted universe, so it pays that family's trial count.

Sources:
  * Fernandez-Perez, Frijns, Fuertes & Miffre, "The skewness of commodity
    futures returns", Journal of Banking & Finance 86 (2018)
    (https://openaccess.city.ac.uk/id/eprint/17843/): long the most negatively
    skewed / short the most positively skewed of 27 futures (12-month daily
    skewness) earns ~8%/yr 1987-2014.
  * GQResearch, "Selling lottery tickets in commodity futures" (2026-09-19,
    https://gqresearch.substack.com/p/selling-lottery-tickets-in-commodity):
    independent replication on 22 futures, holds out of sample (2019-02 to
    2026-06), but the premium sits in grains/softs/livestock (t 2.71) and NOT
    in energy + metals (t 0.80, net Sharpe 0.08).
Why it matters: R-2026-11-08-CMDSKEW (potential 4 -> 3, +4.6%/yr vs DBC
-1.5%, confidence 92%, lost the held-out window) ranks 10 ETFs of which 6
are metals/energy — the half where the replication finds nothing. This test
asks whether the ag half carries the effect on tradeable ETFs.

RATIONALE (written before any run): agricultural futures are dominated by
commercial hedgers (producers selling forward) and by speculators with
lottery preferences after weather scares; positively skewed (spiking)
contracts are overpriced, negatively skewed ones carry a premium for bearing
crash risk (Barberis-Huang skewness preference; hedging-pressure channel).
Grains and softs have the most weather-driven upside spikes, so the mispricing
should be largest there (the replication's sector split).

RULE (fixed before any run):
  universe: CANE CORN SOYB WEAT (every live single-commodity agricultural ETF
            with >= 10 years of Yahoo history; the livestock/softs ETNs —
            COW, JO, NIB, BAL, SGG — are delisted and not on Yahoo: stated
            survivorship/coverage caveat)
  at each month-end close i: skewness of each ETF's last 252 daily returns
  (the SAME _skew function as R-2026-11-08-CMDSKEW, imported, >= 95% of the
  returns present); need >= 3 eligible names (a 2-name "rank" is a coin flip);
  hold the 2 LOWEST-skew ETFs, 1/2 each, next month; else T-bills.
Benchmark: buy & hold DBC (the family's benchmark, so the potential rating is
comparable with CMDSKEW). A no-verdict control is printed alongside:
equal-weight CANE/CORN/SOYB/WEAT rebalanced monthly, and DBA buy & hold —
ag ETFs lost money to contango 2011-24, so beating DBC is a low bar; the
honest question is whether the RANK beats the equal-weight ag basket.
Costs 5bp/unit turnover. Start 2011-09-01 (CANE/SOYB/WEAT list 2011-09-19;
first signal ~2012-09). No 2008 in the sample (caveat, as CMDSKEW).
DATA TIMING: weights decided at month-end close i read only closes <= i (the
harness's _Past guard); the month-end test peeks dates[i+1]'s MONTH only
(calendar, never prices); executes at the same close as the signal
(harness convention, as CMDSKEW).
Variants (neighbours): lookback 126 / 189 / 315 days; hold 1 / 3 lowest.
FAMILY "cmd-skew": lifetime 6 (CMDSKEW: 1 + 5 variants) -> 6 + 1 + 5 = 12.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("cmdskew", HERE / "R-2026-11-08-CMDSKEW.py")
SKEW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SKEW)

UNIV = ["CANE", "CORN", "SOYB", "WEAT"]
START = "2011-09-01"


def make(lb=252, top=2, min_n=3):
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
            v = SKEW._skew(col, i, lb)
            if v is not None and not math.isnan(v):
                sk[s] = v
        if len(sk) < max(min_n, top):
            st["w"] = {}
        else:
            pick = sorted(sk, key=lambda s: (sk[s], s))[:top]
            st["w"] = {s: 1.0 / top for s in pick}
        return st["w"]
    return weights


def ew_control():
    """No-verdict control: equal-weight the ag ETFs that are priced, monthly."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        live = [s for s in UNIV if px[s][i] and i >= 1 and px[s][i - 1]]
        st["w"] = {s: 1.0 / len(live) for s in live} if len(live) >= 3 else {}
        return st["w"]
    return weights


weights = make()


def control_diagnostic():
    """Printed next to the verdict, never a verdict: the ag-skew picks vs the
    equal-weight ag basket and vs DBA, on the same development window."""
    syms = UNIV + ["DBC", "DBA"]
    dates, px = rb.prices(syms, START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    rf1 = rf[1:]
    idea, _ = rb.simulate(weights, dates, px, rf, 5.0)
    ew, _ = rb.simulate(ew_control(), dates, px, rf, 5.0)
    dba = rb.bench_returns("DBA", dates, px, rf)
    act = [a - b for a, b in zip(idea, ew)]
    return {"idea_sharpe": round(rb.sharpe(idea, rf1), 3), "ew_ag_sharpe": round(rb.sharpe(ew, rf1), 3),
            "dba_sharpe": round(rb.sharpe(dba, rf1), 3), "idea_cagr": round(rb.cagr(idea), 4),
            "ew_ag_cagr": round(rb.cagr(ew), 4), "dba_cagr": round(rb.cagr(dba), 4),
            "active_vs_ew_t": round(rb.t_stat(act), 2), "note": "diagnostic only - no verdict, no trial"}


if __name__ == "__main__":
    variants = {"lb126": make(126), "lb189": make(189), "lb315": make(315),
                "top1": make(252, 1), "top3": make(252, 3)}
    res = rb.evaluate("R-2026-11-11-AGSKEW", weights, UNIV, "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=12,
                      family="cmd-skew", variants=variants,
                      notes="month-end: hold the 2 lowest-skew (252d daily returns) of CANE/CORN/SOYB/WEAT, "
                            "1/2 each (>= 3 eligible, else T-bills); bench DBC; ag-only form of "
                            "Fernandez-Perez et al. 2018 per the GQResearch 2026 sector split; promotes "
                            "I-2026-11-10-AGSKEW; family cmd-skew")
    res["control_diagnostic"] = control_diagnostic()
    print(json.dumps(res, indent=1))
