"""R-2026-11-09-CCYCMD — commodity currencies forecast commodity prices
(Chen, Rogoff & Rossi 2010), long/flat ETF form.

Source: Yu-Chin Chen, Kenneth Rogoff & Barbara Rossi, "Can Exchange Rates
Forecast Commodity Prices?", Quarterly Journal of Economics 125(3), 2010,
1145-1194 (https://econpapers.repec.org/RePEc:oup:qjecon:v:125:y:2010:i:3:p:1145-1194. ;
NBER w13901 https://nber.org/papers/w13901): the exchange rates of five
commodity exporters (Australia, Canada, Chile, New Zealand, South Africa)
forecast global commodity price indices in and out of sample (quarterly data,
one-quarter-ahead); the reverse (commodities -> currencies) is not robust.
De-dup: I-2026-11-07-CMDFX and I-2026-11-07-CTOT are the REVERSE direction
(commodity prices -> currencies); this row trades commodities.

Rationale (the paper's): exchange rates are forward-looking asset prices that
discount expected future commodity export earnings, while commodity spot prices
are set by current physical imbalances; currency markets therefore move first.
An appreciation of the commodity currencies (vs USD) predicts higher commodity
prices next quarter.

RULE (fixed before any run; our long/flat operationalisation of the paper's
predictive regression — the paper does not publish a trading rule):
  at each month-end close i (date D):
    for each of AUD, CAD, CLP, NZD, ZAR: x = log change of the currency's USD
      value between the last Yahoo FX bars dated STRICTLY BEFORE D and strictly
      before the month-end date 3 months earlier (AUDUSD/NZDUSD as quoted;
      USDCAD/USDCLP/USDZAR inverted)
      (|x| > 25% is treated as a bad tick and dropped)
    s = mean of the available x (need >= 3 currencies)
    if s > 0: hold 100% DBC next month; else T-bills
  The FX bars are read one bar early on purpose: Yahoo stamps FX bars a day
  early in UK summer time (KNOWLEDGE theme 12), so "strictly before D" can never
  read a close from after D. FX series are loaded on their own calendar and do
  not enter the simulated universe (FX trades Sundays/holidays; mixing calendars
  would drop DBC returns — theme 12).
Benchmark: buy & hold DBC. Costs 5bp. Start 2006-03-01 (DBC 2006-02; signals
from ~2006-06). Includes 2008, 2014-16, 2020, 2022.
Variants (neighbours of the 3-month horizon): 1, 2, 4, 6 months; plus the G10
only basket (AUD, CAD, NZD). trials = 6 (new family "ccy-predicts-cmd").
"""
import bisect
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

FX = {"AUDUSD=X": +1, "NZDUSD=X": +1, "USDCAD=X": -1, "USDCLP=X": -1, "USDZAR=X": -1}
G10 = ["AUDUSD=X", "NZDUSD=X", "USDCAD=X"]
BAD = 0.25
SIDE = {}          # pair -> (sorted dates, closes); filled once, on first use


def _load():
    if not SIDE:
        d, p = rb.prices(list(FX), "2003-01-01")
        for s in FX:
            pts = [(x, v) for x, v in zip(d, p[s]) if v]
            SIDE[s] = ([x for x, _ in pts], [v for _, v in pts])
    return SIDE


def _before(s, d):
    ds, vs = _load()[s]
    k = bisect.bisect_left(ds, d)                  # bars dated strictly before d
    return vs[k - 1] if k > 0 else None


def make(months=3, pairs=tuple(FX)):
    st = {"w": {}, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = {}, []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        st["me"].append(dates[i])
        me = st["me"]
        w = {}
        if len(me) > months and px["DBC"][i]:
            now_d, then_d = me[-1], me[-1 - months]
            xs = []
            for s in pairs:
                a, b = _before(s, then_d), _before(s, now_d)
                if a and b and a > 0 and b > 0:
                    x = FX[s] * math.log(b / a)
                    if abs(x) <= BAD:
                        xs.append(x)
            if len(xs) >= 3 and sum(xs) / len(xs) > 0:
                w = {"DBC": 1.0}
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"m1": make(1), "m2": make(2), "m4": make(4), "m6": make(6),
                "g10only": make(3, tuple(G10))}
    res = rb.evaluate("R-2026-11-09-CCYCMD", weights, ["DBC"], "DBC", start="2006-03-01",
                      cost_bps=5.0, asset_class="commodities", trials=6,
                      family="ccy-predicts-cmd", variants=variants,
                      notes="month-end: DBC next month if the mean 3-month log change vs USD of AUD/CAD/CLP/"
                            "NZD/ZAR (Yahoo FX, bars strictly before the decision date) > 0, else T-bills; "
                            "bench DBC; Chen-Rogoff-Rossi QJE 2010 long/flat form")
    print(json.dumps(res, indent=1))
