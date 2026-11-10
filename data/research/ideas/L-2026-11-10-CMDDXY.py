"""L-2026-11-10-CMDDXY — commodity currencies vs the DXY basket, held only while
commodities trend up (lab original, RESEARCH.md §2b: conditioning a sourced
premium on the regime its own source says drives it).

INGREDIENTS:
  * R-2026-11-10-RRWCMD (Ready-Roussanov-Ward JF 2017, NBER w19371): the
    commodity-exporter vs finished-goods-exporter spread; the paper finds
    their commodity strategy explains "all of [carry's] pro-cyclical
    predictability with commodity prices and shipping costs".
  * Bakshi & Panayotov, "Predictability of currency carry trades and asset
    pricing implications", JFE 110(1) 2013
    (https://econpapers.repec.org/RePEc:eee:jfinec:v:110:y:2013:i:1:p:139-163):
    past commodity-index returns predict carry-trade returns out of sample.
  * DD-2026-11-TREND (10-month SMA as the regime switch; potential 5).
VARIES: L-2026-11-07-CARRYTREND (FAIL: FXA only above the S&P's 10-mo SMA;
-0.6%/yr, worst drop -46%) — two fixes for its stated failure: (1) the gate is
the commodity trend (the driver the sources name) instead of the equity trend;
(2) the USD exposure is hedged by the UUP leg, so the position is commodity vs
finished-goods currencies, not AUD vs USD (CARRYTREND's -46% drop was mostly
the 2008 / 2014-15 dollar rallies).

RATIONALE (written before any run): the commodity-currency premium is paid for
global productivity/commodity risk; when commodity prices fall persistently
(2008, 2014-15) the trade-based carry crashes. A slow trend gate on commodities
should sidestep most of those episodes while keeping the premium in commodity
up-cycles (2009-11, 2016-18, 2021-22).

RULE (fixed before any run):
  * At each month-end close: on = DBC > mean of its last N = 10 month-end
    closes (incl. this one); fewer than N month-ends -> off.
  * Next month: if on -> FXA 25% + FXC 25% + UUP 50% (exactly R-2026-11-10-
    RRWCMD's book; target weights re-set daily), else T-bills. Off also when
    any of the three has no price.
  * Variants (SMA length +-20% / +-50%): N = 5, 8, 12, 15.
Benchmark: T-bills. asset_class="fx" (2bp). Start 2006-03-01 (DBC 2006-02;
UUP 2007-03 -> positions from 2007-03).
FAMILY "L-fx-carryguard" (CARRYTREND 5) -> trials 10.
EXPECTED WEAKNESS: trend gates lag turning points (theme 1: they cut crashes,
rarely add return); DBC is ~55% energy, so the gate is mostly an oil trend
(fits CAD, less so AUD, whose drivers are iron ore and coal).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BOOK = {"FXA": 0.25, "FXC": 0.25, "UUP": 0.50}
GATE = "DBC"
SYMS = list(BOOK) + [GATE]


def make(sma_months=10):
    st = {"me": [], "w": {}}

    def weights(i, dates, px):
        if i == 0:
            st.update(me=[], w={})                    # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        g = px[GATE][i]
        if g:
            st["me"].append(g)
        me = st["me"]
        on = len(me) >= sma_months and me[-1] > sum(me[-sma_months:]) / sma_months
        st["w"] = dict(BOOK) if (on and all(px[s][i] for s in BOOK)) else {}
        return st["w"]
    return weights


weights = make(10)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-10-CMDDXY", weights, SYMS, None, start="2006-03-01",
                    asset_class="fx", trials=10, family="L-fx-carryguard",
                    variants={"N5": make(5), "N8": make(8), "N12": make(12), "N15": make(15)},
                    notes="FXA 25% + FXC 25% + UUP 50% (commodity vs finished-goods currencies, RRW 2017) "
                          "only when DBC > its 10-month SMA at month-end, else T-bills")
    print(json.dumps(r, indent=1))
