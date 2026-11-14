"""L-2026-11-14-CMDBOOK3 — the commodity book WITHOUT its doubtful skew sleeve
(lab, RESEARCH.md §2b; a fragility test of L-2026-11-09-CMDBOOK). League round
1, commodities desk. New ledger row L-2026-11-14-CMDBOOK3 (varies
L-2026-11-09-CMDBOOK: one sleeve removed; same family).

WHY THIS TEST (KNOWLEDGE.md themes 23 and 25, written before any run):
CMDBOOK (CARRYPROXY + OILCURVETREND + CCYCMD + CMDSKEW, inverse-vol budgets)
is the best commodity result to date (6.9%/yr vs 0.1% DBC, confidence 99.4%,
held-out win; failed only DSR/t). But swapping its skew sleeve for the
ag-only version (CMDBOOK2) dropped it to 4.5%/yr and 93% (theme 25), and an
independent replication (GQResearch 2026; R-2026-11-11-AGSKEW) finds the skew
premium ONLY in agriculturals — i.e. the 10-ETF skew sleeve CMDBOOK uses
(6 of 10 metals/energy) rests on a premium that does not replicate. Before
anyone levers or sizes the book (L-2026-11-11-CMDBOOKLEV, queued), the honest
question is whether the book stands WITHOUT that sleeve: three sleeves with
an economic story each (oil curve, oil curve x trend, commodity-currency
demand signal).
HYPOTHESIS: the book's edge comes from the oil-curve and commodity-currency
sleeves; removing the skew sleeve keeps most of the return and confidence.
If instead confidence falls well below 99%, CMDBOOK's headline leaned on the
non-replicating skew picks and should be down-rated (learning either way).
PASS CRITERION (pre-registered): research_bt verdict PASS vs buy-and-hold DBC
(all §0 gates with the family's lifetime trials, >= 70% of the 4 neighbours
beating DBC). Fragility read-out (pre-registered, reported separately):
"robust" if confidence >= 0.99 AND the held-out window beats DBC; "fragile"
otherwise.

RULE (fixed before any run): exactly L-2026-11-09-CMDBOOK's rule (imported:
same code, same parameters — its make() with sleeves=("carry","oct","ccy")):
  at each month-end close i, live sleeves among CARRYPROXY (USO while USO's
  63-day return beats USL's), OILCURVETREND (that AND USO above its 10-month
  SMA), CCYCMD (DBC while the AUD/CAD/CLP/NZD/ZAR basket rose vs USD over
  3 months; FX bars dated strictly before the decision day); each live
  sleeve's budget = (1/sigma63 of the instrument it would hold) normalised to
  sum 1; an OFF sleeve keeps its budget in T-bills; gross <= 1; held to the
  next month-end.
Benchmark: buy & hold DBC. Costs 5bp. Start 2007-03-01 (as CMDBOOK; the oil
sleeves go live ~2008-03 when USL has 63 bars). Symbols: the same list as
CMDBOOK (the skew ETFs stay loaded so the date calendar is identical).
DATA TIMING: price closes dated <= i only (harness guard); FX side data dated
strictly before dates[i] (CCYCMD's own loader, after harness fix 2 `=X` bars
are each day's close); month-end test peeks only at dates[i+1]'s MONTH;
weights decided at close i earn close i -> close i+1.
Variants (neighbours, as CMDBOOK's): vol lookback 42 / 126 days; equal
budgets; two sleeves (CARRYPROXY + CCYCMD, i.e. also without the oil
double-count).
FAMILY "L-2026-11-09-CMDBOOK" (same hypothesis: the commodity shortlist book)
-> lifetime trials 10 + 1 + 4 = 15.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("cmdbook", HERE / "L-2026-11-09-CMDBOOK.py")
BOOK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BOOK)

SLEEVES = ("carry", "oct", "ccy")
weights = BOOK.make(63, False, SLEEVES)

if __name__ == "__main__":
    variants = {"vol42": BOOK.make(42, False, SLEEVES), "vol126": BOOK.make(126, False, SLEEVES),
                "equal": BOOK.make(63, True, SLEEVES), "carry_ccy": BOOK.make(63, False, ("carry", "ccy"))}
    res = rb.evaluate("L-2026-11-14-CMDBOOK3", weights, BOOK.SYMS, "DBC", start=BOOK.START,
                      cost_bps=5.0, asset_class="commodities", trials=15,
                      family="L-2026-11-09-CMDBOOK", variants=variants,
                      notes="month-end: CMDBOOK without the CMDSKEW sleeve (CARRYPROXY + OILCURVETREND + CCYCMD, "
                            "rules imported), each live sleeve budgeted 1/sigma63 of what it would hold, off sleeves "
                            "in T-bills, gross <= 1; bench DBC; fragility test of L-2026-11-09-CMDBOOK (theme 25)")
    print(json.dumps(res, indent=1))
    rob = res.get("confidence", 0) >= 0.99 and res.get("oos_idea_sharpe", -9) > res.get("oos_bench_sharpe", 9)
    print(json.dumps({"fragility_readout": "robust" if rob else "fragile",
                      "cmdbook_v1_reference": {"cagr": 0.0693, "sharpe": 0.493, "confidence": 0.9937}}, indent=1))
