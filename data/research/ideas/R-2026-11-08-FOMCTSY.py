"""R-2026-11-08-FOMCTSY — own Treasuries only in the 3-day window around
scheduled FOMC decisions.

SOURCES:
  * Hillenbrand, "The Fed and the Secular Decline in Interest Rates", Review
    of Financial Studies 38 (2025), doi 10.1093/rfs/hhae089 (summary:
    https://quantpedia.com/secular-decline-in-yields-around-fomc-meetings/):
    essentially the whole 1980-2017 fall in the 10-year yield (10.1% -> 2.4%)
    happened in a 3-day window around FOMC meetings (day before, decision day,
    day after); yields drifted sideways the rest of the time. Driven mostly by
    a lower expected short-rate path (forward guidance, dot plot).
  * Pan & Peng, "The Pre-FOMC Drift and the Secular Decline in Long-Term
    Interest Rates" (AEA 2026 / SAIF WP, Dec 2025,
    https://ftp.aeaweb.org/conference/2026/program/paper/nNSh7NKz): the 10y
    yield falls a significant 0.79bp on the day BEFORE the announcement
    (vs -0.04bp average day), 1989-2025; a term-premium (risk) channel.

RATIONALE: if long-rate news is released on a known schedule and a premium
is paid for carrying duration risk through it, holding duration only around
the schedule should earn most of the duration return at a fraction of the
time (and of the drawdowns). Honest counter-case: the secular decline ENDED
in 2020-22; if the window only harvested a one-way trend in yields, it
breaks in a rising-rate regime. Different asset and window from
R-2026-11-07-PREFOMC (equity, faded after 2015) and R-2026-11-07-FOMCUSD
(dollar on the decision day only).

RULE (fixed before any run):
  * FOMC dates = the scheduled-decision list already in the ledger
    (R-2026-11-07-PREFOMC.py, from federalreserve.gov; unscheduled meetings
    are excluded because they cannot be known in advance).
  * Window = trading days D-1, D, D+1 around each decision day D (offsets in
    trading days of the price calendar; the exchange calendar is known in
    advance, so only `dates`, never prices, are read ahead).
  * Weights decided at close i: IEF 1.0 if the NEXT bar (i+1) is in the
    window, i.e. the position earns close(D-2)->close(D+1); else T-bills.
Benchmark: IEF buy & hold (class benchmark). Costs 3bp (bonds), ~16 one-way
trades a year. 2002-08+ (IEF inception).
Variants (neighbouring windows): PRE [-1] only (Pan-Peng), [-1,0], [0,+1],
[-2..+2]. trials = 5 (new family; FOMCUSD/PREFOMC are other families).
Red-team flags: a decision day that falls on a holiday-shortened week;
regime dependence on 2008-2020 (QE announcements); IEF vs 10y zero yields.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-08-FOMCTSY"
SYM = "IEF"

_spec = importlib.util.spec_from_file_location(
    "prefomc", Path(__file__).resolve().parent / "R-2026-11-07-PREFOMC.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FOMC = set(_mod.FOMC)


def window_days(dates, offsets, fomc=None):
    """Set of indexes k in `dates` that lie at trading-day offset o in
    `offsets` from a scheduled FOMC decision day present in `dates`."""
    fomc = FOMC if fomc is None else fomc
    out = set()
    for k, d in enumerate(dates):
        if d in fomc:
            for o in offsets:
                if 0 <= k + o < len(dates):
                    out.add(k + o)
    return out


def make(offsets=(-1, 0, 1)):
    st = {"key": None, "hold": set()}

    def weights(i, dates, px):
        if i == 0 or st["key"] != (len(dates), dates[0]):
            st["key"] = (len(dates), dates[0])
            st["hold"] = window_days(dates, offsets)
        if i + 1 < len(dates) and (i + 1) in st["hold"] and px[SYM][i]:
            return {SYM: 1.0}
        return {}
    return weights


weights = make((-1, 0, 1))

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [SYM], SYM, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"PRE": make((-1,)), "PRE_DAY": make((-1, 0)),
                              "DAY_POST": make((0, 1)), "WIDE5": make((-2, -1, 0, 1, 2))},
                    notes="IEF only over the 3 trading days around scheduled FOMC decisions "
                          "(earns close D-2 -> close D+1), else T-bills; bench IEF; 2002+; "
                          "variants = windows")
    print(json.dumps(r, indent=1))
