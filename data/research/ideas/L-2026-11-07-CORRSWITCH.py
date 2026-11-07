"""L-2026-11-07-CORRSWITCH — lab original (RESEARCH.md §2b), the queued
combination L-CORRSWITCH in KNOWLEDGE.md: R-2026-10-28-RPARL (risk parity 2x,
potential 4) de-levered by a correlation regime switch (R-2026-11-07-CORRACC,
potential 4, showed correlation regimes are a usable risk signal).

Design choice (before any run): the switch uses the STOCK-BOND correlation,
not CORRACC's sector-ETF correlation acceleration, because RPARL's and HFEA's
recorded failure mode (learnings.csv) is stocks and bonds falling together
(2022, also 1994/1999-2000 style rate shocks) — a positive stock-bond
correlation is the direct measure of that, needs no tuned multiplier (CORRACC's
X=1.13 was picked from 26 values), and the natural threshold is 0.

RATIONALE: risk parity's leverage is safe only while bonds hedge stocks; with
negative correlation the 2x book's volatility is well below the sum of its
parts, with positive correlation the hedge vanishes and leverage multiplies a
joint drawdown. Correlation regimes are persistent (inflation/rate regimes),
so the trailing 63-day sign is informative about the next month.

RULE (fixed before any run):
  * Assets: VFINX (S&P 500), VUSTX (long Treasuries), GC=F (gold), as RPARL.
  * At each month's last close: weights proportional to 1 / (63-day stdev of
    daily returns), summing to 1 (exactly RPARL's sleeve weights).
  * Leverage: 2x when the 63-day correlation of VFINX and VUSTX daily returns
    is <= 0; 1x when it is > 0.
  * 2x legs are synthetic daily series 2 x asset return - 1 x T-bill - 1%/yr
    (RPARL's financing + fee); 1x legs are the raw assets. Weights drift
    between month-ends.
  * Variants: correlation window 42 and 84 days; threshold -0.10 and +0.10.
  * Benchmark VFINX, 5bp/side, 2000-09+ (gold history), vault sealed,
    family "L-CORRSWITCH". trials=15: 1 + 4 variants + RPARL's 10 post-hoc.
Compare against RPARL's own record (ledger): the hypothesis is the same
return shape with a smaller 2022-type loss.
"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "L-2026-11-07-CORRSWITCH"
FEE = 0.01
RAW = ["VFINX", "VUSTX", "GC=F"]
LEV2 = {"VFINX_2X": "VFINX", "VUSTX_2X": "VUSTX", "GC_2X": "GC=F"}
TO2 = {v: k for k, v in LEV2.items()}


def synth_fetch(sym):
    if sym not in LEV2:
        return rb._fetch(sym)
    base, irx = rb._fetch(LEV2[sym]), rb._fetch("^IRX")
    out, lvl, prev, rf = {}, 100.0, None, 0.0
    for d in sorted(base):
        if irx.get(d) is not None:
            rf = irx[d] / 100 / 252
        if prev is not None:
            lvl *= 1 + 2 * (base[d] / prev - 1) - rf - FEE / 252
        out[d] = lvl
        prev = base[d]
    return out


def _rets(col, n):
    """Daily returns from the last n+1 non-missing closes (None if too few)."""
    c = [x for x in col if x]
    if len(c) < n + 1:
        return None
    c = c[-(n + 1):]
    return [c[k] / c[k - 1] - 1 for k in range(1, len(c))]


def _paired(px, i, a, b, n):
    """Daily returns of a and b on days where both closes exist, last n pairs."""
    ra, rb_ = [], []
    lo = max(1, i - 3 * n)
    for k in range(lo, i + 1):
        a0, a1, b0, b1 = px[a][k - 1], px[a][k], px[b][k - 1], px[b][k]
        if a0 and a1 and b0 and b1:
            ra.append(a1 / a0 - 1)
            rb_.append(b1 / b0 - 1)
    return (ra[-n:], rb_[-n:]) if len(ra) >= n else (None, None)


def _corr(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((p - mx) * (q - my) for p, q in zip(x, y))
    sxx = sum((p - mx) ** 2 for p in x)
    syy = sum((q - my) ** 2 for q in y)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def make_weights(corr_n=63, thresh=0.0, vol_n=63):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7] and i > 3 * max(corr_n, vol_n):
            inv = {}
            for s in RAW:
                r = _rets(px[s][max(0, i - 3 * vol_n):i + 1], vol_n)
                if r is None or px[s][i] is None:
                    inv = {}
                    break
                m = sum(r) / len(r)
                sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
                inv[s] = 1 / sd if sd > 0 else 0.0
            x, y = _paired(px, i, "VFINX", "VUSTX", corr_n)
            if inv and sum(inv.values()) > 0 and x is not None:
                tot = sum(inv.values())
                lev2 = _corr(x, y) <= thresh
                tgt = {(TO2[s] if lev2 else s): v / tot for s, v in inv.items()}
                if all(px[s][i] for s in tgt):
                    st["w"], st["base"] = tgt, {s: px[s][i] for s in tgt}
                    st["last"] = dict(st["base"])
                    return dict(tgt)
        if "w" not in st:
            return {}
        v = {}
        for s, w in st["w"].items():
            p = px[s][i]
            if p:
                st["last"][s] = p
            v[s] = w * st["last"][s] / st["base"][s]
        tot = sum(v.values())
        return {s: q / tot for s, q in v.items()} if tot > 0 else {}

    return weights


weights = make_weights()
VARIANTS = {"corr42": make_weights(42, 0.0), "corr84": make_weights(84, 0.0),
            "th-0.10": make_weights(63, -0.10), "th+0.10": make_weights(63, 0.10)}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate(
        ID, weights, RAW + list(LEV2), "VFINX", start="2000-09-01", cost_bps=5.0,
        asset_class="etf", trials=15, family="L-CORRSWITCH", variants=VARIANTS, fetch=synth_fetch,
        notes=("LAB: inverse-63d-vol risk parity VFINX/VUSTX/GC=F, 2x (T-bill + 1%/yr) when 63d "
               "stock-bond corr <= 0 else 1x, monthly; variants corr 42/84d, threshold -/+0.10; "
               "vault sealed")), indent=1))
