"""I-2026-11-14-SLEEVEDM — sourced-idea VARIANT: BTC10's 10% crypto slot run
as Quantpedia's gold/Bitcoin dual momentum instead of static BTC.
Benchmark = BTC10 itself (54% VT / 36% BND / 10% BTC, monthly — the paper
lane), per KNOWLEDGE themes 22/26.

Source: Quantpedia 2026 (replicated first in R-2026-11-14-GLDBTCDM; this
script REFUSES to run its test unless that replication held):
https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/
Varies I-2026-11-07-GLDBTCDM (nested inside a 60/40 slot) and
L-2026-11-11-SLEEVEGOLD (which mixes BTC/gold by inverse vol; this one
ROTATES by momentum). Differs from the failed gated sleeves (SLEEVETREND,
SLEEVEVOL, BOLDTREND) in that the slot is not parked in cash when BTC
weakens: it moves to gold when gold leads, which a pure BTC gate cannot.

Hypothesis (written before any run): inside a 60/40 the slot's job is
growth with low correlation to the core. When BTC's trend breaks (2018,
2022) gold has often led (2019, 2020 H1, 2022 H2 into 2023-24); rotating the
slot keeps a positive-carry diversifier instead of cash and keeps BTC in its
bull legs. Counter-hypothesis (themes 10, 16, 22): every BTC timing rule so
far lost the rebounds and did not beat the static sleeve; weekly switching
costs 25bp on the slot; 2017 (BTC +1,300%) is in this window and any
switching that misses part of it loses to static.

RULE (fixed before any run):
  * Universe VT, BND, GLD, BTC-USD. Target core 54% VT / 36% BND; the 10%
    slot holds the dual-momentum composite: for X in {4, 8, 12} weeks, a
    third of the slot in BTC if R_btc > R_gld and R_btc > 0, in GLD if
    R_gld > R_btc and R_gld > 0, else T-bills (harness cash).
  * Weekly decision at the close of Wednesday when it is a US trading day
    (VT date): recompute the composite; if it changed, re-split the slot's
    CURRENT value (drifted BTC + GLD + slot cash) by the new composite; the
    core is left as drifted.
  * Monthly, first US trading day: reset to 54/36 core + 10% slot split by
    the latest composite (same calendar as BTC10). Warm-up (< 12 weeks of
    history, i.e. until ~2014-12-10): slot = 100% BTC (= the benchmark).
  * Benchmark: BTC10 — 54/36/10 rebalanced on the first US trading day of
    every month, same 25bp, synthetic pseudo-ticker BENCH-BTC10M.
  * Variants (bench unchanged; lookbacks scaled ~±25%/±50%, the robustness
    gate): (2,4,6), (3,6,9), (5,10,15), (6,12,18) weeks.
DATA TIMING: X-week returns read bars dated i-1 (Tuesday) and 7X days
earlier, never the trade day (BTC's bar dated i closes at 00:00 UTC, after
VT/BND/GLD's 4pm fill). The slot cash tracker drifts at 0 (T-bills are
paid by the harness on 1 - sum(weights), so the slot's cash share is the
residual). Weights decided at close i earn i -> i+1. 7-day calendar; ETFs
flat on weekends. Costs 25bp per unit turnover on every leg (GLD's real
cost is ~3bp: conservative). Period 2014-09-17 -> vault (sealed 2024-11-01).
PASS CRITERION (pre-registered): the harness verdict vs BENCH-BTC10M (PASS
needs 99% + held-out win + DSR >= 0.95 + t >= 3 + 2x costs + >= 70% of the
4 variants beating BTC10). PROMISING (>= 90% + held-out win) = shortlist
note only. Report worst drop vs BTC10's and the slot's average BTC share.
trials: 1 (replication) + 5 here = 6; family btc-gold-dualmom. No factor gate.
"""
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "I-2026-11-14-SLEEVEDM"
REPL = "R-2026-11-14-GLDBTCDM"
EQ, BD, GLD, BTC = "VT", "BND", "GLD", "BTC-USD"
SYMS = [EQ, BD, GLD, BTC]
CORE = {EQ: 0.54, BD: 0.36}
SLOT = 0.10
START = "2014-09-17"
COST = 25.0
BENCH = "BENCH-BTC10M"
_CAL = {}


