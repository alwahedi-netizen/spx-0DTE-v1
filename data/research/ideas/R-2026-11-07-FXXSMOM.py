"""R-2026-11-07-FXXSMOM — cross-sectional currency momentum in the G10
(Menkhoff-Sarno-Schmeling-Schrimpf).

SOURCE: Menkhoff, Sarno, Schmeling & Schrimpf, "Currency Momentum Strategies",
BIS Working Paper 366 (2011, https://www.bis.org/publ/work366.pdf), published
Journal of Financial Economics 106(3), 2012: up to 10% p.a. between past winner
and loser currencies; not the carry trade, weakly related to technical trend
rules; partly eaten by costs and strongest in minor currencies (limits to
arbitrage). Headline portfolio: 1-month formation, 1-month holding.
Newest related evidence: Liu, "How to Maximize Momentum Returns in FX
Markets?", J. Int. Money & Finance 164 (2026,
https://ideas.repec.org/a/eee/jimfin/v164y2026ics0261560626000513.html) —
momentum is followed by reversals; conditioning on skewness/kurtosis helps
(needs 42 currencies — logged separately as I-2026-11-07-SKEWMOM).

RATIONALE: investors under-react to currency news, so relative winners keep
winning for a while. This is the CROSS-SECTIONAL, dollar-neutral rank (winners
vs losers), not the time-series sign rule of P-FX TSMOM / DD-2026-11-TREND
(which bet on each currency's own trend vs USD and carry the dollar factor) —
the difference matters because the dollar factor is what made DD-TREND's FX
legs flat.

RULE (fixed before any run):
  * Last trading day of each month: rank the 10 G10 currencies (9 vs USD plus
    USD at 0) by their return vs USD over the last 1 month (month-end to
    month-end). Long the top 3, short the bottom 3, equal weight 1/6 each
    (gross 1); a USD slot is simply cash. Held one month.
  * Variants (neighbours): formation 2 and 3 months; 2 and 4 currencies per
    side.
trials = 25: Menkhoff et al. report a 5x5 grid of formation x holding periods
and the 1/1 headline was picked from it.
Benchmark T-bills; asset_class="fx" (2bp); Yahoo spot pairs 2003-12+ (AUD
2006-05).
HARNESS CAVEAT (before the run): spot pairs earn no interest and are treated
as funded, so a dollar-neutral book is charged ~T-bill x gross vs a futures
implementation; read the Sharpe as conservative by ~rf/vol.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

LEGS = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "AUD": ("AUDUSD=X", 1),
        "NZD": ("NZDUSD=X", 1), "JPY": ("USDJPY=X", -1), "CHF": ("USDCHF=X", -1),
        "CAD": ("USDCAD=X", -1), "SEK": ("USDSEK=X", -1), "NOK": ("USDNOK=X", -1)}
SYMS = [s for s, _ in LEGS.values()]


def usd_price(px, sym, sg, k):
    v = px[sym][k]
    return None if not v else (v if sg > 0 else 1.0 / v)


def make(formation_months=1, per_side=3):
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []      # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            st["me"].append(i)
            if len(st["me"]) > formation_months:
                j = st["me"][-1 - formation_months]
                scores = {"USD": 0.0}
                for c, (sym, sg) in LEGS.items():
                    a, b = usd_price(px, sym, sg, j), usd_price(px, sym, sg, i)
                    if a and b:
                        scores[c] = b / a - 1
                if len(scores) >= 2 * per_side + 1:
                    order = sorted(scores, key=lambda c: scores[c])
                    w = {}
                    for c in order[-per_side:]:
                        if c != "USD":
                            w[LEGS[c][0]] = LEGS[c][1] / (2 * per_side)
                    for c in order[:per_side]:
                        if c != "USD":
                            w[LEGS[c][0]] = -LEGS[c][1] / (2 * per_side)
                    st["w"] = w
                else:
                    st["w"] = {}
        return st["w"] or {}
    return weights


weights = make(1, 3)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-FXXSMOM", weights, SYMS, None, start="2003-12-01",
                    asset_class="fx", trials=25, family="fx-xs-momentum",
                    variants={"F2": make(2, 3), "F3": make(3, 3), "N2": make(1, 2), "N4": make(1, 4)},
                    notes="G10 cross-sectional momentum: 1-month return rank incl. USD, long top 3 / short "
                          "bottom 3, monthly, spot pairs, T-bills bench; trials=25 (source's 5x5 grid); "
                          "harness charges ~rf on the dollar-neutral book (conservative)")
    print(json.dumps(r, indent=1))
