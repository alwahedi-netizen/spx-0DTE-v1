"""R-2026-11-10-FOMCCYCLE — stock returns over the FOMC cycle: hold the S&P 500
only in the "even weeks" after scheduled FOMC decisions, T-bills otherwise.

Source: Cieslak, Morse & Vissing-Jorgensen (2019) "Stock Returns over the FOMC
Cycle", J. Finance 74(5) 2201-2248, doi 10.1111/jofi.12818
(https://econpapers.repec.org/RePEc:bla:jfinan:v:74:y:2019:i:5:p:2201-2248).
1994-2016: the whole US equity premium over T-bills was earned in weeks 0, 2,
4 and 6 of FOMC cycle time (week 0 starts the day before a scheduled
decision); the pattern holds in three sub-periods and in non-US markets.

RATIONALE (fixed before any run): the Fed's internal meeting schedule
(board meetings, informal communication through the press) releases
policy news biweekly; after market declines that news is systematically
accommodative (the "Fed put"), so the risk premium is paid in those weeks.
Why test it here: theme 11 — small, uncorrelated event edges help the book
— and it is only in the market about half the time, so its correlation to
the book is lower than buy-and-hold equity's. Honest counter-case: the
pre-FOMC drift inside week 0 faded after 2015 (R-2026-11-07-PREFOMC: +0.35%
per trade 2000-15 vs +0.03% 2016-26). The paper's sample ends 2016: 2017-24
is out-of-sample for the published result, and the held-out window (last
30% of 2000-24) covers it.

RULE (fixed before any run):
  * FOMC dates = the scheduled-decision list already in the ledger
    (R-2026-11-07-PREFOMC.py, federalreserve.gov; unscheduled meetings
    excluded — they are not known in advance).
  * Cycle day of each trading day j (offsets in trading days of the price
    calendar, which is known in advance): if j is the trading day before a
    scheduled decision, cycle day = -1 (week 0); else cycle day d = j minus
    the index of the most recent scheduled decision day (d >= 0). Week
    k = floor((d + 1) / 5): week 0 = days -1..3, week 1 = 4..8,
    week 2 = 9..13, week 4 = 19..23, week 6 = 29..33 (the paper's
    definition).
  * Weights decided at close i: SPY 1.0 if day i+1 is in an EVEN week
    0, 2, 4 or 6 (so the position earns close(i) -> close(i+1)); else
    T-bills. Days after week 6 that are not the next meeting's day -1 are
    out.
  * Variants (robustness gate): whole cycle shifted one trading day earlier
    and one later; even weeks {0, 2, 4} only; {2, 4, 6} only (drops week 0,
    i.e. the known pre-FOMC drift — does the biweekly pattern stand without
    it?). ({0,...,8} was dropped before any run: synthetic check showed it
    is 99.6% identical to the main rule — cycles rarely reach week 8.)
  * Benchmark SPY, 5bp/side (stocks cost; ~22 round trips a year = ~44
    turnover units = ~2.2%/yr at 5bp — SPY really costs ~1bp, so the 5bp
    class default is conservative; the 2x-cost gate doubles it), Yahoo
    SPY (an ETF timing rule, not a single-stock universe), 2000-01 -> vault,
    strict bar + FF5+Mom alpha gate (asset_class "stocks").
  * family "fomc-cycle" (new; PREFOMC and FOMCTSY are other families, but
    week 0 contains PREFOMC's day): trials = 1 + 4 = 5.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-10-FOMCCYCLE"
SYM = "SPY"

_spec = importlib.util.spec_from_file_location(
    "prefomc", Path(__file__).resolve().parent / "R-2026-11-07-PREFOMC.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FOMC = set(_mod.FOMC)


def even_days(dates, weeks=(0, 2, 4, 6), shift=0, fomc=None):
    """Indexes of `dates` that fall in the given FOMC-cycle weeks. shift moves
    the whole cycle by trading days (-1 = one day earlier)."""
    fomc = FOMC if fomc is None else fomc
    meet = [k for k, d in enumerate(dates) if d in fomc]
    out, m = set(), 0
    for j in range(len(dates)):
        while m < len(meet) and meet[m] <= j:
            m += 1
        nxt = meet[m] if m < len(meet) else None      # next decision strictly after j
        last = meet[m - 1] if m > 0 else None         # most recent decision on/before j
        if nxt is not None and j == nxt - 1:
            week = 0
        elif last is not None:
            week = (j - last + 1) // 5
        else:
            continue
        if week in weeks and 0 <= j + shift < len(dates):
            out.add(j + shift)
    return out


def make(weeks=(0, 2, 4, 6), shift=0):
    st = {"key": None, "hold": set()}

    def weights(i, dates, px):
        if i == 0 or st["key"] != (len(dates), dates[0]):   # fresh state for every simulation
            st["key"] = (len(dates), dates[0])
            st["hold"] = even_days(dates, weeks, shift)
        if i + 1 < len(dates) and (i + 1) in st["hold"] and px[SYM][i]:
            return {SYM: 1.0}
        return {}
    return weights


weights = make()
VARIANTS = {"shift_m1": make(shift=-1), "shift_p1": make(shift=1),
            "weeks024": make(weeks=(0, 2, 4)), "weeks246": make(weeks=(2, 4, 6))}


if __name__ == "__main__":
    import json
    out = rb.evaluate(ID, weights, [SYM], SYM, start="2000-01-01", asset_class="stocks",
                      trials=5, family="fomc-cycle", variants=VARIANTS,
                      notes=("Cieslak-Morse-Vissing-Jorgensen FOMC cycle: SPY only in even weeks 0/2/4/6 of "
                             "FOMC cycle time (week 0 = day before a scheduled decision to day +3), T-bills "
                             "otherwise; scheduled dates from PREFOMC.py; variants shift -1/+1 day, weeks "
                             "{0,2,4}, {2,4,6}"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
