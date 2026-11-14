"""L-2026-11-14-CMDTURN — trend at turning points on broad commodities: half a
position when the slow (12-month) and fast (1-month) trends disagree (lab
original, RESEARCH.md §2b: a variation of the shortlisted DD-2026-11-TREND
block, potential 5). League round 1, commodities desk. Promotes ledger row
I-2026-11-11-CMDTURN to a LAB test (update that row: id L-2026-11-14-CMDTURN,
phase backtest; no second row).

WHY LAB, NOT A REPLICATION (stated before any run): the mechanism comes from
Goulding, Harvey & Mazzoleni, "Momentum turning points", JFE 149(3) 2023
https://econpapers.repec.org/RePEc:eee:jfinec:v:149:y:2023:i:3:p:378-406
(also Garg et al., "Breaking bad trends", FAJ 2021
https://people.duke.edu/~charvey/Research/Published_Papers/P167_Breaking_bad_trends.pdf).
Their headline (the slow/fast blend beats either pure speed on Sharpe across
futures markets, long-short, decades of futures data) needs back-adjusted
futures, which the commodities desk may not use; it CANNOT be reproduced here,
so this script does NOT test GHM. It tests the lab question: does adding a
fast signal (half position in "correction"/"rebound" states) improve the
shortlisted 12-month trend block on the broad commodity ETF? The lead may
veto the slot under quality rule 1 if he reads this as a sourced idea.

HYPOTHESIS (written before any run): 12-month trend on commodities is late at
turning points (2008 H2 top, 2009 H1 bottom, 2014 H2, 2020 Q2, 2022 H2); a
1-month signal halves exposure early in a correction and re-enters half early
in a rebound, cutting the whipsaw cost of pure slow trend. Static 50/50 is
GHM's "intermediate speed" (no fitted dynamic weights).
PASS CRITERION (pre-registered): research_bt verdict PASS vs buy-and-hold DBC
(all §0 gates, >= 70% of the 4 neighbours beating DBC on Sharpe). Learning
value recorded either way: the traits (dd cut, regime Sharpes).

RULE (fixed before any run):
  at each month-end close i (next bar falls in a new month), with m = the
  list of DBC month-end closes seen so far (this one included):
    slow = m[-1] / m[-1-S] - 1   (S = 12 months)
    fast = m[-1] / m[-1-F] - 1   (F = 1 month)
    weight(DBC) = a * 1[slow > 0] + (1 - a) * 1[fast > 0]   (a = 0.5)
    i.e. Bull 1.0, Correction 0.5, Rebound 0.5, Bear 0; rest in T-bills.
  needs S+1 month-end closes (else T-bills); held to the next month-end.
Benchmark: buy & hold DBC. Costs 5bp. Start 2006-02-01 (DBC lists 2006-02-06;
first signal at the 2007-02 month-end; the warm-up year is T-bills — stated).
Includes 2008, 2014-16, 2020, 2022.
DATA TIMING: reads DBC closes dated <= i only (harness guard); month-end test
peeks only at dates[i+1]'s MONTH; weights decided at close i earn
close i -> close i+1.
Variants (neighbours): a = 0.25 / 0.75 (blend toward fast / slow); fast 2
months; slow 9 months.
NEW FAMILY "cmd-turning-points" -> trials 1 + 4 = 5.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "DBC"
START = "2006-02-01"


def make(a=0.5, slow=12, fast=1):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["m"] = []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        if px[SYM][i]:
            st["m"].append(px[SYM][i])
        m = st["m"]
        w = {}
        if len(m) > max(slow, fast) and px[SYM][i]:
            s_up = m[-1] / m[-1 - slow] - 1 > 0
            f_up = m[-1] / m[-1 - fast] - 1 > 0
            x = a * s_up + (1 - a) * f_up
            if x > 0:
                w = {SYM: x}
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"a25": make(0.25), "a75": make(0.75), "fast2": make(0.5, 12, 2),
                "slow9": make(0.5, 9, 1)}
    res = rb.evaluate("L-2026-11-14-CMDTURN", weights, [SYM], SYM, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="cmd-turning-points", variants=variants,
                      notes="month-end: DBC weight = 0.5*1[12m return > 0] + 0.5*1[1m return > 0] (bull 1, "
                            "correction/rebound 0.5, bear 0), rest T-bills; bench DBC; 5bp; lab variation of "
                            "DD-TREND using Goulding-Harvey-Mazzoleni JFE 2023's static intermediate blend (GHM's "
                            "futures headline not reproducible here); promotes I-2026-11-11-CMDTURN")
    print(json.dumps(res, indent=1))
