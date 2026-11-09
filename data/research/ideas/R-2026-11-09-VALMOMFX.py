"""R-2026-11-09-VALMOMFX — currency value + 12-1 momentum, 50/50 (Asness,
Moskowitz & Pedersen 2013). Promotes ledger row I-2026-11-08-VALMOMFX.

SOURCE: Asness, Moskowitz & Pedersen, "Value and Momentum Everywhere", Journal
of Finance 68(3), 2013 (https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf):
in every asset class incl. currencies, value and momentum are negatively
correlated (about -0.5), so the 50/50 combination has a far higher Sharpe than
either leg; in currencies both legs are weak alone and the combination is the
published way to use them. Supporting: Kroencke, Schindler & Schrimpf, RoF 2014
(FX style combinations diversify).

RATIONALE (written before any run): tonight's ledger has both legs failing
alone on 2009-24 G10 data (R-2026-11-07-FXVALUE Sharpe -0.13; momentum tested
as FXXSMOM at 1-3 months, -0.42). The question AMP answer is not whether each
leg works but whether their negative correlation makes the sum work: value
buys falling currencies (JPY 2021-24), momentum sells them, and the losses
partly cancel. L-2026-11-07-VALTREND tested the lab's VETO form; this is the
published ADDITIVE form, in the same family.

RULE (fixed before any run):
  * Value leg: R-2026-11-07-FXVALUE's weights, imported unchanged (nominal
    5-year reversal: ln(mean USD price 4.5-5.5y ago / today), AMP rank weights
    incl. USD at 0, sum|w| = 1, month-end). No CPI (Yahoo has none).
  * Momentum leg (= ledger row I-2026-11-08-XSMOM12): at each month-end,
    mom_c = ln(USD price of c at month-end t-1 / at month-end t-12) (12-1,
    skip the latest month); USD = 0; AMP rank weights incl. USD, sum|w| = 1;
    USD weight dropped.
  * Combined weight per pair = 0.5 x value + 0.5 x momentum (both legs have
    sum|w| = 1 over the same G10 universe, so equal notional ~ equal risk;
    AMP scale each leg to equal ex-post volatility, which needs hindsight).
    Only when BOTH legs are available; otherwise T-bills. Hold one month.
  * Variants: value 4y or 6y (momentum 12); momentum 9 or 15 months (value 5y).
Benchmark: T-bills. asset_class="fx" (2bp). Spot pairs 2003-12+; value
signals need 5.5 years of prices, so positions start ~2009-06 (as FXVALUE).
FAMILY "fx-value" (FXVALUE 5 + VALTREND 5) -> trials 15.
HARNESS CAVEAT: as FXVALUE — spot pairs earn no interest (AMP use forward
returns, i.e. incl. carry); the book is treated as funded (conservative by
~rf/vol). Momentum here is spot-only, AMP's includes the interest differential.
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


def make(value_years=5.0, mom_months=12):
    val = _fv.make(value_years)
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []          # evaluate() re-simulates: start clean
        vw = val(i, dates, px) or {}              # call every bar: the value leg keeps its own state
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"] or {}
        st["me"].append({c: _fv.usd_price(px, sym, sg, i) for c, (sym, sg) in LEGS.items()})
        me = st["me"]
        mw = {}
        if len(me) >= mom_months + 1:
            scores = {"USD": 0.0}
            for c in LEGS:
                a, b = me[-2].get(c), me[-1 - mom_months].get(c)
                if a and b:
                    scores[c] = math.log(a / b)
            if len(scores) >= 4:
                rw = _fv.rank_weights(scores)
                mw = {LEGS[c][0]: LEGS[c][1] * w for c, w in rw.items() if c != "USD" and w}
        if not vw or not mw:
            st["w"] = {}
            return {}
        out = {}
        for s in set(vw) | set(mw):
            x = 0.5 * vw.get(s, 0.0) + 0.5 * mw.get(s, 0.0)
            if x:
                out[s] = x
        st["w"] = out
        return out
    return weights


weights = make(5.0, 12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-09-VALMOMFX", weights, SYMS, None, start="2003-12-01",
                    asset_class="fx", trials=15, family="fx-value",
                    variants={"V4": make(4.0, 12), "V6": make(6.0, 12),
                              "M9": make(5.0, 9), "M15": make(5.0, 15)},
                    notes="AMP 50/50: FXVALUE rank weights (nominal 5y reversal) + 12-1 momentum rank "
                          "weights (incl. USD), month-end; spot pairs; T-bills bench; family fx-value")
    print(json.dumps(r, indent=1))
