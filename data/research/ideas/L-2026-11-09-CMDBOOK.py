"""L-2026-11-09-CMDBOOK — commodity shortlist book, risk-parity sized (lab
original, RESEARCH.md §2b). Designed 2026-11-09 as a portfolio-fit exercise;
re-specified 2026-11-10 by the lead's queue as a full evaluate() run that
combines the four potential-4 commodity blocks (ledger row keeps its id; its
rule text changes from "CARRYPROXY + CMDSKEW + CMDTRENDINFL saved series" to the
four live signals below — note the change in the ledger notes).

INGREDIENTS (each FAILED alone on DSR / t >= 3 but rated potential 4):
  * L-2026-11-07-CARRYPROXY   USO only while USO's 63-day return beats USL's
                              (oil curve-tightening proxy; Boons-Porras Prado JF 2019)
  * L-2026-11-08-OILCURVETREND CARRYPROXY AND USO above its 10-month SMA
  * R-2026-11-09-CCYCMD       DBC only while the AUD/CAD/CLP/NZD/ZAR basket rose vs
                              USD over 3 months (Chen-Rogoff-Rossi QJE 2010)
  * R-2026-11-08-CMDSKEW      the 3 lowest-skew of 10 single-commodity ETFs
                              (Fernandez-Perez et al. JBF 2018)
  The ingredient rules are IMPORTED from their own scripts (same code, same
  parameters), so the book cannot drift from what was tested.

RATIONALE (written before any run): the four blocks earn in different regimes
— oil physical tightness (curve), oil trend, forward-looking demand priced by
commodity currencies, and a cross-sectional lottery/hedging premium — and each
failed alone mainly for lack of statistical power (t < 3), not for lack of
edge (all four beat DBC/USO on Sharpe with -28% to -45% worst drops vs -64% to
-98%). If their active returns are weakly correlated, an equal-risk book should
raise the t-stat roughly by sqrt(effective number of bets) — themes 11, 15.
Known risk stated up front: two of the four sleeves are oil (OILCURVETREND is
a subset of CARRYPROXY's on-months), so oil can carry up to ~half the risk;
the ex-OILCURVETREND variant measures that.

RULE (fixed before any run):
  every day, run the four ingredient rules unchanged (each decides at its own
  month-end close and holds its choice for the next month).
  at each month-end close i:
    live sleeves = those with enough data:
      CARRYPROXY: USL priced 63 bars ago
      OILCURVETREND: the above AND >= 10 month-end USO closes seen
      CCYCMD: > 3 month-ends seen and DBC priced
      CMDSKEW: >= 7 of the 10 ETFs have a valid 252-day skew (so the sleeve
               ranks a real cross-section, as in its own 2011+ test)
    sigma_k = stdev of the last 63 daily returns of the instrument(s) sleeve k
              would hold: USO (both oil sleeves), DBC (CCYCMD), the equal-
              weight basket of this month's 3 skew picks (CMDSKEW); every one of
              the 63 daily returns must be priced, else the sleeve is not live
    budget_k = (1/sigma_k) / sum over live sleeves of (1/sigma_j)   (sums to 1)
    book weight of each symbol = sum_k budget_k * (sleeve k's weight in it)
    a sleeve that is OFF (its rule says T-bills) keeps its budget in T-bills
    — budgets are set on the instruments' risk, not on the sleeves' realised
    returns, so a mostly-cash sleeve is NOT given a huge budget (the RATESBOOK
    vol-floor problem, learnings 2026-11-09).
  gross exposure <= 1, no leverage; held between month-ends.
Benchmark: buy & hold DBC. Costs 5bp. Start 2007-03-01 (OILCURVETREND's SMA
warm-up; USL lists 2007-12, so the oil sleeves go live ~2008-03 and CMDSKEW
~2012-09; until then the live sleeves share the budget — stated before the
run). Includes 2008, 2014-16, 2020, 2022.
Variants (neighbours): vol lookback 42 and 126 days; equal budgets (no risk
parity); three sleeves without OILCURVETREND (oil double-count check).
New family "L-2026-11-09-CMDBOOK" -> trials 5.
Data loaded outside prices(): the CCYCMD sleeve reads FX bars dated STRICTLY
BEFORE the decision day (its own loader; see R-2026-11-09-CCYCMD).
"""
import importlib.util
import json
import math
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


CARRY = _mod("L-2026-11-07-CARRYPROXY")
OCT = _mod("L-2026-11-08-OILCURVETREND")
CCY = _mod("R-2026-11-09-CCYCMD")
SKEW = _mod("R-2026-11-08-CMDSKEW")
UNIV = list(SKEW.UNIV)
SYMS = sorted(set(UNIV) | {"USO", "USL", "DBC"})
START = "2007-03-01"


def _sd_basket(px, syms, i, n):
    r = []
    for k in range(i - n + 1, i + 1):
        vals = []
        for s in syms:
            a, b = px[s][k - 1], px[s][k]
            if not (a and b):
                return None
            vals.append(b / a - 1)
        r.append(sum(vals) / len(vals))
    if len(r) < 20:
        return None
    m = sum(r) / len(r)
    v = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(v) if v > 0 else None


def make(vol_lb=63, equal=False, sleeves=("carry", "oct", "ccy", "skew")):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["fn"] = {"carry": CARRY.make(), "oct": OCT.make(), "ccy": CCY.make(), "skew": SKEW.make()}
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
                n_ok = sum(1 for s in UNIV if px[s][i] and SKEW._skew(px[s], i, 252) is not None)
                picks = sorted(sw["skew"])
                if n_ok >= 7 and picks:
                    live["skew"] = picks
        inv = {}
        for k, basket in live.items():
            sd = _sd_basket(px, basket, i, vol_lb)
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
                "ex_oct": make(63, False, ("carry", "ccy", "skew"))}
    res = rb.evaluate("L-2026-11-09-CMDBOOK", weights, SYMS, "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="L-2026-11-09-CMDBOOK", variants=variants,
                      notes="month-end: CARRYPROXY + OILCURVETREND + CCYCMD + CMDSKEW (rules imported from "
                            "their scripts), each live sleeve budgeted 1/sigma63 of the instrument(s) it would "
                            "hold, off sleeves in T-bills, gross <= 1; bench DBC; lab original (shortlist book)")
    print(json.dumps(res, indent=1))
