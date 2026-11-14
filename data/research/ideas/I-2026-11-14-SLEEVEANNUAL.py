"""I-2026-11-14-SLEEVEANNUAL — sourced-idea VARIANT: our paper lane BTC10
(54% VT / 36% BND / 10% BTC) rebalanced YEARLY instead of monthly.
Benchmark = BTC10 itself (static, monthly — exactly the paper lane in
alloc_lab.py), per KNOWLEDGE themes 22/26: a crypto-sleeve rule must beat
the static sleeve, not the bare 60/40.

Source: Bitwise 2020 (replicated first in R-2026-11-14-BITWISEREBAL; this
script REFUSES to run its test unless that replication held):
https://www.lopp.net/pdf/Bitwise-The-Case-For-Bitcoin-In-An-Institutional-Portfolio.pdf
— 2.5% BTC sleeve 2014-01 -> 2020-03: yearly 8.59%/yr (Sharpe 0.71) vs
monthly 5.30%/yr (0.45). Also scripts the queued lab row
L-2026-11-11-SLEEVEBAND (Daryanani, "Opportunistic Rebalancing", Journal of
Financial Planning 2008: 5-15% tolerance band) as one of the variants, since
it is the same hypothesis (let the sleeve drift; reset rarely).
Varies I-2026-11-07-BTCSLEEVE (static control: rebalance frequency, not size).

Hypothesis (written before any run): BTC's medium-horizon time-series
momentum makes monthly trimming sell winners early in bull legs; a yearly
reset keeps most of the multi-year rebalancing harvest. Average BTC weight is
higher than 10% between resets in bull years — that IS the mechanism (and a
risk: worst drop may rise; we report it). Counter-hypothesis: one anchor
(early January 2018, just after the Dec 2017 peak) carries it; the
anchor variants (April, July) and the 2021/2022 cycle in the development
window test that.

RULE (fixed before any run):
  * Universe VT, BND, BTC-USD; target 54/36/10 (BTC10's weights).
  * Idea: rebalance to target at the close of the first US trading day (VT
    date) of each JANUARY; drift in between; first bar invests at target.
  * Benchmark: same target rebalanced on the first US trading day of EVERY
    month (BTC10), same 25bp, synthetic pseudo-ticker BENCH-BTC10M.
  * Variants (bench unchanged): quarterly (Jan/Apr/Jul/Oct); semi-annual
    (Jan/Jul); yearly anchored April; yearly anchored July; tolerance band
    (SLEEVEBAND): on each US trading day, if BTC's weight drifted through
    the PREVIOUS bar is < 5% or > 15%, rebalance to target at today's close.
DATA TIMING: calendar variants read no signal: a reset at close i trades back
to fixed weights from holdings drifted through bar i. The band variant reads
BTC's weight from holdings drifted through bar i-1 only (the BTC bar dated i
closes at 00:00 UTC, after VT/BND's 4pm fill), and trades at close i.
Weights decided at close i earn i -> i+1. 7-day calendar; VT/BND flat on
weekends. Costs 25bp per unit turnover on every leg. Period 2014-09-17 ->
vault (sealed from 2024-11-01).
PASS CRITERION (pre-registered): the harness verdict vs BENCH-BTC10M (PASS =
99% confidence + held-out win + DSR >= 0.95 + t >= 3 + 2x costs + >= 70% of
the 5 variants beat the bench). PROMISING (>= 90% + held-out win) earns a
shortlist note only. Report worst drop vs BTC10's and the band variant.
trials: 4 (replication) + 6 here = 10; family btc-sleeve-rebal. No factor
gate (FF blind to BTC, red team 11-10).
"""
import importlib.util
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "I-2026-11-14-SLEEVEANNUAL"
REPL = "R-2026-11-14-BITWISEREBAL"
EQ, BD, BTC = "VT", "BND", "BTC-USD"
SYMS = [EQ, BD, BTC]
TARGET = {EQ: 0.54, BD: 0.36, BTC: 0.10}
START = "2014-09-17"
COST = 25.0
BENCH = "BENCH-BTC10M"
_CAL = {}


def us_days():
    if EQ not in _CAL:
        d, _ = rb.prices([EQ], "1990-01-01")
        _CAL[EQ] = set(d)
    return _CAL[EQ]


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(months=(1,), band=None):
    """months: calendar months whose first US trading day resets to target;
    band: (lo, hi) tolerance on BTC's weight drifted through bar i-1."""
    st = {}
    months = set(months)

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["m"], st["prev"] = dict(TARGET), d[:7], dict(TARGET)
            return dict(st["w"])
        st["prev"] = dict(st["w"])        # holdings drifted through bar i-1
        st["w"] = drift(st["w"], i, px)
        if d in us_days():
            if band:
                b = st["prev"].get(BTC, 0.0)
                if b < band[0] or b > band[1]:
                    st["w"] = dict(TARGET)
            elif d[:7] != st["m"]:
                st["m"] = d[:7]           # first US trading day of the month
                if int(d[5:7]) in months:
                    st["w"] = dict(TARGET)
        return dict(st["w"])
    return weights


weights = make((1,))

VARIANTS = {
    "quarterly": make((1, 4, 7, 10)),
    "semiannual": make((1, 7)),
    "annual_apr": make((4,)),
    "annual_jul": make((7,)),
    "band_5_15": make(band=(0.05, 0.15)),
}


def bench_series():
    d, p = rb.prices(SYMS, START)
    rets, _ = rb.simulate(make(tuple(range(1, 13))), d, p, [0.0] * len(d), COST)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else rb._fetch(sym)


def replication_ok():
    """League rule 1: test the variant only if the source's headline held."""
    f = rb.RESULTS / f"{REPL}.json"
    if not f.exists():
        return False, f"{REPL} has not been run yet"
    p = Path(__file__).resolve().parent / f"{REPL}.py"
    spec = importlib.util.spec_from_file_location("bitwiserebal", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = mod.replicated(mod.table())
    return rep["replicated"], rep


if __name__ == "__main__":
    ok, why = replication_ok()
    if not ok:
        print(json.dumps({"idea": IDEA, "skipped": True,
                          "reason": "replication of the source failed or missing", "detail": why},
                         indent=1))
        sys.exit(0)
    print(json.dumps(rb.evaluate(
        IDEA, weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=10, family="btc-sleeve-rebal",
        variants=VARIANTS, fetch=fetch,
        notes="variant of Bitwise 2020 (replicated in R-2026-11-14-BITWISEREBAL): BTC10 (54% VT / 36% BND "
              "/ 10% BTC) rebalanced on the first US trading day of January vs BTC10 monthly (synthetic "
              "BENCH-BTC10M = the paper lane); 25bp all legs; variants quarterly, semi-annual, annual Apr, "
              "annual Jul, 5-15% band (L-2026-11-11-SLEEVEBAND, band read on bar i-1); no FF gate; trials "
              "10 family btc-sleeve-rebal; vault sealed from 2024-11"),
        indent=1))
