"""L-2026-11-10-CCYCURVE — oil only when the curve is tightening AND commodity
currencies are rising (lab original, RESEARCH.md §2b, designed 2026-11-10).

VARIES: L-2026-11-07-CARRYPROXY (potential 4: USO only while USO's 63-day
return beats USL's; +5.5%/yr vs USO -11.4%, worst drop -45% vs -98%) — adds
the R-2026-11-09-CCYCMD demand gate (potential 4: AUD/CAD/CLP/NZD/ZAR vs USD
over 3 months; +4.7%/yr vs DBC +0.6%, worst drop -35% vs -76%).
Sister of L-2026-11-08-OILCURVETREND, which gated the same curve signal with
oil's OWN price trend; this gate is an outside, forward-looking price.

INGREDIENTS / SOURCES:
  * Boons & Porras Prado, "Basis-Momentum", JF 74(1) 2019
    (https://ideas.repec.org/a/bla/jfinan/v74y2019i1p239-279.html) — the curve proxy.
  * Chen, Rogoff & Rossi, "Can Exchange Rates Forecast Commodity Prices?", QJE
    125(3) 2010 (https://econpapers.repec.org/RePEc:oup:qjecon:v:125:y:2010:i:3:p:1145-1194.)
    — commodity currencies discount future commodity demand and move first.

RATIONALE (written before any run): CARRYPROXY's losses came from months when
the front outran the ladder during a demand collapse (late 2008, 2014-15,
early 2020): physical tightness that was about to vanish. Commodity-currency
markets price expected DEMAND (CCYCMD learnings: it worked in demand-driven
cycles and failed in supply shocks). Requiring both — tight physical market
(curve) AND rising expected demand (currencies) — should drop the false
tightening months. The curve leg covers what CCYCMD misses (supply shocks
show up in the curve), the currency leg covers what the curve misses.
Cost: fewer months in the market, lower t.

RULE (fixed before any run):
  at each month-end close i (date D):
    curve_on = USO 63-day return > USL 63-day return            (CARRYPROXY)
    ccy_on   = mean over AUD, CAD, CLP, NZD, ZAR of the 3-month log change of
               the currency's USD value, from the last FX bars dated STRICTLY
               BEFORE D and strictly before the month-end 3 months earlier
               (|x| > 25% dropped, need >= 3 currencies) > 0        (CCYCMD)
    hold 100% USO next month if curve_on AND ccy_on, else T-bills.
  The FX loader, inversion and bad-tick rule are IMPORTED from
  R-2026-11-09-CCYCMD.py (same code); FX never enters the simulated calendar.
Benchmark: buy & hold USO (single-commodity timing rule: the instrument it
times, as CARRYPROXY and OILCURVETREND). Costs 5bp. Start 2007-12-01 (USL
listing; first signal ~2008-03). Includes H2 2008, 2014-16, 2020, 2022.
Variants (neighbours): curve window 42 and 126 days; currency horizon 2 and
4 months.
FAMILY "L-2026-11-07-CARRYPROXY" (lifetime 15 after OILCURVETREND and
CURVEPAIRS) -> trials 15 + 5 = 20. The curve signal is the family's; the
gate is new, so this is a variation of the same hypothesis, not a new one.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("ccycmd", HERE / "R-2026-11-09-CCYCMD.py")
CCY = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CCY)
START = "2007-12-01"


def ccy_signal(me, months):
    """Mean log change vs USD of the commodity currencies between the last FX bars
    dated strictly before me[-1-months] and strictly before me[-1] (CCYCMD's code)."""
    if len(me) <= months:
        return None
    now_d, then_d = me[-1], me[-1 - months]
    xs = []
    for s in CCY.FX:
        a, b = CCY._before(s, then_d), CCY._before(s, now_d)
        if a and b and a > 0 and b > 0:
            x = CCY.FX[s] * math.log(b / a)
            if abs(x) <= CCY.BAD:
                xs.append(x)
    return sum(xs) / len(xs) if len(xs) >= 3 else None


def make(lb=63, months=3):
    st = {"w": {}, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = {}, []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        st["me"].append(dates[i])
        u, l = px["USO"], px["USL"]
        curve_on = (i >= lb and u[i] and u[i - lb] and l[i] and l[i - lb]
                    and u[i] / u[i - lb] > l[i] / l[i - lb])
        s = ccy_signal(st["me"], months) if curve_on else None
        st["w"] = {"USO": 1.0} if (curve_on and s is not None and s > 0) else {}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb42": make(42, 3), "lb126": make(126, 3), "m2": make(63, 2), "m4": make(63, 4)}
    res = rb.evaluate("L-2026-11-10-CCYCURVE", weights, ["USO", "USL"], "USO", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=20,
                      family="L-2026-11-07-CARRYPROXY", variants=variants,
                      notes="month-end: USO next month only if USO 63d return > USL 63d return AND the "
                            "AUD/CAD/CLP/NZD/ZAR basket rose vs USD over 3 months (FX bars strictly before "
                            "the decision day), else T-bills; bench USO; varies L-2026-11-07-CARRYPROXY "
                            "(adds the CCYCMD gate); lab original; vault sealed")
    print(json.dumps(res, indent=1))
