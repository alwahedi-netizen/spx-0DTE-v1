"""L-2026-11-08-SAFEDUR — lab original (RESEARCH.md §2b), designed 2026-11-08
and queued (69, below that night's 5-script cut-off); scripted 2026-11-09.
Keeps its ledger id.

INGREDIENTS: L-2026-11-07-SAFEHAVEN (fx, shortlist 4: havens only while the
S&P 500 is below its 10-month SMA), DD-2026-11-TREND (the trigger);
flight-to-safety evidence Baele, Bekaert, Inghelbrecht & Wei, "Flights to
Safety", RFS 33(2) 2020 (https://doi.org/10.1093/rfs/hhz055): on
flight-to-safety days Treasuries rally while equities fall.

RATIONALE (written before any run): SAFEHAVEN's lesson was that a hedge
sleeve should earn in the regime the equity-trend filter flags. In
deflationary/growth-shock equity bear markets (2001-02, 2008, 2020) long
Treasuries are the asset that rallies hardest; outside them, short
Treasuries keep the sleeve near cash-like risk. So: maximum duration only
while equities trend down. Honest risk: inflation bear markets (2022: stocks
AND long bonds fell, TLT -31%) and V-shaped crashes where the monthly trend
signal is late.

RULE (fixed before any run; the ledger row's rule):
  * On the first trading day of each month, from the PREVIOUS close (the
    month-end): if ^GSPC's last month-end close < the mean of its last
    N = 10 month-end closes (incl. that one) -> TLT for the month; else SHY.
    Bought at that day's close.
  * Warm-up (fewer than N month-ends seen): IEF (= benchmark, no active bet).
Benchmark: IEF buy & hold. Costs 3bp. 2002-08+ (TLT/SHY/IEF inception
2002-07-30; the SMA warms inside the sample, positions from ~2003-06).
VUSTX/VFISX 1991+ would extend history but are NOT used (fund NAVs are for
history only, theme 9).
Variants (SMA neighbours): 6, 8, 12, 14 month-ends.
trials = 10: own 5 + R-2026-11-08-EQCREDIT's 5 (the same S&P 10-month SMA
trigger already tried on the bond book, switching credit instead of
duration). Family: own id. 2-of-2 with CORRDUR's correlation gate is a
SEPARATE idea (L-2026-11-09-SAFEDUR2), not a variant here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-08-SAFEDUR"
SIG, RISKOFF, RISKON, BENCH = "^GSPC", "TLT", "SHY", "IEF"


def make(n=10):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], hold=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
            return {BENCH: 1.0} if px[BENCH][0] else {}
        if dates[i][:7] != dates[i - 1][:7]:
            c = px[SIG][i - 1]
            if c:
                st["me"].append(c)
            if len(st["me"]) >= n:
                down = st["me"][-1] < sum(st["me"][-n:]) / n
                st["hold"] = RISKOFF if down else RISKON
        h = st["hold"] or BENCH
        return {h: 1.0} if px[h][i] else {}
    return weights


weights = make(10)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [SIG, RISKOFF, RISKON], BENCH, start="2002-08-01",
                    asset_class="bonds", trials=10, family=ID,
                    variants={f"SMA{m}": make(m) for m in (6, 8, 12, 14)},
                    notes="month-start, from the prior month-end: S&P 500 below its 10-month SMA "
                          "-> TLT, else SHY; bench IEF; 2002+; lab original (SAFEHAVEN trigger on "
                          "duration)")
    print(json.dumps(r, indent=1))
