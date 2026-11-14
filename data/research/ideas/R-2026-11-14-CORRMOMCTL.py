"""R-2026-11-14-CORRMOMCTL — CONTROL for R-2026-11-14-CORRMOMREV: plain 12-month
cross-sectional momentum, long 2 / short 2 of the four DB commodity sector
ETFs, every month (no correlation switch). League round 1, commodities desk.
No new ledger row of its own: it is the source's baseline ("momentum") and is
logged in R-2026-11-14-CORRMOMREV's row notes.

Source: Pauchlyova/Vojtko, Quantpedia 2024-09-16
https://quantpedia.com/how-to-improve-commodity-momentum-using-intra-market-correlation/
— the source reports that plain 12-month momentum on DBA/DBB/DBE/DBP
"slightly outperforms the benchmark" but with higher volatility, and that the
correlation switch beats it on every metric (numbers unreadable: images).
RUN THIS BEFORE R-2026-11-14-CORRMOMREV (that script reads this result for
its pre-registered sign check).

HYPOTHESIS (written before any run): cross-sectional sector momentum alone
is weak in commodities on ETFs (R-2026-11-07-CMDXSMOM: confidence 52%); this
run is the baseline, not a candidate.
PASS CRITERION (pre-registered): research_bt verdict PASS vs T-bills. Not
expected; its job is the comparison.

RULE: identical to R-2026-11-14-CORRMOMREV with the switch removed (the
weights function is imported from that script, switch=False): at each
month-end close i with all four priced 252 bars ago and on the last 251 bars
(same eligibility as the switched version, so both start on the same month),
long the 2 highest 252-day returns at +0.5 each, short the 2 lowest at -0.5
each; T-bills on capital and short proceeds; bench T-bills; 5bp; start
2007-01-01 (first signal 2008-01).
DATA TIMING: reads closes dated <= i only (harness guard); month-end test
peeks only at dates[i+1]'s MONTH; weights decided at close i earn
close i -> close i+1.
No variants (a single control setting). FAMILY "cmd-xs-momentum" (it is the
plain cross-sectional commodity momentum hypothesis) -> +1 trial.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("corrmomrev", HERE / "R-2026-11-14-CORRMOMREV.py")
CMR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CMR)

weights = CMR.make(switch=False)

if __name__ == "__main__":
    res = rb.evaluate("R-2026-11-14-CORRMOMCTL", weights, CMR.UNIV, None, start=CMR.START,
                      cost_bps=5.0, asset_class="commodities", trials=1,
                      family="cmd-xs-momentum",
                      notes="CONTROL for R-2026-11-14-CORRMOMREV: month-end long 2 best / short 2 worst of "
                            "DBA/DBB/DBE/DBP by 252-day return, +-0.5 each, net 0; bench T-bills; 5bp")
    print(json.dumps(res, indent=1))
