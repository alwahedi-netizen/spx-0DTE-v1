"""L-2026-11-08-TSYCAL — lab original (RESEARCH.md §2b): a Treasury
"calendar book" = the union of two scheduled windows in which a named,
pre-announced event moves duration:
  (1) month-end index extension (R-2026-11-07-EOMTSY, shortlist potential 3:
      Sharpe 0.73 vs 0.32, worst drop -6% vs -24%, failed only t >= 3 / DSR
      because it is in the market ~15% of days), and
  (2) the FOMC window (R-2026-11-08-FOMCTSY: Hillenbrand RFS 2025; Pan-Peng
      2025 pre-FOMC drift in long Treasuries).

RATIONALE (written before any run): KNOWLEDGE theme 11 — small calendar
edges in rates fail t >= 3 alone because they are invested so rarely; two
INDEPENDENT drivers (a mechanical index-rebalance buyer vs a policy-news
risk premium) that land on different days should add their excess returns
while the noise adds only in quadrature, raising the t-stat. The windows
rarely overlap (FOMC decisions fall mid/late month; a late-month meeting
overlapping the last 3 days is held once, not twice).

RULE (fixed before any run):
  * Weights decided at close i: IEF 1.0 if the NEXT bar (i+1) is
      (a) one of the last N_EOM = 3 trading days of its month (EOMTSY's
          definition: earns close T-3 -> close T), OR
      (b) a trading day at offset -1, 0 or +1 from a scheduled FOMC decision
          day (FOMCTSY's window: earns close D-2 -> close D+1);
    else T-bills. Only the calendar (`dates`) is read ahead, never prices.
  * FOMC dates: the scheduled list in R-2026-11-07-PREFOMC.py.
Benchmark: IEF buy & hold. Costs 3bp. 2002-08+ (IEF).
Variants: N_EOM 2 and 4 (FOMC 3-day); FOMC window [-1,0] and [-2..+2]
(N_EOM 3).
trials = 15 = 1 + 4 variants + EOMTSY's 5 + FOMCTSY's 5 (the ingredients'
own runs are honest trials of this combination). family "L-TSYCAL".
Check after the run: portfolio.marginal vs the shortlist book (EOMTSY was
the best marginal add at +0.10 Sharpe).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-08-TSYCAL"
SYM = "IEF"

_spec = importlib.util.spec_from_file_location(
    "fomctsy", Path(__file__).resolve().parent / "R-2026-11-08-FOMCTSY.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
window_days = _mod.window_days


def eom_days(dates, n):
    """Indexes of the last n trading days of each month (the final, possibly
    incomplete month of the sample is excluded, as in EOMTSY)."""
    out, k = set(), 0
    while k < len(dates):
        j = k
        while j + 1 < len(dates) and dates[j + 1][:7] == dates[k][:7]:
            j += 1
        if j + 1 < len(dates):               # month is complete in the sample
            out.update(range(max(k, j - n + 1), j + 1))
        k = j + 1
    return out


def make(n_eom=3, offsets=(-1, 0, 1)):
    st = {"key": None, "hold": set()}

    def weights(i, dates, px):
        if i == 0 or st["key"] != (len(dates), dates[0]):
            st["key"] = (len(dates), dates[0])
            st["hold"] = eom_days(dates, n_eom) | window_days(dates, offsets)
        if i + 1 < len(dates) and (i + 1) in st["hold"] and px[SYM][i]:
            return {SYM: 1.0}
        return {}
    return weights


weights = make(3, (-1, 0, 1))

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [SYM], SYM, start="2002-08-01",
                    asset_class="bonds", trials=15, family="L-TSYCAL",
                    variants={"EOM2": make(2, (-1, 0, 1)), "EOM4": make(4, (-1, 0, 1)),
                              "FOMC2": make(3, (-1, 0)), "FOMC5": make(3, (-2, -1, 0, 1, 2))},
                    notes="IEF over the last 3 trading days of each month OR the 3 trading days "
                          "around scheduled FOMC decisions, else T-bills; bench IEF; 2002+; "
                          "lab original EOMTSY x FOMCTSY")
    print(json.dumps(r, indent=1))
