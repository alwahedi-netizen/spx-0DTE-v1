"""R-2026-11-07-CMDXSMOM — commodity-ETF cross-sectional momentum with
volatility targeting (Quantpedia, 2026-04-29, "Commodity Portfolio Strategy
for a Potential 2026 Inflationary and Supply Shock Regime":
https://quantpedia.com/commodity-portfolio-strategy-for-a-potential-2026-inflationary-and-supply-shock-regime/ ;
canon: Miffre-Rallis 2007, Erb-Harvey 2006 — commodity momentum).

Rationale: commodity momentum is one of the best-documented commodity premia
(slow-moving inventories and hedging pressure make supply/demand shocks
persist). The source finds 12-month momentum the most robust lookback, 3-4
holdings the best balance, and per-asset 10% vol targeting the best risk-
adjusted version.

RULE (fixed before any run; the source's published defaults where given):
  universe : the source's 10 ETFs CANE CPER CORN GLD PALL PPLT SLV SOYB USO WEAT
             (an ETF is eligible once it has 253 daily closes)
  timing   : decide at each month-end close, hold the next month
  rank     : trailing 252-day total return (adjusted closes)
  hold     : the top 3, each weight = (1/3) x min(1, 10% / realized vol),
             realized vol = annualized st.dev. of the last 63 daily returns
  rest     : T-bills (no leverage, no shorts — long-only as published)
  needs >= 3 eligible ETFs, else all T-bills
Choices the source left open (FIXED here, not tuned): ranking on raw 12-month
return; 63-day vol; month-end rebalance; uninvested weight in T-bills.
Benchmark: DBC (broad commodity ETF, RESEARCH.md §4). Costs 5bp/unit turnover.
History: 2011-10+ (youngest ETFs), so development data ~2012-2024, includes
the 2014-16 commodity crash and 2020; NOT 2008 (say so in the email).
trials = 12: the source swept several lookbacks, holding counts and filters
(exact count not stated) — 12 is our honest estimate; variants add to it.
"""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ETFS = ["CANE", "CPER", "CORN", "GLD", "PALL", "PPLT", "SLV", "SOYB", "USO", "WEAT"]


def _ok(col, i, n):
    return i >= n and col[i] and col[i - n]


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


def make(lookback=252, top=3, target=0.10):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            scored = []
            for s in ETFS:
                col = px[s]
                if i < 253 or not _ok(col, i, lookback):
                    continue
                if sum(1 for x in col[i - 252:i + 1] if x) < 253 * 0.95:
                    continue                      # not yet 253 closes of history
                v = _vol(col, i)
                if v is None:
                    continue
                scored.append((col[i] / col[i - lookback] - 1, s, v))
            if len(scored) < top:
                st["w"] = {}
            else:
                scored.sort(reverse=True)
                st["w"] = {s: (1.0 / top) * min(1.0, target / v) for _, s, v in scored[:top]}
        return st.get("w", {})
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb126": make(lookback=126), "lb189": make(lookback=189),
                "lb315": make(lookback=315), "top2": make(top=2), "top4": make(top=4)}
    res = rb.evaluate("R-2026-11-07-CMDXSMOM", weights, ETFS, "DBC", start="2011-10-01",
                      cost_bps=5.0, asset_class="commodities", trials=12,
                      family="cmd-xs-momentum", variants=variants,
                      notes="top-3 of 10 commodity ETFs by 12-month return, each scaled to 10% vol (cap 1/3), "
                            "monthly, rest T-bills; bench DBC; 2011-10+ (no 2008); Quantpedia 2026-04-29 defaults")
    print(json.dumps(res, indent=1))
