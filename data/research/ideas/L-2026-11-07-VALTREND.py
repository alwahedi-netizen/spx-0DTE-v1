"""L-2026-11-07-VALTREND — FX value with a trend veto (lab original, queued
2026-11-07; scripted 2026-11-08 under its ledger id).

INGREDIENTS:
  * R-2026-11-07-FXVALUE (AMP 2013 currency value: nominal 5-year reversal,
    rank-weighted incl. USD). Its weights are imported unchanged from
    R-2026-11-07-FXVALUE.py, so this differs from the baseline ONLY by the veto.
  * P-FX CARRY-V's veto (drop a leg that fights the currency's own 12-1 trend),
    canon Moskowitz-Ooi-Pedersen (JFE 2012); value x momentum are negatively
    correlated (Asness-Moskowitz-Pedersen, JF 2013,
    https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf).

RATIONALE (written before any run): plain value buys currencies that are still
falling (JPY 2021-24 in the FXVALUE learnings row). Keeping a value leg only
once the currency's own trend agrees should skip the falling-knife phase and
keep the reversion phase.

RULE (fixed before any run):
  * Each day, compute R-2026-11-07-FXVALUE's 5-year weights (month-end rebalance).
  * At each month-end, for each currency c: trend_c = sign(ln(USD price of c at
    month-end t-1 / at month-end t-12)) (12-1). Track month-end USD prices from
    the start of data.
  * Zero any value leg whose sign (in currency terms, i.e. long the currency vs
    USD > 0) differs from trend_c, or whose trend is not yet defined. NO
    re-scaling of the surviving legs (the gross shrinks; cash earns T-bills).
  * Variants (trend lookback, value fixed at 5y): 6, 9, 15, 18 months.
Benchmark: T-bills. asset_class="fx" (2bp). Spot pairs from 2003-12.
FAMILY "fx-value" (shared with FXVALUE, which ran 5 trials) -> trials 10.
REVISIT NOTE: the 11-07 learnings row said "revisit when FXVALUE shows potential
>= 3"; FXVALUE scored potential 1. Scripted anyway at the lead's request
(queue item) — the shared family charges the extra attempt to the DSR bar.
HARNESS CAVEAT: as FXVALUE — spot pairs earn no interest; a long/short book is
treated as funded (Sharpe conservative by ~rf/vol).
"""
import importlib.util
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "fxvalue", Path(__file__).resolve().parent / "R-2026-11-07-FXVALUE.py")
_fv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fv)

LEGS = _fv.LEGS
SYMS = _fv.SYMS
SIGN = {sym: sg for sym, sg in LEGS.values()}


def make(trend_months=12, value_years=5.0):
    base = _fv.make(value_years)
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []      # evaluate() re-simulates: start clean
        bw = base(i, dates, px) or {}         # call every bar: base keeps its own state
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            st["me"].append({sym: _fv.usd_price(px, sym, sg, i) for sym, sg in LEGS.values()})
            me = st["me"]
            out = {}
            for sym, w in bw.items():
                if not w:
                    continue
                trend = 0
                if len(me) >= trend_months + 1:
                    a, b = me[-2].get(sym), me[-1 - trend_months].get(sym)
                    if a and b:
                        x = math.log(a / b)
                        trend = (x > 0) - (x < 0)
                ccy_sign = 1 if SIGN[sym] * w > 0 else -1     # +1 = long the currency vs USD
                if trend == ccy_sign:
                    out[sym] = w
            st["w"] = out
        return st["w"] or {}
    return weights


weights = make(12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-07-VALTREND", weights, SYMS, None, start="2003-12-01",
                    asset_class="fx", trials=10, family="fx-value",
                    variants={"T6": make(6), "T9": make(9), "T15": make(15), "T18": make(18)},
                    notes="FXVALUE (AMP nominal 5y reversal) legs kept only when the currency's own 12-1 "
                          "trend agrees; no re-scaling; monthly; spot pairs; T-bills bench; family fx-value")
    print(json.dumps(r, indent=1))
