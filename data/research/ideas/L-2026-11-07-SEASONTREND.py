"""L-2026-11-07-SEASONTREND — lab original (RESEARCH.md §2b) designed and
scored 2026-11-07 (ledger row L-2026-11-07-SEASONTREND, score 68), queued
over that day's 5-script cap; scripted 2026-11-08 under its existing id.
Combination L-SEASONTREND in KNOWLEDGE.md: R-2026-11-07-BEST6M (potential 3,
risk-reducer) x DD-2026-11-TREND (potential 5, risk-reducer).

RATIONALE (written before any run): both filters cut the S&P's worst drop
(BEST6M -36%, SMA10 -33% vs -55%) but each pays for it in lost return —
BEST6M sits in cash every summer, even in strong bull markets, and SMA10
whipsaws in choppy winters. Their failure modes are different: the season
is a calendar prior with no information about today's market, the trend is
today's market with no calendar prior. Requiring BOTH to agree before
stepping out should keep most of the crash protection (the big bear legs —
2001-02, 2008 — ran through May-October below trend) while giving back far
fewer bull-market months than either filter alone.

RULE (fixed before any run):
  * At each month's last close: SMA = average of VFINX's last 10 month-end
    closes (incl. this one).
  * If the NEXT month is May-October AND VFINX's close < SMA -> T-bills for
    the next month; otherwise hold VFINX (S&P 500 with dividends).
  * Before 10 month-ends exist: hold VFINX.
  * Variants (robustness gate): SMA 8 and 12 months; risk-off season window
    Jun-Sep and Apr-Nov (with SMA 10).
  * Benchmark VFINX buy & hold, 5bp/side, 1986+, strict bar, vault sealed
    (development data < VAULT_FROM), family "L-SEASONTREND".
  * trials=8: this family's 1 + 4 variants, plus the ingredients already
    seen on the S&P (BEST6M: 1 run; DD-TREND S&P: SMA10 and 12-1 = 2 runs).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "L-2026-11-07-SEASONTREND"
SYM = "VFINX"


def make_weights(sma_m=10, season=(5, 6, 7, 8, 9, 10)):
    st = {}

    def weights(i, dates, px):
        if i == 0:                                   # fresh state for every simulation
            st.clear()
            st["me"], st["on"] = [], True
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            c = px[SYM][i]
            if c is not None:
                st["me"].append(c)
            nxt_m = int(dates[i + 1][5:7])           # calendar only, no prices
            below = (len(st["me"]) >= sma_m and c is not None
                     and c < sum(st["me"][-sma_m:]) / sma_m)
            st["on"] = not (nxt_m in season and below)
        return {SYM: 1.0} if st["on"] else {}

    return weights


weights = make_weights(10)
VARIANTS = {"sma8": make_weights(8), "sma12": make_weights(12),
            "jun_sep": make_weights(10, (6, 7, 8, 9)),
            "apr_nov": make_weights(10, (4, 5, 6, 7, 8, 9, 10, 11))}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, [SYM], SYM, start="1986-01-01", cost_bps=5.0, asset_class="stocks",
        trials=8, family="L-SEASONTREND", variants=VARIANTS,
        notes=("LAB: hold VFINX except T-bills in May-Oct months when VFINX < 10-month SMA "
               "(both filters must agree); variants SMA8/12, season Jun-Sep / Apr-Nov; "
               "trials 8 incl. BEST6M + DD-TREND S&P runs seen; vault sealed"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1))
