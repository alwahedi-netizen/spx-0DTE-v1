"""L-2026-11-10-RATESLEV — lab original (RESEARCH.md §2b), family L-RATESBOOK:
the rates/FX book v2 (L-2026-11-09-RATESBOOK) levered to IEF's volatility.

WHY (KNOWLEDGE themes 2, 3, 15, 18 + the RATESBOOK v2 result): v2 (TSYCAL +
MEDIAN + EQCREDIT + HAVENVOL, inverse-vol sleeve budgets, no leverage) had
Sharpe 0.735 vs IEF 0.316, worst drop -10% vs -24%, 99.3% confidence and
all neighbours better than IEF. It FAILED on DSR (0.02) and t (0.12) because
it earned only 3.8%/yr (IEF 3.4%) at about 3% volatility. Two sleeves
(TSYCAL, HAVENVOL) sit in T-bills most days, so the book is mostly cash,
and its active return vs IEF is roughly "-IEF + a small book". Theme 15/18:
the next gain is sizing, not more signals. Harvey et al. ("The Impact of
Volatility Targeting", JPM 2018,
https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf)
show that vol scaling leaves bond Sharpe ratios roughly unchanged, so
levering a Sharpe-0.7 book to IEF's risk should keep that Sharpe and turn
it into return: about 2x the book's excess return at IEF's volatility.

RATIONALE (written before any run): if the four sleeves' edges are real,
running the book at the benchmark's risk should beat IEF on return AND on
the active-return t-stat, which leverage raises because active return
stops being dominated by -IEF. The risk is the known failure regime of
levered bonds (theme 2): 2022, when rates rose and stocks fell together.
Financing cost and the vol-estimate lag in shocks (March 2020) are the
costs.

RULE (fixed before any run):
  * The book's weights each day are EXACTLY L-2026-11-09-RATESBOOK's
    (imported unchanged, its own state, LOOK 63 / FLOOR 2%).
  * Leverage L is set on the first trading day of each month from daily
    data through the previous close: vb = stdev of the book's own last
    LOOKV = 63 daily returns (from the prior-day UNLEVERED weights and
    today's closes; cash = 0), vi = stdev of IEF's last 63 daily returns;
    L = min(CAP, TGT x vi / vb) with TGT = 1.0, CAP = 3.0. Until 63 book
    returns exist: L = 1. Held weights = L x book weights (re-set daily).
  * Financing: the harness charges T-bills on gross above 1. THIS SCRIPT
    ADDS SPREAD = 50bp/yr on that borrowed amount (wrapper around
    rb.simulate inside __main__ only, restored afterwards; the 2x-cost
    gate and every variant pay it too). 50bp = the implied financing of
    Treasury/FX futures or an SPX box spread. A Schwab margin loan
    (T-bills + 3-6pp) is NOT assumed and would kill the idea. Note it in
    the ledger: HYG (the EQCREDIT sleeve) has no liquid future, so that
    sleeve's leverage needs a box-spread / portfolio-margin account.
Benchmark: IEF buy & hold. Costs 3bp (turnover scales with L, so the book's
13 turns/yr become about 25-40). 2006-06+ (as v2). FX pairs are aligned
off-calendar exactly as in v2.
Variants: TGT 0.75 and 1.25 (x IEF vol); LOOKV 42 and 126; CAP 2.0.
trials = 51 = v2's honest 45 (own 5 + every ingredient run) + this
script's 6. Family "L-RATESBOOK" (the harness count is lower; the passed
figure wins).
Check after the run: worst drop vs IEF's -24%, 2022 by itself, average L
and average gross, and portfolio.marginal (it overlaps the book).
"""
import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-10-RATESLEV"
HERE = Path(__file__).resolve().parent
BENCH = "IEF"
SPREAD = 0.005          # financing spread over T-bills on gross > 1, per year

_spec = importlib.util.spec_from_file_location("ratesbook", HERE / "L-2026-11-09-RATESBOOK.py")
ratesbook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratesbook)
ETFS = list(ratesbook.ETFS)
assert BENCH in ETFS


def _sd(x):
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def make(lookv=63, tgt=1.0, cap=3.0):
    st = {}

    def reset():
        st.clear()
        st.update(book=ratesbook.make(63, 0.02), prev={}, hist=[], L=1.0)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        else:
            r = 0.0                                   # unlevered book return i-1 -> i
            for s, w in st["prev"].items():
                a, b = px[s][i - 1], px[s][i]
                if a and b:
                    r += w * (b / a - 1)
            st["hist"].append(r)
            if dates[i][:7] != dates[i - 1][:7] and len(st["hist"]) >= lookv and i > lookv:
                c = px[BENCH][i - lookv:i + 1]       # closes i-lookv .. i
                ri = [b / a - 1 for a, b in zip(c, c[1:]) if a and b]
                vb = _sd(st["hist"][-lookv:])
                if vb > 0 and len(ri) >= int(0.9 * lookv):
                    st["L"] = min(cap, tgt * _sd(ri) / vb)
        w = st["book"](i, dates, px) or {}
        st["prev"] = dict(w)
        return {s: st["L"] * v for s, v in w.items() if v}
    return weights


weights = make(63, 1.0, 3.0)

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
        r = rb.evaluate(ID, weights, ETFS, BENCH, start="2006-06-01",
                        asset_class="bonds", trials=51, family="L-RATESBOOK",
                        variants={"TGT75": make(63, 0.75, 3.0), "TGT125": make(63, 1.25, 3.0),
                                  "LOOK42": make(42, 1.0, 3.0), "LOOK126": make(126, 1.0, 3.0),
                                  "CAP2": make(63, 1.0, 2.0)},
                        notes="RATESBOOK v2 (imported unchanged) levered monthly to IEF's 63-day vol "
                              "(L = vol_IEF / vol_book, cap 3x), financed at T-bills + 50bp/yr "
                              "(spread added by this script's simulate wrapper); bench IEF; 2006-06+")
    finally:
        rb.simulate = _ORIG_SIM
    print(json.dumps(r, indent=1))
