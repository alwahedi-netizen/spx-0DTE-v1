"""R-2026-11-11-CMDBAB — betting against beta inside commodities, long-only
ETF form. PROMOTES ledger row I-2026-11-10-CMDBAB (exact id checked; update
that row's id/phase, no second row).

Source: Frazzini & Pedersen, "Betting against beta", Journal of Financial
Economics 111(1), 2014 (https://www.johnhcochrane.com/s/BettingAgainstBeta.pdf ;
NBER draft https://conference.nber.org/confer/2010/BEf10/Frazzini.pdf): in
commodity futures (and every other asset class they test) alphas and Sharpe
ratios fall almost monotonically with beta; the BAB factor is long low-beta
assets levered to beta 1 and short high-beta assets de-levered to beta 1.
Betas are estimated as rho * sigma_i / sigma_m (correlation over 5 years of
3-day overlapping returns, volatility over 1 year of daily returns) and
shrunk toward 1: beta_shrunk = 0.6 * beta + 0.4 * 1.
Varies (same mechanism, other classes): R-2026-11-07-BABTSY (Treasuries),
I-2026-11-09-FXBAB (FX). Critique to keep in mind: Novy-Marx & Velikov (2022)
show much of BAB's construction is effectively equal-weighting + leverage.

RATIONALE (written before any run): leverage-constrained investors who want
commodity exposure buy the high-beta (cyclical: oil, copper, silver) contracts
instead of levering the defensive ones, bidding up high-beta and leaving
low-beta commodities with a higher risk-adjusted return. A long-only investor
who CAN lever (Schwab margin; the harness charges T-bills on gross > 1)
should earn the low-beta premium at market-like risk.
Known risk stated up front: the low-beta picks are likely gold/grains most of
the time — a hidden single bet on gold (the learnings row says so); the
unlevered variant isolates selection from leverage.

RULE (fixed before any run; the ledger row's proposed ETF form):
  universe: CANE CPER CORN GLD PALL PPLT SLV SOYB USO WEAT (the 10 single-
            commodity ETFs of CMDSKEW/CMDXSMOM); market = DBC
  at each month-end close i, for each ETF with all of its last LB daily
  returns priced together with DBC's (LB = 252):
      rho   = correlation of the ETF's and DBC's daily returns over LB days
      beta  = rho * sd(ETF) / sd(DBC), same LB window (one window for both
              parts: the paper's 5-year correlation window would start the
              test in 2016; stated deviation)
      b     = 0.6 * beta + 0.4                      (FP's shrinkage)
  need >= 5 eligible names (a real cross-section) and DBC priced;
  hold the 3 LOWEST-b ETFs, equal weight, the basket scaled so its beta is
  1: gross = min(2.0, 1 / mean(b of picks)) (cap 2x; if mean b <= 0.5,
  gross = 2); next month; else T-bills.
Benchmark: buy & hold DBC. Costs 5bp. Start 2011-09-01 (CANE/SOYB/WEAT
2011-09-19; first signal ~2012-09). No 2008 (caveat). Leverage above 1 pays
the T-bill rate (harness financing; no spread — optimistic by ~0.5%/yr on
the levered part, stated).
DATA TIMING: reads closes <= i only (harness guard); month-end test peeks
dates[i+1]'s MONTH only (calendar); trades at the signal's close (harness
convention).
Variants (neighbours): LB 126 / 504; hold 2 / 4 lowest; unlevered (gross 1,
selection only).
NEW FAMILY "cmd-bab": trials 1 + 5 = 6.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

UNIV = ["CANE", "CPER", "CORN", "GLD", "PALL", "PPLT", "SLV", "SOYB", "USO", "WEAT"]
MKT = "DBC"
START = "2011-09-01"


def _beta(px, s, i, lb):
    xs, ys = [], []
    for k in range(i - lb + 1, i + 1):
        a, b = px[s][k - 1], px[s][k]
        c, d = px[MKT][k - 1], px[MKT][k]
        if not (a and b and c and d):
            return None
        xs.append(b / a - 1)
        ys.append(d / c - 1)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs) / (n - 1)
    vy = sum((y - my) ** 2 for y in ys) / (n - 1)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
    rho = cov / math.sqrt(vx * vy)
    return rho * math.sqrt(vx) / math.sqrt(vy)


def make(lb=252, top=3, lever=True, cap=2.0, min_n=5):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        w = {}
        if i >= lb + 1 and px[MKT][i]:
            bs = {}
            for s in UNIV:
                if not px[s][i]:
                    continue
                b = _beta(px, s, i, lb)
                if b is not None:
                    bs[s] = 0.6 * b + 0.4
            if len(bs) >= max(min_n, top):
                pick = sorted(bs, key=lambda s: (bs[s], s))[:top]
                mb = sum(bs[s] for s in pick) / top
                gross = (cap if mb <= 1.0 / cap else min(cap, 1.0 / mb)) if lever else 1.0
                w = {s: gross / top for s in pick}
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"lb126": make(126), "lb504": make(504), "top2": make(252, 2),
                "top4": make(252, 4), "unlev": make(252, 3, False)}
    res = rb.evaluate("R-2026-11-11-CMDBAB", weights, UNIV + [MKT], MKT, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=6,
                      family="cmd-bab", variants=variants,
                      notes="month-end: 3 lowest shrunk-beta (0.6*beta+0.4, beta vs DBC over 252 daily returns) "
                            "of 10 commodity ETFs, equal weight, levered to basket beta 1 (cap 2x, T-bill "
                            "financing), else T-bills; bench DBC; long-only ETF form of Frazzini-Pedersen 2014; "
                            "promotes I-2026-11-10-CMDBAB")
    print(json.dumps(res, indent=1))
