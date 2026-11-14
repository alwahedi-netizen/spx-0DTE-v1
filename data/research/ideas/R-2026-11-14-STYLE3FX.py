"""R-2026-11-14-STYLE3FX — REPLICATION: G10 currency multi-style (value +
momentum + carry, equal weight) on carry-inclusive returns, checked month by
month against the SOURCE'S OWN published series (AQR "Century of Factor
Premia, Monthly", columns "Currencies Value / Momentum / Carry / Multi-style").

SOURCE: Ilmanen, Israel, Moskowitz, Thapar & Lee, "How Do Factor Premia Vary
Over Time? A Century of Evidence", Journal of Investment Management 19(4)
2021 (SSRN 3400998); data, rebuilt monthly by AQR:
https://www.aqr.com/Insights/Datasets/Century-of-Factor-Premia-Monthly
(file: https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Century-of-Factor-Premia-Monthly.xlsx).
Supporting: Kroencke, Schindler & Schrimpf, "International Diversification
Benefits with Foreign Exchange Investment Styles", Review of Finance 18(5)
2014 — FX styles diversify an equity/bond book.
In AQR's file, 1979-2008: currency value Sharpe 0.71, momentum 0.28, carry
0.52, multi-style 0.76. On OUR overlap 2009-06 .. 2024-10 (185 months):
value 0.15, momentum -0.10, carry 0.28, multi-style 0.19 (2017-24: -0.05).
Varies nothing in the ledger directly: L-2026-11-09-FXSTYLE (same three
styles, equal risk) was REJECTED unrun because no carry ranking existed;
FRED's OECD 3-month rates now supply it (as in L-2026-11-10-OECDCARRY), and
harness fix 2 makes the short legs fair. Every earlier carry test was long-
only trusts or DXY-funded; this is the first dollar-neutral G10 carry leg.

HYPOTHESIS (written before any run): our construction reproduces the
source's published currency multi-style series on the overlap (so a fair FX
style book can be built in research_bt), and the book is a low-correlation
building block (AQR: FX styles are nearly uncorrelated with equities) even
though its standalone Sharpe on this window (~0.2 in the source) cannot pass
the t >= 3 gate. Its use, if any, is via portfolio.marginal.

PASS CRITERION (pre-registered, two separate questions):
  A. REPLICATION: over the months 2009-06 .. 2024-10 in which the book holds
     positions, our monthly excess return correlates >= 0.50 with AQR's
     "Currencies Multi-style", AND our annualised Sharpe of those months is
     within +/- 0.30 of AQR's over the same months. Both -> "replicated";
     else "harness/data suspect" (log it; no FX style variant is tested).
  B. STRATEGY: research_bt verdict vs T-bills (§4 + world-class gates).
     Pre-stated expectation: FAIL. Shortlist claim (potential >= 3) needs:
     positive active return overall AND in the recent half, and correlation
     <= 0.3 to the book (the lead's portfolio.marginal).
DATA-TIMING: signals read only month-end bar i. Value and momentum exactly
as R-2026-11-14-VMEFX (spot `=X` true closes; momentum on deposit-index
excess returns, skip-month). Carry = OECD 3-month rate of month m-2 minus the
US rate of month m-2, where m is bar i's month (publication lag: on
2026-11-14 the latest values are 2026-08/09). Deposit-index accrual on bar
k-1 -> k uses the rate of the month before bar k's month (not a signal).
Weights decided at close i earn close i -> close i+1.
RULE (fixed before any run):
  * Universe EUR GBP AUD NZD JPY CHF CAD SEK NOK + USD (score 0); traded via
    the synthetic deposit indices TR_<ccy> of R-2026-11-14-VMEFX.
  * Each leg: AMP rank weights incl. USD, sum|w| = 1, USD weight dropped.
  * Book = (value + momentum + carry) / 3, only when all three legs exist
    (else T-bills); month-end, held one month. Value 5y centre, momentum 12-1.
  * Variants: V4, V6 (value centre), M9, M15 (momentum months).
Benchmark T-bills; asset_class "fx" (2bp); start 2003-12-01; positions from
~2009-06. FAMILY "fx-multistyle" (new) -> 5 trials. Never vault.
Diagnostics re-simulate the SAME book on the same data to build its monthly
series; one-leg books are built only to correlate with AQR's matching column.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "vmefx", Path(__file__).resolve().parent / "R-2026-11-14-VMEFX.py")
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)

ID = "R-2026-11-14-STYLE3FX"
AQR_CFP = ("https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/"
           "Century-of-Factor-Premia-Monthly.xlsx")
CARRY_LAG = 2
_RATES = {}


def rates():
    if not _RATES:
        for c, (_, _, code, _) in V.CCY.items():
            _RATES[c] = V.fred(f"IR3TIB01{code}M156N")
        _RATES["USD"] = V.fred("IR3TIB01USM156N")
    return _RATES


def carry_scores(i, dates, px):
    ym = V.month_back(dates[i][:7], CARRY_LAG)
    rt = rates()
    us = V.rate_for(rt["USD"], ym)
    if us is None:
        return {}
    sc = {"USD": 0.0}
    for c in V.CCY:
        r = V.rate_for(rt[c], ym)
        if r is not None and px[V.TR[c]][i]:
            sc[c] = r - us
    return sc


def make(value_years=5.0, mom_months=12, legs=("value", "momentum", "carry")):
    vm_legs = tuple(l for l in legs if l != "carry")
    vm = {l: V.make(value_years, mom_months, legs=(l,)) for l in vm_legs}
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                               # evaluate() re-simulates
        books = {l: fn(i, dates, px) for l, fn in vm.items()}   # call every bar (own state)
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        if "carry" in legs:
            sc = carry_scores(i, dates, px)
            if len(sc) >= 4:
                books["carry"] = {V.TR[c]: w for c, w in V.rank_weights(sc).items() if c != "USD" and w}
        if any(not books.get(l) for l in legs):
            st["w"] = {}
            return st["w"]
        out = {}
        for bk in books.values():
            for s, w in bk.items():
                out[s] = out.get(s, 0.0) + w / len(legs)
        st["w"] = {s: w for s, w in out.items() if w}
        return st["w"]
    return weights


weights = make()
VARIANTS = {"V4": make(4.0, 12), "V6": make(6.0, 12), "M9": make(5.0, 9), "M15": make(5.0, 15)}


def replication():
    cols = ["Currencies Value", "Currencies Momentum", "Currencies Carry", "Currencies Multi-style"]
    aqr = V.aqr_columns(AQR_CFP, "aqr_century_factor_premia.xlsx", cols)
    ms = aqr["Currencies Multi-style"]
    ours = V.monthly_excess(make())
    months = [m for m in sorted(ours) if V.OVERLAP[0] <= m <= V.OVERLAP[1] and m in ms
              and abs(ours[m]) > 1e-9]
    a, b = [ours[m] for m in months], [ms[m] for m in months]
    out = {"months": len(months), "from": months[0] if months else None,
           "to": months[-1] if months else None,
           "corr_multistyle": round(V._corr(a, b), 3) if months else None,
           "sharpe_ours": round(V._stats(a), 3) if months else None,
           "sharpe_aqr": round(V._stats(b), 3) if months else None}
    for leg, col in (("value", "Currencies Value"), ("momentum", "Currencies Momentum"),
                     ("carry", "Currencies Carry")):
        o = V.monthly_excess(make(legs=(leg,)))
        mm = [m for m in months if m in o and m in aqr[col]]
        out[f"corr_{leg}"] = round(V._corr([o[m] for m in mm], [aqr[col][m] for m in mm]), 3) if mm else None
    ok = (out["corr_multistyle"] is not None and out["corr_multistyle"] >= 0.50
          and abs(out["sharpe_ours"] - out["sharpe_aqr"]) <= 0.30)
    out["replicated"] = bool(ok)
    out["verdict_replication"] = "REPLICATED" if ok else "HARNESS/DATA SUSPECT"
    return out


if __name__ == "__main__":
    r = rb.evaluate(ID, weights, V.SYMS, None, start=V.START, asset_class="fx",
                    trials=5, family="fx-multistyle", variants=VARIANTS, fetch=V.fetch,
                    notes="REPLICATION of AQR Century currencies multi-style (value+momentum+carry, "
                          "equal weight, rank weights incl. USD) on carry-inclusive synthetic deposit "
                          "indices (spot x OECD 3m rate); carry on OECD rates lagged 2 months; nominal "
                          "value; month-end; T-bills bench; first dollar-neutral G10 carry leg")
    try:
        r["replication"] = replication()
    except Exception as e:                 # noqa: BLE001 — report, never hide
        r["replication"] = {"verdict_replication": "NOT COMPUTED", "error": repr(e)}
    print(json.dumps(r, indent=1))
