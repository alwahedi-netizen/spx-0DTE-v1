"""L-2026-11-08-POLICYMOM — lab original (RESEARCH.md §2b), designed
2026-11-08 and queued (69); scripted 2026-11-09. Keeps its ledger id.

SOURCE OF THE MECHANISM: Coibion & Gorodnichenko, "Why Are Target Interest
Rate Changes So Persistent?", AEJ: Macroeconomics 4(4), 2012
(https://www.aeaweb.org/articles?id=10.1257/mac.4.4.126): the Fed smooths
policy (interest-rate inertia), so rate moves come in long runs of small
steps in one direction.

VARIES: I-2026-11-07-FIRSTCUT (one event: extend duration after the first
cut) -> a continuous short-rate DIRECTION signal in both directions.

RATIONALE (written before any run): because the Fed moves in persistent
small steps, a rising 3-month bill yield says more hikes are likely; markets
under-price that persistence often enough that intermediate duration keeps
losing to short duration through the cycle (1994, 2004-06, 2015-18,
2022-23). Outside hiking cycles, hold intermediates and earn the term
premium. Honest risks: hikes priced in advance (2004-06 "conundrum": long
yields fell while bills rose) and late exits after a surprise first hike;
close to CTH's trend leg (graveyard), so CTH's lesson applies.

RULE (fixed before any run; the ledger row's rule):
  * On the first trading day of each month, from the PREVIOUS close (the
    month-end): D = ^IRX at the last month-end minus ^IRX L = 6 month-ends
    earlier (in percentage points; ^IRX quotes % yield). If D > T = +0.25pp
    -> SHY for the month; else IEF. Bought at that day's close. A missing
    ^IRX print (bond-market holiday) uses the last valid print.
  * Warm-up (fewer than L+1 month-ends): IEF (= benchmark).
Benchmark: IEF buy & hold. Costs 3bp. 2002-08+.
Variants: lookback 3 and 9 months (T = 0.25pp); threshold 0 and +0.50pp
(L = 6).
trials = 5 (new family; FIRSTCUT was never run).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-08-POLICYMOM"
SIG, SAFE, BASE = "^IRX", "SHY", "IEF"


def make(lookback=6, thresh=0.25):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], last=None, hold=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        elif dates[i][:7] != dates[i - 1][:7]:
            if st["last"] is not None:                 # last valid ^IRX <= i-1
                st["me"].append(st["last"])
            if len(st["me"]) > lookback:
                d = st["me"][-1] - st["me"][-1 - lookback]
                st["hold"] = SAFE if d > thresh else BASE
        v = px[SIG][i]                                 # joins history AFTER the
        if v is not None:                              # decision above
            st["last"] = v
        h = st["hold"] or BASE
        return {h: 1.0} if px[h][i] else {}
    return weights


weights = make(6, 0.25)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [SIG, SAFE, BASE], BASE, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"L3": make(3, 0.25), "L9": make(9, 0.25),
                              "T0": make(6, 0.0), "T50": make(6, 0.50)},
                    notes="month-start, from the prior month-end: 3-month bill yield up > 0.25pp "
                          "over 6 months (hiking) -> SHY, else IEF; bench IEF; 2002+; lab original "
                          "(policy inertia)")
    print(json.dumps(r, indent=1))
