"""L-2026-11-08-HAVENBASKET — lab original (RESEARCH.md §2b), designed 2026-11-08
by the commodities desk, scripted 2026-11-09 from the queue (ledger row keeps its id).

VARIES: L-2026-11-07-SAFEHAVEN (potential 4: yen + franc only while the S&P 500
is below its 10-month SMA). Same switch; the haven basket ADDS GOLD and sizes the
three legs by inverse volatility instead of 50/50.

INGREDIENTS / SOURCES:
  * DD-2026-11-TREND (potential 5): the S&P 10-month SMA state is the lab's most
    reliable risk-off flag (cut the worst drop on almost every asset).
  * Ranaldo & Soderlind, "Safe Haven Currencies", Review of Finance 14(3), 2010:
    JPY and CHF appreciate when US stocks fall.
  * Baur & Lucey, "Is Gold a Hedge or a Safe Haven?", Financial Review 45(2), 2010
    (https://econpapers.repec.org/RePEc:bla:finrev:v:45:y:2010:i:2:p:217-229):
    gold is a safe haven for stocks in extreme down markets.
  * Independent descriptive support (read before the run, not used to set the
    rule): CXO Advisory, "Best Safe Haven ETF?" (May 2026,
    https://www.cxoadvisory.com/commodity-futures/best-safe-haven-etf/): of 16
    funds, GLD and SLV held up best in months when the S&P 500 was below its
    10-month SMA at the prior month-end.

RATIONALE (written before any run): SAFEHAVEN's weakness was 2022 — an equity
bear market with RISING US rates, when the yen collapsed. Gold's crisis behaviour
is driven by different buyers (central banks, real-asset demand) and it held up
in 2022 better than the yen; adding it diversifies the haven sleeve across
drivers. Inverse-vol sizing stops the most volatile haven (gold, ~2x the
currencies' vol) from dominating the sleeve's risk.

RULE (fixed before any run; exactly the ledger row's stated rule):
  at each month-end close i:
    if SPY < mean of the last 10 month-end SPY closes (incl. this one):
        hold GLD, FXY, FXF next month with weights proportional to
        1 / (63-day stdev of daily returns), summing to 1
        (all three need a price today and >= 60 of the last 63 returns,
         else T-bills)
    else: T-bills
Benchmark: T-bills (bench=None). WHY not DBC: this is a crisis sleeve that is in
cash ~75% of the time; the ledger row fixed T-bills before any run and the
SAFEHAVEN family (SAFEHAVEN / HAVENVOL / HAVENRATES) was judged against T-bills,
so the same yardstick keeps the family comparable. Costs 5bp (asset_class
commodities). Start 2006-05-01 (SPY SMA warm-up); FXY lists 2007-02, so
positions from 2007.
Variants (neighbours): SMA 8, 9, 11, 12 months; equal weights (1/3 each).
FAMILY "L-fx-safehaven" (shared with the FX desk): lifetime trials before this
run = 15 (SAFEHAVEN 5 + HAVENRATES 5 + HAVENVOL 5); this run adds 1 + 5 = 6
-> trials = 21. If the FX desk runs another safe-haven variant first tonight the
harness raises the count automatically.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

HAVENS = ["GLD", "FXY", "FXF"]
SYMS = HAVENS + ["SPY"]
VOL_N = 63


def _vol(col, i, n=VOL_N):
    r = []
    for k in range(i - n + 1, i + 1):
        if k < 1:
            return None
        a, b = col[k - 1], col[k]
        if a and b:
            r.append(b / a - 1)
    if len(r) < 60:
        return None
    m = sum(r) / len(r)
    v = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
    return v if v > 0 else None


def make(n_months=10, inv_vol=True):
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []      # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if px["SPY"][i]:
                st["me"].append(px["SPY"][i])
            me = st["me"]
            off = len(me) >= n_months and me[-1] < sum(me[-n_months:]) / n_months
            w = {}
            if off and all(px[h][i] for h in HAVENS):
                if inv_vol:
                    vols = {h: _vol(px[h], i) for h in HAVENS}
                    if all(vols.values()):
                        inv = {h: 1.0 / v for h, v in vols.items()}
                        tot = sum(inv.values())
                        w = {h: x / tot for h, x in inv.items()}
                else:
                    w = {h: 1.0 / len(HAVENS) for h in HAVENS}
            st["w"] = w
        return st["w"] or {}
    return weights


weights = make(10)

if __name__ == "__main__":
    variants = {"SMA8": make(8), "SMA9": make(9), "SMA11": make(11), "SMA12": make(12),
                "EQW": make(10, inv_vol=False)}
    r = rb.evaluate("L-2026-11-08-HAVENBASKET", weights, SYMS, None, start="2006-05-01",
                    cost_bps=5.0, asset_class="commodities", trials=21, family="L-fx-safehaven",
                    variants=variants,
                    notes="month-end: if SPY < 10-month SMA hold GLD/FXY/FXF inverse 63d-vol weights, "
                          "else T-bills; bench T-bills (crisis sleeve, family yardstick); varies "
                          "L-2026-11-07-SAFEHAVEN (adds gold); lab original; vault sealed")
    print(json.dumps(r, indent=1))