def us_days():
    if EQ not in _CAL:
        d, _ = rb.prices([EQ], "1990-01-01")
        _CAL[EQ] = set(d)
    return _CAL[EQ]


def ret_back(sym, i, dates, pos, px, weeks):
    j = i - 1
    if j < 0:
        return None
    lo = (date.fromisoformat(dates[j]) - timedelta(days=7 * weeks)).isoformat()
    k = pos.get(lo)
    if k is None:
        return None
    a, b = px[sym][k], px[sym][j]
    return b / a - 1 if (a and b) else None


def composite(i, dates, pos, px, looks):
    """Shares of the slot {BTC, GLD} (rest = cash); None during warm-up."""
    out = {BTC: 0.0, GLD: 0.0}
    for x in looks:
        r_b, r_g = ret_back(BTC, i, dates, pos, px, x), ret_back(GLD, i, dates, pos, px, x)
        if r_b is None or r_g is None:
            return None
        if r_b > r_g and r_b > 0:
            out[BTC] += 1 / len(looks)
        elif r_g > r_b and r_g > 0:
            out[GLD] += 1 / len(looks)
    return out


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(looks=(4, 8, 12), static=False):
    st = {}

    def split(slot_value, comp):
        return {BTC: slot_value * comp[BTC], GLD: slot_value * comp[GLD]}

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["pos"] = {x: k for k, x in enumerate(dates)}
            st["comp"] = {BTC: 1.0, GLD: 0.0}
            st["m"] = d[:7]
            st["w"] = dict(CORE, **split(SLOT, st["comp"]))
            return {k: v for k, v in st["w"].items() if v}
        st["w"] = drift(st["w"], i, px)
        us = d in us_days()
        changed = False
        if us and not static and date.fromisoformat(d).weekday() == 2:
            c = composite(i, dates, st["pos"], px, looks)
            if c is not None and c != st["comp"]:
                st["comp"], changed = c, True
        if us and d[:7] != st["m"]:
            st["m"] = d[:7]               # first US trading day: full reset
            st["w"] = dict(CORE, **split(SLOT, st["comp"]))
        elif changed:                     # re-split the slot's current value
            slot_val = 1.0 - st["w"].get(EQ, 0.0) - st["w"].get(BD, 0.0)
            st["w"] = {EQ: st["w"].get(EQ, 0.0), BD: st["w"].get(BD, 0.0),
                       **split(slot_val, st["comp"])}
        return {k: v for k, v in st["w"].items() if v}
    return weights


weights = make()

VARIANTS = {
    "look_2_4_6": make((2, 4, 6)),
    "look_3_6_9": make((3, 6, 9)),
    "look_5_10_15": make((5, 10, 15)),
    "look_6_12_18": make((6, 12, 18)),
}


def bench_series():
    d, p = rb.prices(SYMS, START)
    rets, _ = rb.simulate(make(static=True), d, p, [0.0] * len(d), COST)
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
    j = json.loads(f.read_text())
    gain_c = j["idea_cagr"] - j["bench_cagr"]
    gain_s = j["idea_sharpe"] - j["bench_sharpe"]
    return (gain_c >= 0.09 and gain_s > 0), {"cagr_gain": gain_c, "sharpe_gain": gain_s}


if __name__ == "__main__":
    ok, why = replication_ok()
    if not ok:
        print(json.dumps({"idea": IDEA, "skipped": True,
                          "reason": "replication of the source failed or missing", "detail": why},
                         indent=1))
        sys.exit(0)
    print(json.dumps(rb.evaluate(
        IDEA, weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=6, family="btc-gold-dualmom",
        variants=VARIANTS, fetch=fetch,
        notes="variant of Quantpedia 2026 gold/BTC dual momentum (replicated in R-2026-11-14-GLDBTCDM) "
              "nested in BTC10's 10% slot: weekly Wednesday composite of 4/8/12-week rules (BTC or GLD if it "
              "leads and is positive, else T-bills), slot re-split on change, full 54/36/10 reset monthly; "
              "returns read on bars dated the day before; bench BTC10 monthly (synthetic BENCH-BTC10M); "
              "25bp all legs; variants lookbacks (2,4,6),(3,6,9),(5,10,15),(6,12,18); no FF gate; trials 6; "
              "vault sealed from 2024-11"),
        indent=1))
