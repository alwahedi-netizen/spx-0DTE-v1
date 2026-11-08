"""L-2026-11-08-HAVENVOL — safe-haven currencies switched on by global FX
volatility (lab original, RESEARCH.md §2b: cross-signal variation of a
shortlist block).

VARIES: L-2026-11-07-SAFEHAVEN (potential 4) — same havens, but the switch is
the currency market's own stress gauge instead of the S&P 500 trend.

INGREDIENTS:
  * Menkhoff, Sarno, Schmeling & Schrimpf, "Carry Trades and Global Foreign
    Exchange Volatility", Journal of Finance 67(2), 2012
    (https://openaccess.city.ac.uk/id/eprint/3391/1/CTVOL_R3_v4_paper.pdf):
    global FX volatility = monthly average of the cross-currency mean absolute
    daily log return (their eq. 4); low-rate currencies (JPY, CHF) hedge
    against volatility innovations, high-rate currencies lose.
  * Ranaldo & Soderlind (RoF 2010): JPY and CHF are the G10 safe havens.

RATIONALE (written before any run): volatility regimes persist (vol clusters),
so a month whose FX vol is above its trailing norm is likely followed by
another stressed month, in which carry unwinds lift the funding currencies.
Unlike the S&P trend switch, this fires on FX-specific stress (2015 CNY,
2016 Brexit) and reacts within one month.

RULE (fixed before any run):
  * Daily: for each of the 9 G10 USD pairs with prices on both bars,
    |ln(p_k / p_k-1)|; ignore |r| > 10% as bad ticks; average across pairs
    (the day's value). Monthly vol V_t = mean of the month's daily values.
  * At each month-end: if V_t > mean(V_{t-12} .. V_{t-1}) (above its trailing
    12-month norm) -> FXY 50% + FXF 50% next month; else T-bills.
  * Fewer than 12 prior months, or FXY/FXF missing: T-bills.
  * Variants (trailing norm length): 6, 9, 15, 18 months.
Instruments: FXY, FXF (deposit-backed, Schwab-tradeable); Yahoo spot pairs for
the signal only. Benchmark T-bills. asset_class="fx" (2bp). Start 2005-01
(signal warm-up; positions from 2007 when FXY lists).
FAMILY "L-fx-safehaven" -> honest trials 15 (SAFEHAVEN 5 + HAVENRATES 5 + 5).
Data notes: the UK-summer-time stamp shift moves a daily bar by one date but
not its magnitude, so V_t is unaffected except at month boundaries.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

HAVENS = ["FXY", "FXF"]
PAIRS = ["EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X", "USDJPY=X",
         "USDCHF=X", "USDCAD=X", "USDSEK=X", "USDNOK=X"]
SYMS = HAVENS + PAIRS
BAD_TICK = 0.10


def make(norm_months=12):
    st = {"w": None, "day": [], "months": [], "last": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["day"], st["months"], st["last"] = None, [], [], {}
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
        if month_end:
            if st["day"]:
                st["months"].append(sum(st["day"]) / len(st["day"]))
            st["day"] = []
            m = st["months"]
            on = (len(m) >= norm_months + 1 and
                  m[-1] > sum(m[-1 - norm_months:-1]) / norm_months)
            st["w"] = ({h: 1.0 / len(HAVENS) for h in HAVENS}
                       if on and all(px[h][i] for h in HAVENS) else {})
        return st["w"] or {}
    return weights


weights = make(12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-08-HAVENVOL", weights, SYMS, None, start="2005-01-01",
                    asset_class="fx", trials=15, family="L-fx-safehaven",
                    variants={"N6": make(6), "N9": make(9), "N15": make(15), "N18": make(18)},
                    notes="FXY+FXF 50/50 when global FX vol (Menkhoff et al. 2012 mean |daily log ret| of 9 "
                          "G10 pairs, monthly) > its trailing 12-mo mean, else T-bills; monthly; "
                          "varies L-2026-11-07-SAFEHAVEN")
    print(json.dumps(r, indent=1))
