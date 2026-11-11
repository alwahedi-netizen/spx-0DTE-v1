"""L-2026-11-11-CMDBOOK2 — CMDBOOK v2: the commodity shortlist book with the
skew sleeve restricted to agriculture (lab original, RESEARCH.md §2b,
designed 2026-11-11). SAME FAMILY as L-2026-11-09-CMDBOOK (a robustness
re-specification of one combination hypothesis, not a new idea): it pays
CMDBOOK's lifetime trial count, and the family keeps ONE vault test.

VARIES: L-2026-11-09-CMDBOOK (potential 4; +6.9%/yr vs DBC +0.1%, worst drop
-28% vs -76%, 99.4% confidence, held-out Sharpe 0.67 vs 0.38; failed only
DSR 0.69 / t 1.69). Only change: the R-2026-11-08-CMDSKEW sleeve (3 lowest-
skew of 10 ETFs, 6 of them metals/energy) is replaced by the
R-2026-11-11-AGSKEW sleeve (2 lowest-skew of CANE/CORN/SOYB/WEAT).
Why (the stated, fixable reason): an independent 2026 replication
(GQResearch, https://gqresearch.substack.com/p/selling-lottery-tickets-in-commodity)
finds the skew premium only in agriculturals (t 2.71) and none in
energy+metals (t 0.80). If that is right, v1's skew sleeve was mostly noise,
and swapping in the half that carries the premium should raise the book's
active t without adding a parameter. It also removes the book's third oil
exposure (USO was eligible in v1's skew picks) — ag is a driver the other
three sleeves (oil curve, oil trend, currency-priced demand) do not have.
Honest caveat stated before the run: if AGSKEW alone fails its own test, a
v2 win would be a diversification effect, not evidence for the skew premium
— read the ex_skew variant (book without any skew sleeve) next to it.

RULE (fixed before any run): identical to L-2026-11-09-CMDBOOK except the
skew sleeve.
  every day, run the four ingredient rules unchanged (each decides at its own
  month-end close); ingredient code IMPORTED from its own script:
    carry  L-2026-11-07-CARRYPROXY    (USO while USO's 63-day return > USL's)
    oct    L-2026-11-08-OILCURVETREND (carry AND USO above its 10-month SMA)
    ccy    R-2026-11-09-CCYCMD        (DBC while the AUD/CAD/CLP/NZD/ZAR basket
                                       rose vs USD over 3 months; FX strictly
                                       before the decision day)
    agskew R-2026-11-11-AGSKEW        (2 lowest 252-day skew of CANE/CORN/SOYB/WEAT)
  at each month-end close i:
    live sleeves (as v1): carry needs USL priced 63 bars ago; oct also >= 10
      month-end USO closes; ccy > 3 month-ends seen and DBC priced; agskew
      needs >= 3 of the 4 ag ETFs with a valid 252-day skew (its own rule's
      minimum) and a non-empty pick
    sigma_k = stdev of the last 63 daily returns of the instrument(s) sleeve
      k would hold (USO; USO; DBC; the equal-weight basket of this month's 2
      ag picks), all 63 priced, else the sleeve is not live
    budget_k = (1/sigma_k) / sum of (1/sigma_j) over live sleeves
    book weight = sum_k budget_k * sleeve k's weights; an OFF sleeve keeps its
    budget in T-bills (budgets on instrument risk, not sleeve returns —
    v1's design, avoids the RATESBOOK vol-floor problem)
  gross <= 1, no leverage; held between month-ends.
Benchmark: buy & hold DBC. Costs 5bp. Start 2007-03-01 (as v1; oil sleeves
live ~2008-03, agskew ~2012-09; until then the live sleeves share the budget).
Includes 2008, 2014-16, 2020, 2022.
DATA TIMING: ETF closes <= i only (harness guard); FX side data strictly
before the decision day on its own calendar (CCYCMD's loader); month-end
tests peek dates[i+1]'s MONTH only (calendar, never prices).
Variants (neighbours, same as v1 so the two are comparable): vol lookback
42 / 126; equal budgets; ex_skew (carry + oct + ccy only — is ANY skew
sleeve worth its budget?).
FAMILY "L-2026-11-09-CMDBOOK": lifetime 5 -> 5 + 1 + 4 = 10.
A self-check mode (skew="all") rebuilds v1 exactly from this code; it is
used by the smoke test only and is NOT a variant or a trial.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb


def _mod(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V1 = _mod("L-2026-11-09-CMDBOOK")          # v1: its CARRY/OCT/CCY/SKEW modules + _sd_basket
AG = _mod("R-2026-11-11-AGSKEW")
CARRY, OCT, CCY, SKEW = V1.CARRY, V1.OCT, V1.CCY, V1.SKEW
SYMS = sorted(set(AG.UNIV) | {"USO", "USL", "DBC"})
START = "2007-03-01"


def make(vol_lb=63, equal=False, sleeves=("carry", "oct", "ccy", "skew"), skew="ag"):
    st = {}
    if skew == "ag":
        sk_univ, sk_make, sk_min = AG.UNIV, AG.make, 3
    else:                                   # "all": v1's sleeve (smoke self-check only)
        sk_univ, sk_make, sk_min = SKEW.UNIV, SKEW.make, 7

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["fn"] = {"carry": CARRY.make(), "oct": OCT.make(), "ccy": CCY.make(), "skew": sk_make()}
            st["w"], st["me_uso"], st["n_me"] = {}, [], 0
        sw = {k: f(i, dates, px) for k, f in st["fn"].items()}   # every day: ingredient state stays exact
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        st["n_me"] += 1
        if px["USO"][i]:
            st["me_uso"].append(px["USO"][i])
        live = {}
        usl_ok = i >= 63 and px["USL"][i] and px["USL"][i - 63]
        if i >= vol_lb + 1:
            if "carry" in sleeves and usl_ok:
                live["carry"] = ["USO"]
            if "oct" in sleeves and usl_ok and len(st["me_uso"]) >= 10:
                live["oct"] = ["USO"]
            if "ccy" in sleeves and st["n_me"] > 3 and px["DBC"][i]:
                live["ccy"] = ["DBC"]
            if "skew" in sleeves and i >= 253:
                n_ok = sum(1 for s in sk_univ if px[s][i] and SKEW._skew(px[s], i, 252) is not None)
                picks = sorted(sw["skew"])
                if n_ok >= sk_min and picks:
                    live["skew"] = picks
        inv = {}
        for k, basket in live.items():
            sd = V1._sd_basket(px, basket, i, vol_lb)
            if sd:
                inv[k] = 1.0 if equal else 1.0 / sd
        tot = sum(inv.values())
        w = {}
        for k, x in inv.items():
            b = x / tot
            for s, ws in sw[k].items():
                w[s] = w.get(s, 0.0) + b * ws
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"vol42": make(42), "vol126": make(126), "equal": make(63, True),
                "ex_skew": make(63, False, ("carry", "oct", "ccy"))}
    res = rb.evaluate("L-2026-11-11-CMDBOOK2", weights, SYMS, "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=10,
                      family="L-2026-11-09-CMDBOOK", variants=variants,
                      notes="CMDBOOK v2: month-end CARRYPROXY + OILCURVETREND + CCYCMD + AGSKEW (ag-only skew "
                            "sleeve replaces CMDSKEW; rules imported from their scripts), each live sleeve "
                            "budgeted 1/sigma63 of the instrument(s) it would hold, off sleeves in T-bills, "
                            "gross <= 1; bench DBC; family L-2026-11-09-CMDBOOK; lab original")
    print(json.dumps(res, indent=1))
