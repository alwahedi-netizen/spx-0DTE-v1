"""L-2026-11-07-TRENDLEV — lab original (RESEARCH.md §2b), the queued
combination L-TRENDLEV in KNOWLEDGE.md: DD-2026-11-TREND (10-month SMA,
potential 5, risk-reducer) x R-2026-10-28-VTSPYL (levered S&P core, potential
5). Closest published form: Gayed & Bilello 2016 Dow Award, "Leverage for the
Long Run" (https://docs.cmtassociation.org/dow-award/2016-gayed-bilello.pdf:
lever the S&P above its 200-day MA, T-bills below; 1%/yr cost of leverage).

RATIONALE (written before any run): leverage is dangerous because of crashes
and volatility drag, both of which cluster below the long-term trend (the lab
measured S&P worst drop -33% with the SMA10 filter vs -55% buy & hold). Above
the trend, volatility is lower and return streaks longer (Gayed-Bilello), so
leverage applied only then should earn more per unit of drawdown than either
the unlevered trend rule (which lags in bull markets) or always-on leverage.

RULE (fixed before any run):
  * Signal at each month's last close: VFINX (S&P 500 with dividends) close
    vs the average of its last 10 month-end closes (incl. this one).
  * Above -> hold 1.5x S&P next month; at or below -> T-bills.
  * 1.5x S&P = synthetic daily series 1.5 x VFINX return - 0.5 x T-bill
    (financing) - 1%/yr (cost of leverage, as in VTSPYL and Gayed-Bilello).
  * Variants (robustness gate): SMA 8 and 12 months at 1.5x; SMA 10 at
    1.25x and 2.0x.
  * Benchmark VFINX buy & hold (1x), 5bp/side, 1986+, strict bar with the
    vault sealed (development data < VAULT_FROM), family "L-TRENDLEV".
  * trials=15: this family's 1 + 4 variants, plus the 10 post-hoc leverage
    variants already tried in VTSPYL (the leverage level was seen there).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "L-2026-11-07-TRENDLEV"
FEE = 0.01
LEV = {"SPX_L125": 1.25, "SPX_L150": 1.5, "SPX_L200": 2.0}


def synth_fetch(sym):
    if sym not in LEV:
        return rb._fetch(sym)
    k = LEV[sym]
    base, irx = rb._fetch("VFINX"), rb._fetch("^IRX")
    out, lvl, prev, rf = {}, 100.0, None, 0.0
    for d in sorted(base):
        if irx.get(d) is not None:
            rf = irx[d] / 100 / 252
        if prev is not None:
            lvl *= 1 + k * (base[d] / prev - 1) - (k - 1) * rf - FEE / 252
        out[d] = lvl
        prev = base[d]
    return out


def make_weights(sma_m=10, sym="SPX_L150"):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["me"], st["on"] = [], False
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            c = px["VFINX"][i]
            if c is not None:
                st["me"].append(c)
            if len(st["me"]) >= sma_m and c is not None:
                st["on"] = c > sum(st["me"][-sma_m:]) / sma_m
        return {sym: 1.0} if st["on"] else {}

    return weights


weights = make_weights(10, "SPX_L150")
VARIANTS = {"sma8_150": make_weights(8, "SPX_L150"), "sma12_150": make_weights(12, "SPX_L150"),
            "sma10_125": make_weights(10, "SPX_L125"), "sma10_200": make_weights(10, "SPX_L200")}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate(
        ID, weights, ["VFINX"] + list(LEV), "VFINX", start="1986-01-01", cost_bps=5.0,
        asset_class="stocks", trials=15, family="L-TRENDLEV", variants=VARIANTS, fetch=synth_fetch,
        notes=("LAB: 1.5x S&P (T-bill financing + 1%/yr) when VFINX > 10-month SMA at month-end, "
               "else T-bills; variants SMA8/12 at 1.5x, SMA10 at 1.25x/2x; vault sealed")), indent=1))
