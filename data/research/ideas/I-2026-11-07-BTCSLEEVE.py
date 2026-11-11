"""I-2026-11-07-BTCSLEEVE — the STATIC Bitcoin sleeve in a 60/40 (Bitwise /
WisdomTree), run as the CONTROL for every crypto-sleeve rule (KNOWLEDGE
theme 22; red team of L-2026-11-10-SLEEVETREND, 2026-11-10).

Source: https://bitwiseinvestments.com/crypto-market-insights/bitcoins-role-in-a-traditional-portfolio
(Bitwise: 1-5% BTC in a 60/40, quarterly rebalanced; WisdomTree/CoinShares
argue the same 1-5% range). Ledger row 2026-11-07 (rejected then ONLY for the
mixed-calendar defect fixed 2026-11-09); id kept, rule as written that day.

Rationale (written before any run): BTC's premium since 2014 has been large
and its correlation to stocks/bonds low-to-moderate; a fixed small sleeve,
rebalanced back to target, harvests part of that premium and a rebalancing
return (sell after BTC rallies, buy after crashes) at a cost of a few points
of extra drawdown. There is no timing signal: this is the static allocation
every gated sleeve (BTCSLEEVE10H, SLEEVETREND, RPCRYPTO, SLEEVEVOL) must beat
to claim its RULE adds anything. Counter-hypothesis: the result is "owning
BTC 2014-2024" and leans on 2017 (red team: ex-2017 confidence 96%);
post-2020 BTC-equity coupling (CONTAGION) erodes the diversification.

RULE (fixed before any run; the ledger's 2026-11-07 rule):
  * Universe VT (world equities), BND (US aggregate bonds), BTC-USD.
    Target = 57% VT, 38% BND, 5% BTC (= 60/40 scaled by 0.95 + 5% BTC).
  * Rebalance to target at the close of the FIRST US trading day (VT date) of
    each calendar quarter (Jan/Apr/Jul/Oct); weights drift in between. The
    first bar of the sample invests at target.
  * Benchmark = the same 60/40 VT/BND, same quarterly rebalance, same 25bp —
    built inside this script as a synthetic price series (pseudo-ticker
    BENCH-VTBND6040Q) because evaluate() needs a ticker; the active return is
    therefore the BTC sleeve alone (no fund-fee or index-mix noise).
DATA TIMING: no signal is read. Rebalancing uses only holdings drifted
through bar i. VT/BND trade at their 4pm ET close on the decision day; the
BTC leg fills at the BTC-USD bar dated that day (00:00 UTC next day, ~4-5h
later) — both executable, no bar after the decision is read.
Calendar: 7-day union; VT/BND carried flat over weekends (harness fix
2026-11-09), they earn the Fri->Mon move on Monday.
Costs 25bp per unit turnover on every leg (crypto floor; IBIT realistic ~2bp).
Variants (sleeve size and rebalance frequency, all vs the 60/40 bench):
  1% BTC, 2.5% BTC, 10% BTC (quarterly) and 5% BTC monthly.
trials: 5 here + the red team's 7 static configurations on 2026-11-10 (10%
VBINX, 5%, 20%, AOR, SPY/AGG, GBTC x2) = 12; family btc-sleeve-static.
Factor gate forced (ff5mom) for comparability with SLEEVETREND, but the red
team showed FF is blind to BTC beta (static alpha t 2.55): read it as n/a.
A static allocation is a sizing decision for the owner, never a "signal PASS".
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

EQ, BD, BTC = "VT", "BND", "BTC-USD"
SYMS = [EQ, BD, BTC]
START = "2014-09-17"
COST = 25.0
BENCH = "BENCH-VTBND6040Q"
_CAL = {}


def us_days():
    """Real VT pricing dates (a public exchange calendar)."""
    if EQ not in _CAL:
        d, _ = rb.prices([EQ], "1990-01-01")
        _CAL[EQ] = set(d)
    return _CAL[EQ]


def set_us_days(ds):                     # smoke tests inject a calendar
    _CAL[EQ] = set(ds)


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(sleeve=0.05, quarterly=True):
    st = {}
    target = {EQ: 0.6 * (1 - sleeve), BD: 0.4 * (1 - sleeve)}
    if sleeve:
        target[BTC] = sleeve

    def period(d):
        return d[:4] + "Q" + str((int(d[5:7]) - 1) // 3) if quarterly else d[:7]

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["p"] = dict(target), period(d)
            return dict(st["w"])
        st["w"] = drift(st["w"], i, px)
        if d in us_days() and period(d) != st["p"]:
            st["p"] = period(d)           # first US trading day of the period
            st["w"] = dict(target)
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "btc1": make(sleeve=0.01),
    "btc2_5": make(sleeve=0.025),
    "btc10": make(sleeve=0.10),
    "btc5_monthly": make(quarterly=False),
}


def bench_series(fn=None, syms=SYMS, start=START, cost=COST, prices=None):
    """Synthetic price index of a weights fn (the static benchmark), built
    with the harness's own simulate on the idea's calendar."""
    prices = prices or rb.prices
    d, p = prices(syms, start)
    rets, _ = rb.simulate(fn or make(sleeve=0.0), d, p, [0.0] * len(d), cost)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else rb._fetch(sym)


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "I-2026-11-07-BTCSLEEVE", weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=12, family="btc-sleeve-static",
        variants=VARIANTS, factors="ff5mom", fetch=fetch,
        notes="STATIC CONTROL: 57% VT / 38% BND / 5% BTC, rebalanced on the first US trading day of "
              "each quarter; bench = the same 60/40 VT/BND quarterly (synthetic BENCH-VTBND6040Q, 25bp), "
              "so the active return is the sleeve alone; 25bp all legs; no signal (sizing question for "
              "the owner); FF gate blind to BTC (red team 11-10) — read as n/a; variants 1/2.5/10% "
              "quarterly, 5% monthly; vault sealed from 2024-11"),
        indent=1))
