"""L-2026-11-07-RPCRYPTO — original (RESEARCH.md §2b): risk parity 2x (RPARL's
stocks / long Treasuries / gold book) with Bitcoin as a 4th inverse-vol
sleeve held only while BTC is above its 10-month average.

Ingredients: R-2026-10-28-RPARL (shortlist 4, paper lane RP2X: inverse 63-day
vol on S&P / long Treasuries / gold, monthly, 2x); DD-2026-11-TREND (shortlist
5: the BTC SMA10 gate). Ledger row 2026-11-07 (rejected then ONLY for the
mixed-calendar defect fixed 2026-11-09); id kept.
Varies L-2026-11-10-SLEEVETREND (60/40 base -> levered risk parity; fixed 10%
-> inverse-vol sleeve). Its red team (2026-11-10) found the SLEEVETREND PASS
was "owning BTC", not the gate: a STATIC sleeve did as well. So, per
KNOWLEDGE theme 22, THIS script's benchmark is the static-sleeve portfolio —
the identical 4-asset risk parity 2x with BTC ALWAYS in — and the question
is only "does the trend gate add anything inside risk parity?".

Rationale (written before any run): inside an inverse-vol book BTC's sleeve
is small (its vol is ~4-5x stocks'), and BTC's multi-month bears (2018, 2022)
are when its weight is still sized off pre-crash vol; the gate removes those
episodes and hands the budget to the three classic sleeves. 2022 is RPARL's
failure regime (stocks, bonds and BTC fell together): the gate was out of BTC
for nearly all of 2022, so the drawdown should shrink. Counter-hypothesis
(red team on SLEEVETREND): the gate loses BTC's rebounds (2015, 2019, 2020,
2023) and only trims drawdown; the active return is tiny vs the static
sleeve because inverse-vol already keeps BTC's weight low.

RULE (fixed before any run):
  * Universe SPY, TLT, GLD, BTC-USD (tradeable ETFs; BTC only exists 2014+,
    so RPARL's VFINX/VUSTX/GC=F history adds nothing here — theme 9).
  * Rebalance at the close of the FIRST US trading day (SPY date) of each
    month; weights drift in between.
  * Inputs strictly before the decision day: ETF vol = sd of the last 63
    US-trading-day returns ending at the last US day < today, x sqrt(252);
    BTC vol = sd of daily returns over the 91 calendar days ending the day
    before, x sqrt(365) (same ~3-month span).
  * Weights = inverse vol, normalised to 1 over the included assets, x 2.0
    (financing at the T-bill rate, as the harness charges; no spread).
  * BTC is included only if ON: BTC's latest month-end close (bar dated the
    last calendar day of the prior month) > mean of its last 10 month-end
    closes. Off -> renormalise over SPY/TLT/GLD. Before 10 month-ends: BTC
    included (= the benchmark, neutral). Before BTC has 91 days: 3 assets
    (both rule and benchmark).
  * Benchmark = the same book with BTC always included (gate off), built
    inside this script as a synthetic series (pseudo-ticker
    BENCH-RP4STATIC2X) because evaluate() needs a ticker; same costs and
    the same financing.
DATA TIMING: every input is a bar dated before the decision day; trades at
the decision day's close (ETFs 4pm ET, BTC bar 00:00 UTC next day).
Costs 25bp per unit turnover on every leg (crypto floor; ETFs would be ~3bp,
so this is conservative for a 2x book: ~5-8 units/yr of ETF turnover).
Variants (bench unchanged): SMA 8 / 12 months; 12-month momentum gate
(latest month-end close > the one 12 months earlier); "to cash" (BTC's
inverse-vol slot goes to T-bills instead of being renormalised).
trials: family btc-sleeve-6040 (the same hypothesis: does a trend gate on a
BTC sleeve beat holding it): BTCSLEEVE10H 8 + SLEEVETREND 5 + 5 here = 18.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

EQ, TSY, GOLD, BTC = "SPY", "TLT", "GLD", "BTC-USD"
ETFS = [EQ, TSY, GOLD]
SYMS = ETFS + [BTC]
START = "2014-09-17"
COST = 25.0
LEV = 2.0
BENCH = "BENCH-RP4STATIC2X"
_CAL = {}


def us_days():
    """Real SPY pricing dates (a public exchange calendar)."""
    if EQ not in _CAL:
        d, _ = rb.prices([EQ], "1990-01-01")
        _CAL[EQ] = set(d)
    return _CAL[EQ]


def set_us_days(ds):                     # smoke tests inject a calendar
    _CAL[EQ] = set(ds)


def _sd(x):
    m = sum(x) / len(x)
    return (sum((v - m) ** 2 for v in x) / (len(x) - 1)) ** 0.5


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def vols(i, dates, px):
    """Annualised vols from bars dated strictly before dates[i]."""
    bd = us_days()
    us = [k for k in range(i - 1, -1, -1) if dates[k] in bd][:64][::-1]
    out = {}
    if len(us) == 64:
        for s in ETFS:
            p = [px[s][k] for k in us]
            if None not in p:
                out[s] = _sd([b / a - 1 for a, b in zip(p, p[1:])]) * 252 ** 0.5
    j = i - 1
    lo = (date.fromisoformat(dates[j]) - timedelta(days=91)).isoformat() if j >= 0 else None
    if lo and dates[0] <= lo:
        ks = [k for k in range(j, -1, -1) if dates[k] >= lo][::-1]
        p = [px[BTC][k] for k in ks]
        if None not in p and len(p) >= 80:
            out[BTC] = _sd([b / a - 1 for a, b in zip(p, p[1:])]) * 365 ** 0.5
    return out


def make(gate="sma", months=10, to_cash=False):
    st = {}

    def on_now():
        e = st["ends"]
        if gate == "none":
            return True
        if gate == "mom":
            return True if len(e) < 13 else e[-1] > e[-13]
        if len(e) < months:
            return True                   # warm-up: included (= benchmark)
        return e[-1] > sum(e[-months:]) / months

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["ends"], st["month"] = {}, [], None
        else:
            st["w"] = drift(st["w"], i, px)
            if dates[i][:7] != dates[i - 1][:7] and px[BTC][i - 1]:
                st["ends"].append(px[BTC][i - 1])   # BTC month-end close (bar i-1)
        d = dates[i]
        if d in us_days() and d[:7] != st["month"]:
            v = vols(i, dates, px)
            if all(s in v for s in ETFS):
                st["month"] = d[:7]
                use = dict(v)
                drop_btc = BTC in use and not on_now()
                if drop_btc and not to_cash:
                    use.pop(BTC)
                inv = {s: 1 / x for s, x in use.items() if x > 0}
                tot = sum(inv.values())
                w = {s: LEV * x / tot for s, x in inv.items()}
                if drop_btc and to_cash:
                    w.pop(BTC, None)
                st["w"] = w
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "sma8": make(months=8),
    "sma12": make(months=12),
    "mom12": make(gate="mom"),
    "to_cash": make(to_cash=True),
}


def bench_series(fn=None, syms=SYMS, start=START, cost=COST, prices=None, tbill=None):
    """Synthetic price index of the static-sleeve book (gate off), with the
    harness's own simulate, T-bill financing and costs on the idea's calendar."""
    prices, tbill = prices or rb.prices, tbill or rb.tbill
    d, p = prices(syms, start)
    rets, _ = rb.simulate(fn or make(gate="none"), d, p, tbill(d), cost)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else rb._fetch(sym)


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-07-RPCRYPTO", weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=18, family="btc-sleeve-6040",
        variants=VARIANTS, fetch=fetch,
        notes="lab original: inverse-vol SPY/TLT/GLD/BTC x2 (T-bill financing), first US trading day "
              "monthly, BTC only while its month-end close > 10-month SMA (else renormalised); inputs "
              "dated before the decision day; BENCH = the same book with BTC always in (static sleeve, "
              "synthetic BENCH-RP4STATIC2X, theme 22); 25bp all legs; variants SMA 8/12, 12-mo momentum, "
              "to-cash; vault sealed from 2024-11"),
        indent=1))
