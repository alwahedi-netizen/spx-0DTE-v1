"""R-2026-11-07-FXVALUE — G10 currency value (5-year reversal), Asness-Moskowitz-
Pedersen form.

SOURCE: Asness, Moskowitz & Pedersen, "Value and Momentum Everywhere", Journal
of Finance 68(3), 2013 (https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf),
§I.B: currency value = log(average spot rate 4.5-5.5 years ago / spot today)
minus the 5-year CPI-inflation differential (the 5-year change in PPP); 10
currencies (AUD, CAD, DEM/EUR, JPY, NZD, NOK, SEK, CHF, GBP, USD), rank-
weighted, zero-cost, monthly. Supporting: Menkhoff, Sarno, Schmeling &
Schrimpf, "Currency Value", RFS 30(2) 2017 (https://ideas.repec.org/p/cpr/ceprdp/11324.html)
— value is distinct from carry and momentum; Chen, "Currency Investing
Throughout Recent Centuries" (SSRN 4692257, via
https://quantpedia.com/fx-carry-value-momentum-strategies-over-their-200-year-history/)
— long-run reversal positive since ~1980 in the floating era.

RATIONALE: exchange rates overshoot and revert slowly toward purchasing-power
parity; currencies that have fallen most over five years are cheap and earn a
premium as they revert. Nothing in the ledger trades currency value (P-FX runs
carry and trend only), and value is negatively correlated with momentum.

RULE (fixed before any run; AMP's single published definition, trials=1):
  * On the last trading day of each month, for each of the 9 non-USD G10
    currencies with enough history: value = ln(mean USD price of the currency
    over the dates 5.5 to 4.5 years ago / USD price today). USD is the 10th
    currency with value 0.
  * NO CPI adjustment: Yahoo has no CPI, so this is the nominal 5-year
    reversal (AMP note: G10 inflation gaps are small; FRED CPI would unlock
    the true PPP version).
  * Rank-weights (AMP): w = c * (rank - mean rank) across the available
    currencies incl. USD, c so that sum|w| = 1 (0.5 long / 0.5 short). The USD
    weight is the numeraire and is dropped; foreign weights go on the pairs
    (USD-quoted pairs take the opposite sign). Held one month.
  * Variants (neighbouring lookbacks, centre +/- 0.5y): 3y, 4y, 6y, 7y.
Benchmark: T-bills. asset_class="fx" (2bp). Yahoo spot pairs from 2003-12
(AUD 2006-05), so signals start ~2009-06 (development data to the vault).
HARNESS CAVEAT (on the record before the run): spot pairs earn no interest and
research_bt treats them as funded positions, so a dollar-neutral book is
charged roughly the T-bill rate x gross vs a real futures implementation (and
misses the net carry of the legs). Read the Sharpe as conservative by ~rf/vol.
"""
import bisect
import math
import sys
from datetime import date, timedelta
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


def _shift(d, years):
    return (date.fromisoformat(d) - timedelta(days=int(round(years * 365.25)))).isoformat()


def rank_weights(scores):
    """AMP rank weights: scores {ccy: s} incl. USD -> {ccy: w}, sum|w| = 1."""
    names = sorted(scores, key=lambda c: scores[c])
    n = len(names)
    ranks = {c: r + 1 for r, c in enumerate(names)}
    mean = (n + 1) / 2
    raw = {c: ranks[c] - mean for c in names}
    tot = sum(abs(v) for v in raw.values())
    return {c: v / tot for c, v in raw.items()} if tot else {}


def make(center_years):
    st = {"w": None, "first": {}}
    lo_y, hi_y = center_years + 0.5, center_years - 0.5

    def weights(i, dates, px):
        if i == 0:
            st["w"] = None          # evaluate() re-simulates (2x costs): start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            a = bisect.bisect_left(dates, _shift(dates[i], lo_y), 0, i + 1)
            b = bisect.bisect_right(dates, _shift(dates[i], hi_y), 0, i + 1)
            scores = {"USD": 0.0}
            for c, (sym, sg) in LEGS.items():
                now = usd_price(px, sym, sg, i)
                past = [usd_price(px, sym, sg, k) for k in range(a, b)]
                past = [p for p in past if p]
                # need the full window: first available price older than the window start
                if sym not in st["first"] and now:
                    st["first"][sym] = next(k for k in range(0, i + 1) if px[sym][k])
                first = st["first"].get(sym)
                if now and past and first is not None and first <= a and len(past) > 100:
                    scores[c] = math.log((sum(past) / len(past)) / now)
            if len(scores) >= 4:
                rw = rank_weights(scores)
                st["w"] = {LEGS[c][0]: LEGS[c][1] * w for c, w in rw.items() if c != "USD" and w}
            else:
                st["w"] = {}
        return st["w"] or {}
    return weights


weights = make(5.0)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-FXVALUE", weights, SYMS, None, start="2003-12-01",
                    asset_class="fx", trials=1, family="fx-value",
                    variants={"3y": make(3.0), "4y": make(4.0), "6y": make(6.0), "7y": make(7.0)},
                    notes="AMP currency value without CPI (nominal 5y reversal, avg 4.5-5.5y ago vs today), "
                          "rank-weighted incl. USD, monthly, spot pairs, T-bills bench; harness charges ~rf "
                          "on the dollar-neutral book (conservative)")
    print(json.dumps(r, indent=1))
