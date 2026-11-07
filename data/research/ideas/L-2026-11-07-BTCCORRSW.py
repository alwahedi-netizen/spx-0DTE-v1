"""L-2026-11-07-BTCCORRSW — original (RESEARCH.md §2b): Bitcoin risk-off when its
coupling to US equities accelerates during an equity drawdown. Source: lab.

Ingredients: R-2026-11-07-CORRACC (potential 4, risk-reducer: rising
correlation is a usable crisis signal; lesson = use a robust default, not
the source's tuned 1.13), and Dyer & Guest, "Crypto Contagion" (SSRN 5630550,
via Quantpedia 2026-03-27: since spot ETFs, BTC/ETH move WITH US stocks, so
crypto stopped diversifying). Queued family L-CORRSWITCH applied to crypto.

Rationale (written before any run): when BTC trades as a high-beta equity
proxy (correlation to SPY rising) while equities are falling, BTC inherits
the equity sell-off plus its own leverage-liquidation spiral (margin calls on
crypto perps, ETF outflows); when coupling is low or equities are rising,
BTC's own drift dominates. Equity weakness alone is not enough (BTC often
decouples), and coupling alone is not enough (coupled rallies are good).

RULE (fixed before any run). Pairs = (BTC close, SPY close) on SPY trading
days only; returns between consecutive SPY days (BTC's return spans the same
calendar interval, weekends included):
  * corr20 / corr60 = correlation of the last 20 / 60 paired daily returns.
  * SPY20 = SPY's return over the last 20 SPY trading days.
  * RISK-OFF (T-bills) if corr20 > max(corr60, 0) AND SPY20 < 0; else 100% BTC.
  * Re-evaluated on each SPY trading day at the BTC UTC close (after the SPY
    close: no look-ahead), held through weekends. Hold BTC until 61 pairs exist.
SPY is a signal only; only BTC-USD is ever held (so the 7-day crypto calendar
does not distort the return accounting).
Benchmark = buy & hold BTC-USD; 25bp (asset_class crypto).
Variants: windows 10/30 and 30/90; SPY trend over 10 or 40 days; no zero
floor on the correlation level.
trials: 1 + 5 variants = 6 (new family)."""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM, EQ = "BTC-USD", "SPY"


def _corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    return sab / math.sqrt(saa * sbb) if saa > 0 and sbb > 0 else 0.0


def make(n_s=20, n_l=60, eq_n=20, floor=0.0):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(pairs=[], w={SYM: 1.0})
        b, s = px[SYM][i], px[EQ][i]
        if b and s:
            st["pairs"].append((b, s))
            p = st["pairs"]
            if len(p) > max(n_l, eq_n) + 1:
                win = p[-(n_l + 1):]
                rbtc = [win[k][0] / win[k - 1][0] - 1 for k in range(1, len(win))]
                rspy = [win[k][1] / win[k - 1][1] - 1 for k in range(1, len(win))]
                c_l = _corr(rbtc, rspy)
                c_s = _corr(rbtc[-n_s:], rspy[-n_s:])
                eq = p[-1][1] / p[-1 - eq_n][1] - 1
                lvl = c_l if floor is None else max(c_l, floor)
                st["w"] = {} if (c_s > lvl and eq < 0) else {SYM: 1.0}
        return st["w"]
    return weights


weights = make()

VARIANTS = {
    "win10_30": make(n_s=10, n_l=30),
    "win30_90": make(n_s=30, n_l=90),
    "spy10": make(eq_n=10),
    "spy40": make(eq_n=40),
    "no_floor": make(floor=None),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-07-BTCCORRSW", weights, [SYM, EQ], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=6, family="crypto-corr-switch", variants=VARIANTS,
        notes="lab original: out of BTC when corr20(BTC,SPY) > max(corr60,0) and SPY 20-day return < 0; "
              "SPY signal only; 25bp; CORRACC x Dyer-Guest crypto contagion; vault sealed from 2024-11"),
        indent=1))
