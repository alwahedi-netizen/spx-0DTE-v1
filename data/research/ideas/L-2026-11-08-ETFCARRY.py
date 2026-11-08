"""L-2026-11-08-ETFCARRY — G10 carry from interest rates IMPLIED by the
CurrencyShares trusts (lab original, RESEARCH.md §2b).

THE TRICK: each CurrencyShares trust (FXE, FXY, FXF, FXA, FXB, FXC) holds a
foreign-currency deposit; its Yahoo adjusted close = spot x (1 + deposit
interest - 0.40% fee, distributions reinvested). So
    ln(ETF_adj / USD price of the currency)
drifts at (deposit rate - fee) per year. Its 12-month change is a free,
daily, Yahoo-only estimate of each currency's realised short rate — the data
the ledger said was missing for every FX carry idea (theme 12: "no FRED
rates", I-2026-11-07-DOLCARRY / VIXCARRY / FACTMOM / P-FX CARRY).

INGREDIENTS: currency carry canon — Lustig, Roussanov & Verdelhan, "Common
Risk Factors in Currency Markets", RFS 2011
(https://www.nber.org/papers/w14082); Koijen, Moskowitz,
Pedersen & Vrugt, "Carry", JFE 2018. Lab shortlist context: L-2026-11-07-
CARRYTREND (AUD-only carry guarded by equity trend) failed at potential 0 —
this tests carry as a RANKING, which is the published form.

RATIONALE (written before any run): high-rate currencies pay a risk premium
(crash risk, global-vol beta). Rates are persistent, so last year's realised
deposit yield is a fair estimate of next month's. Long-only and deposit-backed
means no shorting, no funding error, and the ETF's own price includes the
carry, so the harness measures the true total return (theme 12 caveat on spot
pairs does not apply).

RULE (fixed before any run):
  * Pairs: FXE/EURUSD=X, FXY/USDJPY=X, FXF/USDCHF=X, FXA/AUDUSD=X,
    FXB/GBPUSD=X, FXC/USDCAD=X (USD-quoted pairs inverted to USD per unit).
  * At each month-end close i: g_k(t) = mean of ln(ETF_adj/usdspot) over the
    last 21 bars where both exist (smooths the ETF 16:00 ET vs FX close
    mismatch and the UK-summer-time stamp shift); carry_k = (g_k(i) - g_k(i-L))
    / (calendar years between the two window ends), L = 252 bars.
  * US rate = mean of ^IRX over the last 21 bars / 100.
  * Hold the 2 highest-carry currencies at 50% each, but only those whose
    carry_k > US rate (positive carry vs T-bills after the trust fee); unused
    weight sits in T-bills. Hold one month.
  * Variants (carry lookback L, +-25%/+-50%): 126, 189, 315, 378 bars.
Benchmark: T-bills. asset_class="fx" (2bp). Start 2006-06 (FXF/FXA/FXB/FXC
listed mid-2006, FXY 2007-02); first signals mid-2007 (includes 2008 carry
crash).
FAMILY "L-fx-etfcarry"; honest trials 10 = CARRYTREND's 5 (the lab's prior
carry attempt) + this + 4 variants.
RED-TEAM NOTES (before the run): distributions appear in adjclose on the
ex-date (monthly, lumpy) — the 21-bar smoothing and 12-month window absorb it;
check for trust reverse splits / data gaps in FXY and FXF.
"""
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

PAIRS = {"FXE": ("EURUSD=X", 1), "FXY": ("USDJPY=X", -1), "FXF": ("USDCHF=X", -1),
         "FXA": ("AUDUSD=X", 1), "FXB": ("GBPUSD=X", 1), "FXC": ("USDCAD=X", -1)}
ETFS = list(PAIRS)
SYMS = ETFS + [p for p, _ in PAIRS.values()] + ["^IRX"]
SMOOTH = 21
TOP = 2


def _g(px, etf, end):
    """Mean ln(ETF/usdspot) over the last SMOOTH bars ending at `end` (both present)."""
    pair, sg = PAIRS[etf]
    vals = []
    for k in range(max(0, end - SMOOTH + 1), end + 1):
        e, s = px[etf][k], px[pair][k]
        if e and s:
            usd = s if sg > 0 else 1.0 / s
            vals.append(math.log(e / usd))
    return sum(vals) / len(vals) if len(vals) >= SMOOTH // 2 else None


def make(lookback=252):
    st = {"w": None}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = None                    # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"] or {}
        j = i - lookback
        if j < SMOOTH:
            st["w"] = {}
            return {}
        yrs = (date.fromisoformat(dates[i]) - date.fromisoformat(dates[j])).days / 365.25
        irx = [px["^IRX"][k] for k in range(i - SMOOTH + 1, i + 1)]
        irx = [v for v in irx if v is not None]
        if not irx or yrs <= 0:
            st["w"] = {}
            return {}
        us = sum(irx) / len(irx) / 100.0
        carry = {}
        for etf in ETFS:
            a, b = _g(px, etf, i), _g(px, etf, j)
            if a is not None and b is not None and px[etf][i]:
                carry[etf] = (a - b) / yrs
        best = sorted(carry, key=lambda e: carry[e], reverse=True)[:TOP]
        st["w"] = {e: 1.0 / TOP for e in best if carry[e] > us}
        return st["w"]
    return weights


weights = make(252)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-08-ETFCARRY", weights, SYMS, None, start="2006-06-01",
                    asset_class="fx", trials=10, family="L-fx-etfcarry",
                    variants={"L126": make(126), "L189": make(189), "L315": make(315), "L378": make(378)},
                    notes="Top-2 of 6 CurrencyShares trusts by implied deposit carry (12m drift of ln(ETF/spot)), "
                          "held only if carry > ^IRX; monthly; long-only, deposit-backed; T-bills bench; "
                          "lab original (LRV 2011 carry x ETF-implied rates)")
    print(json.dumps(r, indent=1))
