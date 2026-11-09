"""L-2026-11-09-CURVEPAIRS — lab original (RESEARCH.md §2b), 2026-11-09:
the CARRYPROXY curve signal on a SECOND market (natural gas), run as a two-leg book.

VARIES: L-2026-11-07-CARRYPROXY (potential 4; oil only). Same signal, same
window, applied to the only other commodity with a front-month ETF AND a
12-month-ladder ETF from the same sponsor: UNG (front natural gas, rolls to the
2nd month two weeks before expiry) vs UNL (12 consecutive monthly NG contracts,
equal weights; lists 2009-11).

SOURCES / INGREDIENTS:
  * Boons & Porras Prado, "Basis-Momentum", JF 74(1) 2019
    (https://ideas.repec.org/a/bla/jfinan/v74y2019i1p239-279.html): basis
    momentum predicts returns across commodities, not only oil.
  * WisdomTree, "Please mind the slope" (Jan 2026,
    https://www.wisdomtree.com/gb/insights/blog/please-mind-the-slope-why-futures-curves-matter):
    time-series slope momentum 3.8%/yr (t 2.0) across 2001-2025 curves.
  * Gorton, Hayashi & Rouwenhorst, Review of Finance 17(1) 2013: a tightening
    curve signals low inventories and a high futures risk premium.

RATIONALE (written before any run): if CARRYPROXY is a real curve effect and not
an oil accident, the same price-only proxy should work on natural gas, the
market with the steepest, most persistent contango (UNG lost ~99% buy-and-hold)
— exactly where staying out while the ladder outruns the front should save the
most. Holding the two legs together also halves single-market risk. This is an
out-of-market replication of a shortlisted signal, so it shares CARRYPROXY's
trial family (the bar rises for both).

RULE (fixed before any run):
  at each month-end close i, for each pair (front, ladder) in
  [(USO, USL), (UNG, UNL)]:
    leg on if front 63-day return > ladder 63-day return (both priced at i and i-63)
    an "on" leg gets 50% of capital in its FRONT ETF; an "off" leg's 50% is T-bills
Benchmark: buy & hold DBC (multi-commodity book; DBC is the desk's standard
yardstick and a far tougher one than USO or UNG buy-and-hold, both deeply
negative). Costs 5bp. Start 2009-12-01 (UNL's first 63-day window completes
~2010-04; the oil leg starts at the same time so the book is the same shape
throughout). Includes the 2014-16 commodity crash and 2020.
Variants (neighbours of the window, as CARRYPROXY): 21, 42, 126, 189 days.
FAMILY "L-2026-11-07-CARRYPROXY": lifetime 5 + OILCURVETREND 5 (if run first
tonight) + this run 5 -> trials 15 (the harness raises it if needed).
Diagnostic (no extra verdict, no extra trial): each leg alone vs its own front
ETF over the same window — the gas leg alone is the true out-of-market test.
Known caveats stated before the run: UNG spread its holdings across months in
2009-10 under position limits; USO changed its roll method in 2020-04.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

PAIRS = [("USO", "USL"), ("UNG", "UNL")]
SYMS = [s for p in PAIRS for s in p]
START = "2009-12-01"


def make(lb=63, pairs=PAIRS):
    st = {"w": {}}
    share = 1.0 / len(pairs)

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        w = {}
        for f, l in pairs:
            a, b = px[f], px[l]
            if (i >= lb and a[i] and a[i - lb] and b[i] and b[i - lb]
                    and a[i] / a[i - lb] > b[i] / b[i - lb]):
                w[f] = share
        st["w"] = w
        return w
    return weights


weights = make()


def leg_report(lb=63):
    """Diagnostic only: each leg at 100% vs buy & hold of its own front ETF."""
    dates, px = rb.prices(SYMS + ["DBC"], START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    rf1 = rf[1:]
    out = {}
    for f, l in PAIRS:
        rets, _ = rb.simulate(make(lb, [(f, l)]), dates, px, rf, 5.0)
        bret = rb.bench_returns(f, dates, px, rf)
        out[f] = {"leg_sharpe": round(rb.sharpe(rets, rf1), 3), "front_sharpe": round(rb.sharpe(bret, rf1), 3),
                  "leg_cagr": round(rb.cagr(rets), 4), "front_cagr": round(rb.cagr(bret), 4),
                  "leg_maxdd": round(rb.max_dd(rets), 4), "front_maxdd": round(rb.max_dd(bret), 4)}
    return out


if __name__ == "__main__":
    variants = {f"lb{k}": make(k) for k in (21, 42, 126, 189)}
    res = rb.evaluate("L-2026-11-09-CURVEPAIRS", weights, SYMS, "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=15,
                      family="L-2026-11-07-CARRYPROXY", variants=variants,
                      notes="month-end: 50% USO if USO 63d > USL 63d, 50% UNG if UNG 63d > UNL 63d, "
                            "else that half in T-bills; bench DBC; varies L-2026-11-07-CARRYPROXY "
                            "(adds natural gas); lab original; vault sealed")
    res["leg_diagnostic"] = leg_report()
    print(json.dumps(res, indent=1))
