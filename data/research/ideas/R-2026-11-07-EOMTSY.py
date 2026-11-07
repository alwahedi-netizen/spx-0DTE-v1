"""R-2026-11-07-EOMTSY — end-of-month Treasury returns (index-extension flow).
Source: Hartley & Schwarz, "Predictable End-of-Month Treasury Returns"
(Wharton Rodney White Center WP 17-19, 2019):
https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2019/12/17-19.Schwarz.pdf
summarised by CXO Advisory: https://www.cxoadvisory.com/bonds/term-premium-end-of-month-effect/

Rationale: bond indices re-balance (extend duration) on the last business day
of each month; insurers and index-tracking managers buy Treasuries — especially
issues entering the index — into month-end, a predictable demand shock that
dealers must warehouse and are paid for. Paper (1990-2018): 2/5/10-year notes
earn positive, significant excess returns over the last 3-5 trading days,
largest on the last day; 10-year ~0.25% over the last three days, gross Sharpe
~1. 2015-18 weaker but significant. CXO notes TLT since 2002 did NOT
corroborate — this test is the honest check on the ETF a Schwab account holds.

RULE (fixed before any run; the paper's central 3-day window):
  hold IEF over the last N = 3 trading-day returns of each month: weights
  decided at close i are IEF when 1 <= (trading days left in the month after
  day i) <= N,
  so the position earns close(T-3)->close(T), T = the last trading day; out to
  T-bills at the close of T. Otherwise T-bills.
  (The exchange calendar is known in advance; only `dates`, never prices, are
  read ahead.)
Benchmark: IEF buy & hold (the bond class benchmark; the idea is in IEF only
~15% of days, so this asks whether those days carry enough to beat holding it).
Costs: 3bp/unit turnover (24 one-way trades a year). 2002-08+ (IEF inception).
Variants: N = 1, 2, 4, 5 days. trials = 5 (the paper itself reports 3-5 days).
Red-team flags: IEF ex-dividend dates sit at the start of the month (check the
adjusted series has no month-boundary artefact); effect may be smaller in a
7-10y ETF than in on-the-run notes; decay after the 2019 publication."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "IEF"


def make(n=3):
    def weights(i, dates, px):
        m, k, j = dates[i][:7], 0, i + 1
        while j < len(dates) and dates[j][:7] == m:
            k += 1
            j += 1
        if j >= len(dates):          # sample ends inside this month
            return {}
        return {SYM: 1.0} if 1 <= k <= n and px[SYM][i] else {}
    return weights


weights = make(3)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-EOMTSY", weights, [SYM], SYM, start="2002-08-01",
                    asset_class="bonds", trials=5, family="R-2026-11-07-EOMTSY",
                    variants={f"last{n}": make(n) for n in (1, 2, 4, 5)},
                    notes="IEF over the last 3 trading-day returns of each month, else T-bills; "
                          "bench IEF; 2002+")
    print(json.dumps(r, indent=1))
