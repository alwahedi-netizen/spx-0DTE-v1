"""L-2026-11-10-DEMANDVOTE — broad commodities only when two forward-looking
demand prices agree: commodity currencies AND the copper/gold ratio (lab
original, RESEARCH.md §2b, designed 2026-11-10).

VARIES: R-2026-11-09-CCYCMD (potential 4; DBC while the AUD/CAD/CLP/NZD/ZAR
basket rose vs USD over 3 months: +4.7%/yr vs DBC +0.6%, worst drop -35% vs
-76%, confidence 90%, held-out Sharpe 0.33 vs 0.36 — lost the held-out window).
Adds a second, independent market-priced growth gauge.

INGREDIENTS / SOURCES:
  * Chen, Rogoff & Rossi, QJE 125(3) 2010
    (https://econpapers.repec.org/RePEc:oup:qjecon:v:125:y:2010:i:3:p:1145-1194.) —
    commodity currencies forecast commodity prices.
  * Copper/gold ratio as a market gauge of global growth expectations (copper
    = industrial demand, gold = fear/real-rate demand): DoubleLine (ledger row
    I-2026-11-08-CUAU, https://doubleline.com/wp-content/uploads/2022/06/) uses
    it for yields; Bakshi, Panayotov & Skoulakis (2011, "The Baltic Dry Index as
    a Predictor of Global Stock Returns, Commodity Returns, and Global Economic
    Activity", https://www.cxoadvisory.com/economic-indicators/baltic-dry-index-as-return-predictor)
    show that a real-activity price's 3-month growth predicts commodity returns
    — the BDI itself is not on Yahoo; copper/gold is the free, daily analogue.

RATIONALE (written before any run): CCYCMD failed where currencies and
commodities moved together for USD reasons (same-month, not lead-lag) and in
supply shocks. Copper/gold is priced in dollars on BOTH legs, so a broad USD
move cancels out of the ratio: a rising ratio says growth expectations rose,
not that the dollar fell. Two growth gauges with different noise agreeing
should cut CCYCMD's false 'on' months (theme 1 logic: two filters agreeing ->
fewer whipsaws, L-SEASONTREND).

RULE (fixed before any run):
  at each month-end close i (date D):
    s1 = CCYCMD's signal: mean 3-month log change vs USD of AUD, CAD, CLP, NZD,
         ZAR (FX bars dated STRICTLY BEFORE D; |x| > 25% dropped; >= 3 ccys) —
         loader and code IMPORTED from R-2026-11-09-CCYCMD.py
    s2 = log change of HG=F / GC=F (Yahoo front-month copper and gold, closes
         dated STRICTLY BEFORE D and strictly before the month-end 3 months
         earlier). Front-month LEVELS are a valid spot proxy over 3 months
         (metals' roll gaps are small; CMDVALUE learnings).
    hold 100% DBC next month if s1 > 0 AND s2 > 0; else T-bills.
  Side data (FX, HG=F, GC=F) is loaded on its own calendar and never enters the
  simulated universe (FX Sunday bars would drop DBC returns — theme 12); the
  strictly-before read costs one day of freshness and can never see a close
  from after D.
Benchmark: buy & hold DBC. Costs 5bp. Start 2006-03-01 (DBC 2006-02; signals
~2006-06). Includes 2008, 2014-16, 2020, 2022.
Variants (neighbours): both horizons 2 and 4 months; copper/gold horizon 2 and
6 months (currency horizon kept at 3).
FAMILY "ccy-predicts-cmd" (lifetime 6 after CCYCMD) -> trials 6 + 5 = 11: the
hypothesis — market-priced demand expectations lead commodities — is CCYCMD's.
"""
import bisect
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
START = "2006-03-01"
METALS = ["HG=F", "GC=F"]
SIDE = {}          # symbol -> (sorted dates, closes); filled once, on first use


def _load():
    if not SIDE:
        d, p = rb.prices(METALS, "2003-01-01")
        for s in METALS:
            pts = [(x, v) for x, v in zip(d, p[s]) if v and v > 0]
            SIDE[s] = ([x for x, _ in pts], [v for _, v in pts])
    return SIDE


def _before(s, d):
    ds, vs = _load()[s]
    k = bisect.bisect_left(ds, d)                  # bars dated strictly before d
    return vs[k - 1] if k > 0 else None


def ccy_signal(me, months):
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


def cuau_signal(me, months):
    if len(me) <= months:
        return None
    now_d, then_d = me[-1], me[-1 - months]
    c0, g0 = _before("HG=F", then_d), _before("GC=F", then_d)
    c1, g1 = _before("HG=F", now_d), _before("GC=F", now_d)
    if not (c0 and g0 and c1 and g1):
        return None
    return math.log((c1 / g1) / (c0 / g0))


def make(m_ccy=3, m_cg=3):
    st = {"w": {}, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = {}, []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        st["me"].append(dates[i])
        w = {}
        if px["DBC"][i]:
            s1 = ccy_signal(st["me"], m_ccy)
            s2 = cuau_signal(st["me"], m_cg) if (s1 is not None and s1 > 0) else None
            if s2 is not None and s2 > 0:
                w = {"DBC": 1.0}
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"m2": make(2, 2), "m4": make(4, 4), "cg2": make(3, 2), "cg6": make(3, 6)}
    res = rb.evaluate("L-2026-11-10-DEMANDVOTE", weights, ["DBC"], "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=11,
                      family="ccy-predicts-cmd", variants=variants,
                      notes="month-end: DBC next month only if the AUD/CAD/CLP/NZD/ZAR basket rose vs USD "
                            "over 3 months AND HG=F/GC=F rose over 3 months (side data strictly before the "
                            "decision day), else T-bills; bench DBC; varies R-2026-11-09-CCYCMD (adds a "
                            "copper/gold gate); lab original; vault sealed")
    print(json.dumps(res, indent=1))
