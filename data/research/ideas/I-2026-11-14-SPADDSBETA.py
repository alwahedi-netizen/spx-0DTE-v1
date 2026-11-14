"""I-2026-11-14-SPADDSBETA — variant of R-2026-11-14-SPADDS: the short
basket of recent S&P 500 additions hedged to ZERO MARKET BETA instead of
dollar-neutral.

Source: as SPADDS — Bennett, Stulz & Wang (2020) "Does Joining the S&P 500
Index Hurt Firms?" (https://www.nber.org/papers/w27593): -0.63..-0.73% a
month abnormal return in the year after announcement, 2008-2017, measured
both market-adjusted (= SPADDS) and as 3/4/5-factor ALPHAS (= this variant's
target). They also report that added firms are more volatile.

WHY THIS VARIANT (fixed before any run): additions arrive after strong
run-ups and carry above-market beta, so the dollar-neutral SPADDS book is
net SHORT the market — in a bull market it loses on beta even when the
abnormal return is there. Sizing the SPY leg to the basket's own beta
removes that drag and isolates the source's alpha-style measure.
RUNS ONLY IF SPADDS REPLICATES (RESEARCH.md § LEAGUE rule 1): the script
first runs SPADDS.replication_check() (mean monthly SPY-minus-additions
2008-2017 >= +0.30%) and refuses — no evaluate, no trial — if it fails.

RULE (fixed before any run): identical to SPADDS (events = announced
additions, 12-month window from announcement, equal-weight short basket,
re-set on basket change and month end, drift in between, < 5 names ->
cash), EXCEPT the SPY leg = +beta, where beta = the equal-weight average
of each basket stock's OLS beta to SPY on daily returns over the 252
trading days ending dates[i-1] (a stock with < 120 paired returns counts
as beta 1.0), clipped to [0.5, 2.0]. Net weight = beta - 1: a positive
remainder is borrowed (pays T-bill + fin_spread 0.5%/yr), a negative one
is short proceeds (earns T-bills).
  * Variants (robustness gate): holding window 6, 9, 15, 18 months.
  * Benchmark T-bills, 5bp/side, 1998-01 -> vault, strict bar + FF5+Mom
    alpha gate. Family "sp500-additions" (same hypothesis as SPADDS):
    lifetime 5 after SPADDS + 5 here -> trials 10.
  * Borrow fees on the short leg not charged (~0.4%/yr; see SPADDS).
PASS CRITERION (written before any run): harness verdict PASS with every
world-class gate (incl. factor alpha t >= 2) on 1998-01 -> 2024-10.

DATA-TIMING: basket membership from announcement dates <= dates[i-1];
betas from closes dated <= dates[i-1]; px[.][i] only to drift the held
book. Weights decided at close i earn close i -> close i+1.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("spadds", _here.with_name("R-2026-11-14-SPADDS.py"))
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)                     # also installs the SFP wrapper for SPY

ID = "I-2026-11-14-SPADDSBETA"
LOOKBACK, MIN_OBS, BETA_LO, BETA_HI = 252, 120, 0.5, 2.0


def _beta(col, mkt, end):
    xs, ys = [], []
    for k in range(max(1, end - LOOKBACK + 1), end + 1):
        a, b, c, d = col[k - 1], col[k], mkt[k - 1], mkt[k]
        if a and b and c and d:
            ys.append(b / a - 1)
            xs.append(d / c - 1)
    if len(xs) < MIN_OBS:
        return 1.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx else 1.0


def basket_beta(names, i, px):
    end = i - 1                                   # signal day: closes <= dates[i-1]
    mkt = px[sp.HEDGE]
    b = sum(_beta(px[t], mkt, end) for t in names) / len(names)
    return min(BETA_HI, max(BETA_LO, b))


weights = sp.make_weights(12, hedge_fn=basket_beta)
VARIANTS = {f"hold{m}m": sp.make_weights(m, hedge_fn=basket_beta) for m in (6, 9, 15, 18)}


if __name__ == "__main__":
    rep = sp.replication_check()
    print("REPLICATION (SPADDS rule)", json.dumps(rep))
    if not rep["replicated"]:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "SPADDS did not replicate the source headline — harness/data suspect; "
                                    "variant not tested (RESEARCH.md LEAGUE rule 1)"}))
        sys.exit(0)
    out = rb.evaluate(
        ID, weights, sp.TICKERS + [sp.HEDGE], None, start=sp.START, asset_class="stocks", trials=10,
        family=sp.FAMILY, variants=VARIANTS, source="sharadar", fin_spread=0.005,
        notes=("SPADDS variant: short equal-weight basket of S&P 500 additions (12m from announcement), "
               "long SPY sized to the basket's 252-day beta (clip 0.5-2.0), bench T-bills, borrow "
               "T-bill+50bp; variants hold 6/9/15/18m; borrow fees on shorts not charged"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
