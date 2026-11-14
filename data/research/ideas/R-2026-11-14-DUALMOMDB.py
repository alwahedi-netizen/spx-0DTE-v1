"""R-2026-11-14-DUALMOMDB — dual momentum across the four Invesco DB commodity
sector ETFs (replication of the source on its own universe and period).
PROMOTES ledger row I-2026-11-11-DUALMOMDB (update that row's id/phase; no
second row). League round 1, commodities desk.

Source: Cyril Dujava, "Dual vs. Single Momentum in Commodities: Enhancing
Risk-Adjusted Returns through Absolute Trend Filtering", Quantpedia, 2026-06-15
https://quantpedia.com/dual-vs-single-momentum-in-commodities-enhancing-risk-adjusted-returns-through-absolute-trend-filtering/
Universe DBA (agriculture), DBB (base metals), DBE (energy), DBP (precious
metals), 2007-01-05 -> 2026-02-27, adjusted closes, month-end rebalance; rank
by X-month rate of change, hold the top M equal weight, each held name only if
its price is strictly above its X-month SMA (else that slot is cash at 0%).
0bp costs, 0% cash. Published headline (Table 2, X=3, M=3):
    7.54%/yr, vol 11.92%, Sharpe 0.63, max drawdown -30.07%
vs static equal-weight buy-and-hold of the four: 4.76%/yr, Sharpe 0.30, -53.25%;
all 12 dual-momentum grid cells (X 3/6/9/12 x M 1/2/3) beat that benchmark on
Sharpe, while relative momentum alone failed 7 of 12.
Varies (same family): R-2026-11-07-CMDXSMOM (cross-sectional momentum on 10
single-commodity ETFs, graveyard) and L-2026-11-07-XSMOMGATE (broad trend
gate). The new ingredient is the per-asset absolute filter on sector ETFs.

HYPOTHESIS (written before any run): commodity sector trends persist
(time-series momentum: slow-moving hedging/inventory adjustment), and the
absolute filter moves the portfolio to cash in commodity bear markets (2008,
2014-15, 2020) that cross-sectional ranking alone keeps fully invested in.
REPLICATION CHECK (pre-registered, judged on the printed result): the run
reproduces the source if CAGR is within 7.5% +/- 3pp and the worst drop within
-30% +/- 10pp (sign and rough size). Differences stated up front: our window
ends 2024-10-31 (the vault), cash earns T-bills (source 0%) — which LIFTS our
return slightly, and costs are 5bp (source 0bp).
PASS CRITERION (pre-registered): research_bt verdict PASS vs buy-and-hold DBC
(all §0 gates incl. DSR with the family's lifetime trials and >= 70% of the
11 other grid cells beating DBC). Anything less is FAIL/PROMISING as the
harness says; the replication check is reported separately.

RULE (the source's, fixed before any run):
  at each month-end close i (next bar falls in a new month):
    for each of DBA DBB DBE DBP priced at i and at i - 21*X:
        roc = px[i] / px[i - 21*X] - 1
        sma = mean of the last 21*X daily closes (i - 21*X + 1 .. i); every
              one must be priced (an X-month SMA on daily bars: the source
              does not state its sampling; stated choice)
    need all 4 eligible (else all cash); rank by roc (ties by name); take the
    top M; each pick gets 1/M if px[i] > sma, else its slot stays in T-bills.
  held to the next month-end.
Benchmark: buy & hold DBC (class rule). The source's benchmark (static EW
buy-and-hold of the four ETFs) is printed as a data check, computed here from
the same prices without research_bt.
Costs 5bp. Start 2007-01-01 (the ETFs list 2007-01-05; X=3 is live from the
2007-04 month-end — the 3 warm-up months are cash, as in the source). Includes
2008, 2014-16, 2020, 2022.
DATA TIMING: the signal reads closes dated <= i only (harness guard); the
month-end test peeks only at dates[i+1]'s MONTH (calendar); weights decided at
close i earn close i -> close i+1 (harness convention).
Variants (the source's own grid, all of which the source searched): the 11
other (X, M) cells, X in 3/6/9/12, M in 1/2/3.
FAMILY "cmd-xs-momentum" (shared with CMDXSMOM: same commodity-momentum
hypothesis) -> trials 6 + 1 + 11 = 18.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

UNIV = ["DBA", "DBB", "DBE", "DBP"]
BENCH = "DBC"
START = "2007-01-01"


def make(x=3, m=3):
    n = 21 * x
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        w = {}
        if i >= n:
            roc, sma = {}, {}
            for s in UNIV:
                a, b = px[s][i - n], px[s][i]
                if not (a and b):
                    continue
                win = [px[s][k] for k in range(i - n + 1, i + 1)]
                if not all(win):
                    continue
                roc[s] = b / a - 1
                sma[s] = sum(win) / n
            if len(roc) == len(UNIV):
                picks = sorted(UNIV, key=lambda s: (-roc[s], s))[:m]
                w = {s: 1.0 / m for s in picks if px[s][i] > sma[s]}
        st["w"] = w
        return w
    return weights


weights = make()


def _ew_bh():
    """Source benchmark: static equal-weight buy-and-hold of the four ETFs
    (not rebalanced), over the same development window. Data check only."""
    d, p = rb.prices(UNIV, START)
    keep = [k for k, x in enumerate(d) if x < rb.VAULT_FROM and all(p[s][k] for s in UNIV)]
    k0, k1 = keep[0], keep[-1]
    val = [sum(p[s][k] / p[s][k0] for s in UNIV) / 4 for k in keep]
    rets = [val[j] / val[j - 1] - 1 for j in range(1, len(val))]
    yrs = len(rets) / 252
    peak, dd = val[0], 0.0
    for v in val:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
    return {"period": [d[k0], d[k1]], "cagr": round(val[-1] ** (1 / yrs) - 1, 4),
            "sharpe_rf0": round(mu / sd * math.sqrt(252), 3), "maxdd": round(dd, 4)}


if __name__ == "__main__":
    variants = {f"x{x}m{m}": make(x, m) for x in (3, 6, 9, 12) for m in (1, 2, 3)
                if (x, m) != (3, 3)}
    res = rb.evaluate("R-2026-11-14-DUALMOMDB", weights, UNIV + [BENCH], BENCH, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=18,
                      family="cmd-xs-momentum", variants=variants,
                      notes="month-end: rank DBA/DBB/DBE/DBP by 63-day ROC, hold top 3 at 1/3 each, each only if "
                            "above its 63-day SMA, else that slot in T-bills; bench DBC; 5bp; replication of "
                            "Quantpedia 2026-06-15 (source X=3,M=3: 7.54%/yr, Sharpe 0.63, maxDD -30.07%, 0bp, 0% "
                            "cash); variants = the source's other 11 grid cells; promotes I-2026-11-11-DUALMOMDB")
    print(json.dumps(res, indent=1))
    cagr, dd = res.get("idea_cagr"), res.get("idea_maxdd")
    rep = (cagr is not None and dd is not None and abs(cagr - 0.075) <= 0.03 and abs(dd - (-0.30)) <= 0.10)
    print(json.dumps({"replication_check": "REPRODUCED" if rep else "NOT REPRODUCED",
                      "ours": {"cagr": cagr, "maxdd": dd}, "source": {"cagr": 0.0754, "maxdd": -0.3007},
                      "source_benchmark_ew4_buyhold_same_window": _ew_bh(),
                      "source_benchmark_published": {"cagr": 0.0476, "sharpe_rf0": 0.30, "maxdd": -0.5325}},
                     indent=1))
