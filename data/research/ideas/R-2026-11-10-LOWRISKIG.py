"""R-2026-11-10-LOWRISKIG — scripts the queued I-2026-11-09-LOWRISKIG (scored
72): the low-risk factor in corporate bonds. Hold short-maturity investment
grade levered to the risk of the broad IG index instead of the broad index.

SOURCES: Houweling & van Zundert, "Factor Investing in the Corporate Bond
Market", FAJ 73(2) 2017 (https://papers.ssrn.com/abstract_id=2516322 ;
https://rpc.cfainstitute.org/research/financial-analysts-journal/2017/corporate-bonds-time-for-factors):
short-maturity, highly rated bonds earn more return per unit of risk (the
low-risk factor). Mechanism: Frazzini & Pedersen, "Betting Against Beta",
JFE 2014. Leverage-constrained investors reach for yield in long and risky
bonds, so safe short bonds are under-priced per unit of risk. The
Treasury version (R-2026-11-07-BABTSY, VFISX levered to VFITX, 1991+)
FAILED (Sharpe 0.35 vs 0.43). This tests whether the effect lives in
credit, where Houweling-van Zundert found it, rather than in the Treasury curve.

RATIONALE (written before any run): IG credit spreads per unit of
duration are typically wider at the short end, and short IG has less
spread-duration risk in crunches. An investor who can borrow near T-bills
should therefore get more return from L x IGSB than from LQD at the same
volatility.

RULE (fixed before any run):
  * On the first trading day of each month, from daily closes through the
    previous close: L = stdev(LQD daily returns, last 63) / stdev(IGSB
    daily returns, last 63), capped at 2.5. Hold L x IGSB for the month
    (re-set to target daily, as in BABTSY). Warm-up (fewer than 63
    returns): LQD 1.0.
  * Financing: the harness charges T-bills on gross exposure above 1.
    THIS SCRIPT ADDS a stated spread of 50bp/yr on that borrowed amount
    (`SPREAD`; an SPX box-spread / portfolio-margin rate, NOT a Schwab
    margin loan, which costs far more and would kill the idea). This is a
    change from the 2026-11-09 ledger row (T-bills flat), made before any
    run. It is implemented by wrapping rb.simulate inside __main__ only,
    restored afterwards, so the 2x-cost gate and every variant pay it too.
Benchmark: LQD buy & hold. This deliberately departs from the class
default (AGG/IEF): the hypothesis is "more return at LQD's risk", and only
the risk-matched index tests it (BABTSY likewise used VFITX). To use AGG
instead, change BENCH and add LQD to the symbols.
Costs 3bp. 2007-01+ (IGSB, ex-CSJ, 2007-01-11; LQD 2002). Includes 2008,
March 2020, 2022.
Variants: vol window 42 and 126; cap 2.0 and 3.0. trials = 10 = own 5 +
BABTSY's 5 (same lever-the-short-end hypothesis). Family: own id.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-10-LOWRISKIG"
SHORT, BENCH = "IGSB", "LQD"
SPREAD = 0.005          # financing spread over T-bills on gross > 1, per year


def _vol(col, i, n):
    c = col[i - n:i]                         # closes i-n .. i-1 (n-1 returns)
    r = [b / a - 1 for a, b in zip(c, c[1:]) if a and b]
    if len(r) < int(0.9 * (n - 1)):
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def make(n=63, cap=2.5):
    st = {"w": None}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = None
        if i > n + 1 and (st["w"] is None or dates[i][:7] != dates[i - 1][:7]):
            vs, vb = _vol(px[SHORT], i, n + 1), _vol(px[BENCH], i, n + 1)
            if vs and vb:
                st["w"] = {SHORT: min(cap, vb / vs)}
        if st["w"] is not None and px[SHORT][i]:
            return st["w"]
        return {BENCH: 1.0} if px[BENCH][i] else {}
    return weights


weights = make(63, 2.5)

_ORIG_SIM = rb.simulate


def spread_simulate(weights_fn, dates, px, rf, cost_bps=5.0):
    """rb.simulate plus SPREAD/yr on gross exposure above 1 (daily, /252)."""
    gross = {}

    def rec(i, d, p):
        w = weights_fn(i, d, p) or {}
        gross[i] = sum(abs(v) for v in w.values() if v)
        return w
    rets, turnover = _ORIG_SIM(rec, dates, px, rf, cost_bps)
    return [r - max(0.0, gross.get(i, 0.0) - 1) * SPREAD / 252
            for i, r in enumerate(rets)], turnover


if __name__ == "__main__":
    import json
    rb.simulate = spread_simulate
    try:
        r = rb.evaluate(ID, weights, [SHORT], BENCH, start="2007-01-01",
                        asset_class="bonds", trials=10, family=ID,
                        variants={"N42": make(42, 2.5), "N126": make(126, 2.5),
                                  "CAP2": make(63, 2.0), "CAP3": make(63, 3.0)},
                        notes="month-start: IGSB levered to LQD's 63-day vol (cap 2.5x), financed "
                              "at T-bills + 50bp/yr (spread added by this script's simulate "
                              "wrapper); bench LQD (risk-matched, deliberate); 2007+; Houweling-"
                              "van Zundert FAJ 2017; varies BABTSY; scripts I-2026-11-09-LOWRISKIG")
    finally:
        rb.simulate = _ORIG_SIM
    print(json.dumps(r, indent=1))
