"""VAULT CRITERION — PRE-REGISTERED 2026-11-11 (after the red team, BEFORE the
one vault run; red-team report digest6/redteam/TSYCALPLUS.json): the vault
test PASSES if, over the vault-only stretch (VAULT_FROM 2024-11-01 -> latest
data), TSYCALPLUS's cumulative return beats IEF's net of the 50bp financing
and 3bp trade costs (active return > 0). t >= 3 is not required on ~2 years
(expected t ~1.2). Reported alongside: vault-only Sharpe vs IEF, active
return, and the full-history harness verdict. Never hold TSYCAL and
TSYCALPLUS together in the book.

L-2026-11-11-TSYCALPLUS — lab original (RESEARCH.md §2b), family L-TSYCAL:
hold IEF ALWAYS and add a second 1x IEF only inside the Treasury calendar
windows (month-end extension + FOMC), i.e. TSYCAL run as an OVERLAY on its
own benchmark instead of as a replacement for it.

INGREDIENTS: L-2026-11-08-TSYCAL (shortlist 4: IEF on the last 3 trading
days of each month OR the 3 days around scheduled FOMC decisions, else
T-bills; Sharpe 0.92 vs IEF 0.32, worst drop -5% vs -24%, held-out 1.07 vs
-0.16, confidence 99.7%) — imported unchanged. Evidence for the two windows:
Hartley & Schwarz, "Predictable End-of-Month Treasury Returns" (Wharton
2019, https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2019/12/17-19.Schwarz.pdf);
Hillenbrand, "The Fed and the Secular Decline in Interest Rates" (RFS 2025)
for the FOMC window.

WHY (KNOWLEDGE themes 11, 14, 15, 18, 23): TSYCAL failed ONLY the two
multiple-testing gates (DSR 0.14, active t 0.69) — not because its edge is
small but because of how it is measured: its active return vs IEF is
"TSYCAL - IEF" = (calendar excess return) - (IEF's excess return on the
~75% of days it sits in bills). That second term is pure IEF noise that has
nothing to do with the calendar hypothesis, and it drowns the t-stat.
Holding IEF all the time and ADDING 1x IEF in the windows makes the active
return exactly the calendar excess return (minus financing), so the gates
measure the hypothesis itself: TSYCAL's 4.6%/yr vs ~1.5% bills at Sharpe
0.92 over ~22 years implies an active t near 4 if the edge is real.
Theme 15/18: the next gain is sizing, not new signals — this is sizing.

RATIONALE (written before any run): the month-end index-extension buyer
and the FOMC risk premium are scheduled, mechanical and different days;
an investor who is already long duration can lever into those days with
a Treasury future (ZN/TN, financing ~ T-bills + a few bp) instead of
leaving duration on the other days. If the windows' excess return is
real, IEF + overlay beats IEF on Sharpe AND clears the t-stat bar. The
risk: in 2x windows a bad FOMC surprise or month-end selloff (2013 taper,
2022) costs double; and the held-out window (2018-24) includes 2022.
Caveat to state with any PASS: TSYCAL itself was designed on the same
development data, so its windows are not new information; only the vault
is an honest exam.

RULE (fixed before any run):
  * Weights at close i: IEF = 1.0 + OV x TSYCAL(i), where TSYCAL(i) is
    L-2026-11-08-TSYCAL's own weight (1.0 when bar i+1 is one of the last
    N_EOM = 3 trading days of its month or within [-1, 0, +1] trading days
    of a scheduled FOMC decision, else 0). OV = 1.0. Only the calendar is
    read ahead (as in TSYCAL), never prices.
  * Financing: harness charges T-bills on gross > 1; THIS SCRIPT ADDS
    SPREAD = 50bp/yr on gross above 1 (wrapper around rb.simulate inside
    __main__ only, restored after; the 2x-cost gate and all variants pay
    it) — conservative vs Treasury-futures implied financing.
  * Turnover: 1 unit in + 1 unit out per window (~25-30 windows/yr ->
    ~55 turns/yr at 3bp = ~17bp/yr; the 2x-cost gate doubles it).
Benchmark: IEF buy & hold. Costs 3bp. Start 2002-08-01 (as TSYCAL).
Variants (4): OV 0.5 and 1.5; N_EOM 2 and 4 (FOMC window unchanged).
trials = 20 = TSYCAL's honest 15 (own 5 + EOMTSY 5 + FOMCTSY 5) + this
script's 5. Family "L-TSYCAL" (harness count 5 -> it adds its own).
DATA TIMING: Yahoo IEF adjusted closes; FOMC dates are the scheduled
calendar published in advance (R-2026-11-07-PREFOMC.py list, via
R-2026-11-08-FOMCTSY); month-end days come from the trading calendar.
No external or revised series.
Check after the run: active t and DSR (the point of the design), 2013 and
2022 separately, worst drop vs IEF's -24%, portfolio.marginal (overlaps
TSYCAL in the book — compare, do not add both).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-11-TSYCALPLUS"
HERE = Path(__file__).resolve().parent
SYM = "IEF"
SPREAD = 0.005

_spec = importlib.util.spec_from_file_location("tsycal", HERE / "L-2026-11-08-TSYCAL.py")
tsycal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsycal)
assert tsycal.SYM == SYM


def make(ov=1.0, n_eom=3):
    st = {}

    def reset():
        st.clear()
        st.update(cal=tsycal.make(n_eom, (-1, 0, 1)))

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        c = (st["cal"](i, dates, px) or {}).get(SYM, 0.0)
        if not px[SYM][i]:
            return {}
        return {SYM: 1.0 + ov * c}
    return weights


weights = make(1.0, 3)

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
        r = rb.evaluate(ID, weights, [SYM], SYM, start="2002-08-01",
                        asset_class="bonds", trials=20, family="L-TSYCAL",
                        variants={"OV050": make(0.5, 3), "OV150": make(1.5, 3),
                                  "EOM2": make(1.0, 2), "EOM4": make(1.0, 4)},
                        notes="IEF 1.0 always + 1.0 extra IEF in TSYCAL's windows (last 3 trading days "
                              "of the month OR +-1 day around scheduled FOMC decisions); financing "
                              "T-bills + 50bp on gross > 1 (script wrapper); bench IEF; 2002-08+; "
                              "TSYCAL as an overlay so active return = calendar excess return")
    finally:
        rb.simulate = _ORIG_SIM
    print(json.dumps(r, indent=1))
