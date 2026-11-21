"""L-2026-11-21-EOMCREDIT — month-end index extension in investment-grade
corporates (lab). Scripts the bond desk's queued row L-2026-11-08-EOMCREDIT
(same rule, new id per the league naming rule).

RATIONALE (written 2026-11-08, restated before any run): bond indices
re-balance on the last business day of each month; index-tracking and
benchmarked managers buy the bonds entering the index (new issues, longer
duration) into month-end, a predictable demand that dealers warehouse and
are paid for. For Treasuries this is R-2026-11-07-EOMTSY (Hartley &
Schwarz, Wharton WP 17-19, 2019: 2/5/10y notes earn significant excess
returns over the last 3-5 days; our IEF test: Sharpe 0.73 vs 0.32,
confidence 95.6%, shortlist 3). The corporate index should feel it MORE:
heavier new issuance each month (bigger index extension) and scarcer dealer
balance sheet for corporates than for Treasuries (iBoxx USD Liquid IG,
LQD's index, rebalances on the last business day of the month:
https://www.spglobal.com/spdji/en/indices/fixed-income/iboxx-usd-liquid-investment-grade-index/).
Lab idea (RESEARCH.md §2b): no published corporate month-end rule to
replicate; the mechanism's evidence is Hartley-Schwarz plus our own EOMTSY.
New family (the Treasury calendar family L-TSYCAL spent its vault on
2026-11-11; this asset is different, but the read-out below shows how much
of any gain is simply EOMTSY's Treasury effect inside LQD's duration).
Counter-evidence logged before the run: theme 4 (calendar effects decay
after publication, 2019); theme 24 (TSYCALPLUS: a real month-end effect was
too small to show in the 2-year vault); LQD can trade away from NAV at
month-end (premium/discount noise).

RULE (fixed before any run, as queued): weights decided at close i are
LQD 1.0 when 1 <= (trading days left in the month after day i) <= N = 3,
so the position earns close(T-3) -> close(T), T = the month's last trading
day; T-bills otherwise. If the sample ends inside a month, flat.
Benchmark: AGG buy & hold (as queued). Costs 3bp (24 one-way trades/yr).
Start 2003-10-01 (AGG listed 2003-09-29; LQD 2002-07).
Variants (4): N = 1, 2, 4, 5 days (the source reports 3-5).
trials = 5 (new family L-2026-11-21-EOMCREDIT).
CONTROL (printed, not a test, no evaluate call): EOMTSY's IEF over the same
window and the credit-only part (LQD minus IEF on window days), through the
same simulate() on the same dates, so the red team can see whether credit
adds anything beyond the Treasury month-end effect.
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs AGG, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating AGG). Learning criterion
(for the shortlist, not a pass): full-period Sharpe above the IEF control's
AND the credit-only read-out's mean window return > 0.
DATA TIMING: the rule reads no prices at all, only the exchange calendar
(how many trading days remain in the month after bar i; holidays are
scheduled in advance); the weight decided at close i earns close i ->
close i+1. LQD's monthly ex-dividend date is the first business day of the
month, outside the window.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-21-EOMCREDIT"
SYM, BENCH, TSY = "LQD", "AGG", "IEF"
START = "2003-10-01"


def days_left_after(dates, i):
    """Trading days left in bar i's month after bar i, or None if the sample ends inside it."""
    m, k, j = dates[i][:7], 0, i + 1
    while j < len(dates) and dates[j][:7] == m:
        k += 1
        j += 1
    return None if j >= len(dates) else k


def make(n=3, sym=SYM):
    def weights(i, dates, px):
        k = days_left_after(dates, i)
        return {sym: 1.0} if k is not None and 1 <= k <= n and px[sym][i] else {}
    return weights


weights = make(3)


def control():
    dates, px = rb.prices([SYM, BENCH, TSY], START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    out = {}
    for name, fn in (("lqd_window", make(3, SYM)), ("ief_window_eomtsy", make(3, TSY))):
        r, _ = rb.simulate(fn, dates, px, rf, 3.0)
        out[name] = {"cagr": round(rb.cagr(r), 4), "sharpe": round(rb.sharpe(r, rf[1:]), 3),
                     "maxdd": round(rb.max_dd(r), 4)}
    diff = []
    for i in range(len(dates) - 1):
        k = days_left_after(dates, i)
        if k is not None and 1 <= k <= 3 and all(px[s][i] and px[s][i + 1] for s in (SYM, TSY)):
            diff.append(px[SYM][i + 1] / px[SYM][i] - px[TSY][i + 1] / px[TSY][i])
    out["credit_only_mean_bp_per_window_day"] = round(1e4 * sum(diff) / max(len(diff), 1), 2)
    out["credit_only_t"] = round(rb.t_stat(diff), 2)
    out["window_days"] = len(diff)
    return out


if __name__ == "__main__":
    r = rb.evaluate(ID, weights, [SYM], BENCH, start=START,
                    asset_class="bonds", trials=5, family=ID,
                    variants={f"last{n}": make(n) for n in (1, 2, 4, 5)},
                    notes="LQD over the last 3 trading-day returns of each month, else T-bills; "
                          "bench AGG; 2003-10+; lab: EOMTSY's index-extension mechanism on IG "
                          "corporates")
    r["control_not_test"] = control()
    print(json.dumps(r, indent=1))
