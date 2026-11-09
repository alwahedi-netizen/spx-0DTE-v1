"""R-2026-11-09-DOLVOL — buy the G10 currency basket against the dollar after
global FX volatility rises (Qiao & Wang, Journal of Empirical Finance 2026).

SOURCE: Qiao Fang & Wang Tianyi, "Global currency volatility risk and currency
return predictability", Journal of Empirical Finance, Aug 2026,
doi:10.1016/j.jempfin.2026.101740 (abstract via
https://sbf.uibe.edu.cn/xsyj/xscg/e8d0fdc76a064ddabe63ffeadf49da1d.htm; the
ScienceDirect page returned 403): global currency volatility = equal-weighted
average of option-implied or REALIZED volatility of 17 major currencies; it
"significantly and positively predicts currency returns, especially for
horizons beyond three months"; out-of-sample R2 3.5-10.1% with realized vol;
the measure tracks US activity, uncertainty and the VIX.
LAB READING (flagged, not confirmed from the full text): "currency returns" =
the average return of foreign currencies vs USD (the dollar factor, Lustig-
Roussanov-Verdelhan RFS 2011), i.e. the dollar risk premium is high after
volatility rises (countercyclical premium, Lustig-Roussanov-Verdelhan JFE
2014). If the full text says the target is a carry/HML portfolio instead, this
script tests the wrong target and must be re-logged, not re-tuned.

RATIONALE (written before any run): when global FX volatility jumps,
constrained dollar intermediaries demand a higher premium to hold foreign
currency; the dollar overshoots and foreign currencies earn the premium back
over the following quarters. Different bet from L-2026-11-08-HAVENVOL, which
buys only yen/franc when vol rises: this holds the whole basket (incl. the
high-beta AUD/GBP/CAD) and for three months, betting on the premium, not on
the haven.

RULE (fixed before any run):
  * V_t (as HAVENVOL): daily mean of |ln return| across the 9 G10 USD pairs
    (ignore |r| > 10%), averaged over the calendar month.
  * At each month-end t: signal_t = 1 if V_t > mean(V_{t-12} .. V_{t-1}),
    else 0 (realized-vol measure only; Yahoo has no FX implied vol).
  * Exposure next month = (signal_t + signal_{t-1} + signal_{t-2}) / 3 —
    overlapping 3-month holding (Jegadeesh-Titman style) for the paper's
    ">3 months" horizon.
  * Basket: equal weight over the CurrencyShares trusts listed that day among
    FXE FXY FXF FXA FXB FXC (deposit-backed: each earns its currency's deposit
    rate minus 0.40%, so the harness return is the currency's true excess
    return over T-bills; spot pairs would earn nothing). Rest in T-bills.
  * Variants (vol norm): 6, 9, 15, 18 months.
Benchmark: T-bills. asset_class="fx" (2bp). Start 2005-01 (vol warm-up;
FXE 2005-12, FXF/FXA/FXB/FXC 2006-06, FXY 2007-02).
FAMILY "fx-dolvol" (new) -> trials 5. NB it shares HAVENVOL's switch: expect
correlated results; compare with portfolio.marginal, not side by side.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ETFS = ["FXE", "FXY", "FXF", "FXA", "FXB", "FXC"]
PAIRS = ["EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X", "USDJPY=X",
         "USDCHF=X", "USDCAD=X", "USDSEK=X", "USDNOK=X"]
SYMS = ETFS + PAIRS
BAD_TICK = 0.10
HOLD = 3


def make(norm_months=12):
    st = {"w": None, "day": [], "months": [], "last": {}, "sig": []}

    def weights(i, dates, px):
        if i == 0:
            st.update(w=None, day=[], months=[], last={}, sig=[])
        absr = []
        for p in PAIRS:
            v = px[p][i]
            prev = st["last"].get(p)
            if v and prev:
                r = abs(math.log(v / prev))
                if r <= BAD_TICK:
                    absr.append(r)
            if v:
                st["last"][p] = v
        if len(absr) >= 5:
            st["day"].append(sum(absr) / len(absr))
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"] or {}
        if st["day"]:
            st["months"].append(sum(st["day"]) / len(st["day"]))
        st["day"] = []
        m = st["months"]
        st["sig"].append(int(len(m) >= norm_months + 1 and
                             m[-1] > sum(m[-1 - norm_months:-1]) / norm_months))
        expo = sum(st["sig"][-HOLD:]) / HOLD
        live = [e for e in ETFS if px[e][i]]
        st["w"] = {e: expo / len(live) for e in live} if expo and live else {}
        return st["w"]
    return weights


weights = make(12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-09-DOLVOL", weights, SYMS, None, start="2005-01-01",
                    asset_class="fx", trials=5, family="fx-dolvol",
                    variants={"N6": make(6), "N9": make(9), "N15": make(15), "N18": make(18)},
                    notes="Qiao-Wang JEF 2026: equal-weight 6 CurrencyShares trusts, exposure = share of the "
                          "last 3 month-ends with global FX realized vol above its 12-mo norm; else T-bills")
    print(json.dumps(r, indent=1))
