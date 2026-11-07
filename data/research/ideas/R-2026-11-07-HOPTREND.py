"""R-2026-11-07-HOPTREND — diversified managed-futures trend portfolio in the
Hurst-Ooi-Pedersen form (Hurst, Ooi & Pedersen, "A Century of Evidence on
Trend-Following Investing", Journal of Portfolio Management 2017:
https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing ;
Moskowitz-Ooi-Pedersen 2012 TSMOM).

VARIES ledger row DD-2026-11-TREND (single asset, long-or-cash, one lookback,
no vol scaling: never beat buy & hold anywhere). HOP's claim is about the
PORTFOLIO: equal-risk positions across many markets, long AND short, averaged
over 1/3/12-month signals — the Sharpe comes from diversification across
asset classes, not from any single market. That is the difference tested.

Rationale: under-reaction then over-reaction to news (and central-bank /
hedger flows) produce trends in every asset class; the bets are close to
uncorrelated across classes, so a vol-balanced book of many small trend bets
has a far better Sharpe than any single one, with crisis-alpha skew.

RULE (fixed before any run; HOP's published defaults, ETF instruments):
  universe : SPY EFA EEM (equities), IEF TLT (rates), GLD SLV USO DBA
             (commodities), UUP FXE FXY (currencies) — futures proxies
             tradeable as ETFs at Schwab (or ES/NQ/ZN/ZB/GC/SI/CL/6E/6J futures)
  timing   : decide at each month-end close, hold the next month
  signal   : for each lookback k in (21, 63, 252) trading days, sign of the
             asset's total return over k days; s = mean of the three signs
  size     : w = s x (1/N) x 40% / sigma, sigma = annualized st.dev. of the last
             63 daily returns, N = number of eligible assets (eligible after
             253 closes); |w| capped at 2; gross capped at 3 (scaled down)
  rest     : T-bills on any unused capital; financing above 1x charged
Benchmark: T-bills (bench=None) — a long/short book is judged on Sharpe above
cash (RESEARCH.md §4 market-neutral rule); DBC would be an unfairly easy bar.
Costs 5bp/unit turnover (ETF; short-borrow fees NOT modelled — red-team item).
History 2007-03+ (UUP/FXY/DBA) -> signals from 2008-03; includes 2008.
Caveat: raw-return signs (no excess-over-cash) — HOP use excess returns.
trials = 35: the 30 DD-2026-11-TREND runs share the trend hypothesis, plus
this run and its 4 lookback-set variants.
"""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

UNIV = ["SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "SLV", "USO", "DBA", "UUP", "FXE", "FXY"]


def _vol(col, i, n=63):
    r = []
    for k in range(i - n + 1, i + 1):
        a, b = col[k - 1], col[k]
        if a and b:
            r.append(b / a - 1)
    if len(r) < n * 0.8:
        return None
    m = sum(r) / len(r)
    v = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
    return v or None


def make(lookbacks=(21, 63, 252), target=0.40, wcap=2.0, gcap=3.0):
    st = {}
    need = max(253, max(lookbacks) + 1)

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            elig = {}
            for s in UNIV:
                col = px[s]
                if i < need or not col[i]:
                    continue
                if sum(1 for x in col[i - need + 1:i + 1] if x) < need * 0.95:
                    continue
                signs = []
                for k in lookbacks:
                    if not col[i - k]:
                        break
                    r = col[i] / col[i - k] - 1
                    signs.append(1.0 if r > 0 else -1.0 if r < 0 else 0.0)
                v = _vol(col, i)
                if len(signs) == len(lookbacks) and v:
                    elig[s] = (sum(signs) / len(signs), v)
            n = len(elig)
            w = {}
            for s, (sig, v) in elig.items():
                x = sig * (1.0 / n) * target / v
                w[s] = max(-wcap, min(wcap, x))
            g = sum(abs(x) for x in w.values())
            if g > gcap:
                w = {s: x * gcap / g for s, x in w.items()}
            st["w"] = w
        return st.get("w", {})
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb63-252": make((63, 252)), "lb252": make((252,)),
                "lb21-63": make((21, 63)), "lb21-126-252": make((21, 126, 252))}
    res = rb.evaluate("R-2026-11-07-HOPTREND", weights, UNIV, None, start="2007-03-01",
                      cost_bps=5.0, asset_class="futures", trials=35,
                      family="trend-portfolio", variants=variants,
                      notes="HOP 1/3/12-month TSMOM, 12 ETF futures proxies, 40%/N vol-scaled long/short, "
                            "monthly; bench T-bills; borrow fees not modelled; varies DD-2026-11-TREND")
    print(json.dumps(res, indent=1))
