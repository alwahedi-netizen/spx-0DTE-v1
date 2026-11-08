"""L-2026-11-07-GOLDCRISIS — lab original (RESEARCH.md §2b), queued 2026-11-07,
scripted 2026-11-08: correlation-acceleration switch into GOLD instead of cash.

VARIES R-2026-11-07-CORRACC (potential 4, risk-reducer): same trigger (sector
correlations accelerating = market stress), but the off-signal destination is
GLD instead of T-bills, and the threshold is the round X = 1.10 rather than
the source's in-sample pick 1.13.
Ingredients / sources:
  * Quantpedia (Mesicek, 2026-11-06), "Correlation Acceleration"
    (https://quantpedia.com/correlation-acceleration-detecting-market-stress-through-rising-etf-correlations/)
    — the trigger; CORRACC cut SPY's worst drop -55% -> -34% but sat in cash.
  * Erb & Harvey, "Understanding Gold" (2025; summary
    https://quantpedia.com/understanding-gold-hedge-diversifier-or-overpriced-insurance/):
    gold rose in most large equity drawdowns — the stress windows CORRACC
    exits are when gold has tended to earn its crisis premium.
Rationale: when stocks start moving as one block (deleveraging, macro shock)
investors flee to the safe-haven asset; holding gold in those windows should
keep CORRACC's crash cut AND earn a return instead of the T-bill rate.
Known failure stated before the run: liquidity dashes where gold is sold with
everything else (Mar 2020, Oct 2008), and fast V-rebounds.

RULE (fixed before any run; the ledger row's stated rule):
  daily at the close: c20 / c60 = average pairwise correlation of the nine
  SPDR sector ETFs' daily returns over the last 20 / 60 days;
  if c20 > 1.10 x c60: hold 100% GLD tomorrow, else 100% SPY.
Benchmark: SPY buy & hold. Costs 5bp/unit turnover (a switch = 2 units).
History: GLD 2004-11 -> start 2004-12 (60-day warm-up), includes 2008, 2020, 2022.
Variants: X = 1.00 / 1.05 / 1.15 / 1.20.
trials = 31: CORRACC's source swept 26 thresholds (counted there) + this
run + 4 variants; family R-2026-11-07-CORRACC so the bar keeps rising.
asset_class "commodities" (cost model only; the gold leg is the new part).
"""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SECT = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]


def _avg_corr(px, i, n):
    rets = {}
    for s in SECT:
        c = px[s][i - n:i + 1]
        if len(c) < n + 1 or None in c:
            return None
        rets[s] = [c[k] / c[k - 1] - 1 for k in range(1, len(c))]
    tot, cnt = 0.0, 0
    for a in range(len(SECT)):
        for b in range(a + 1, len(SECT)):
            x, y = rets[SECT[a]], rets[SECT[b]]
            mx, my = sum(x) / n, sum(y) / n
            sxy = sum((p - mx) * (q - my) for p, q in zip(x, y))
            sxx = sum((p - mx) ** 2 for p in x)
            syy = sum((q - my) ** 2 for q in y)
            if sxx and syy:
                tot += sxy / math.sqrt(sxx * syy)
                cnt += 1
    return tot / cnt if cnt else None


def make(x=1.10):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i < 61 or not px["GLD"][i]:
            return {"SPY": 1.0}
        c20, c60 = _avg_corr(px, i, 20), _avg_corr(px, i, 60)
        if c20 is None or c60 is None:
            return {"SPY": 1.0}
        return {"GLD": 1.0} if c20 > x * c60 else {"SPY": 1.0}
    return weights


weights = make()

if __name__ == "__main__":
    variants = {f"x{v:.2f}": make(v) for v in (1.00, 1.05, 1.15, 1.20)}
    res = rb.evaluate("L-2026-11-07-GOLDCRISIS", weights, SECT + ["SPY", "GLD"], "SPY", start="2004-11-18",
                      cost_bps=5.0, asset_class="commodities", trials=31,
                      family="R-2026-11-07-CORRACC", variants=variants,
                      notes="daily: GLD tomorrow when sector corr20 > 1.10 x corr60, else SPY; bench SPY; "
                            "varies R-2026-11-07-CORRACC (gold not cash, X=1.10 not 1.13); vault sealed")
    print(json.dumps(res, indent=1))
