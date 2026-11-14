"""R-2026-11-14-GLDBTCDM — REPLICATION (league rule 1) of Quantpedia's dual
momentum between gold and Bitcoin. Scripts ledger row I-2026-11-07-GLDBTCDM
(blocked 11-07 only by the mixed-calendar defect, fixed 2026-11-09).

Source: Quantpedia, "Dual Momentum Allocation Between Physical Gold and
Bitcoin (Digital Gold)", May 2026 —
https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/
Published headline (2018-12-31 -> 2026-04, no costs, cash earns 0):
    Bitcoin buy & hold        46.66%/yr  vol 64.0%  Sharpe 0.73  max DD -77.5%
    GLD buy & hold            18.80%/yr             Sharpe 1.10
    Dual momentum, composite  64.73%/yr  vol 44.1%  Sharpe 1.47  max DD -49.4%
    (8-week alone: 79.91%/yr, Sharpe 1.64; vol-capped composite 12.0%/yr)

Hypothesis (written before any run): gold and BTC are both "store of value"
assets whose regimes alternate (BTC in liquidity booms, gold in risk-off /
real-rate falls); relative momentum picks the one in its regime and absolute
momentum steps aside when both fall (2022), so the rotation keeps most of
BTC's upside at a smaller drawdown. Counter-hypothesis: the period is short
(two BTC cycles), the lookbacks were picked from a grid of 10, and our 25bp
cost on weekly switches eats much of it.

RULE (the source's, fixed before any run):
  * Universe GLD, BTC-USD. Decision once a week at the close of WEDNESDAY
    when it is a US trading day (GLD date); a Wednesday holiday skips that
    week (positions held).
  * For X in {4, 8, 12} weeks: R_btc, R_gld = X-week returns; hold BTC if
    R_btc > R_gld and R_btc > 0; GLD if R_gld > R_btc and R_gld > 0; else
    cash. Composite = equal thirds of the three positions (position average).
  * Warm-up (until 12 weeks of history exist, ~2019-03-27): hold BTC, i.e.
    the benchmark, so the warm-up is neutral.
  * Cash earns T-bills (source: 0). Benchmark = BTC-USD buy & hold (the
    source's Table 1 comparison). Not tested: the 20% vol-capped version
    (a cash-dominated variant; the source's pure composite is the headline).
DATA TIMING: returns are measured on bars dated Tuesday (i-1) and the
weekly date 7X days earlier — never the trade day: BTC's Wednesday bar
closes at 00:00 UTC, after GLD's 4pm fill, so reading it would be ~4h of
look-ahead for the GLD leg. Trades at Wednesday's close (GLD 4pm; BTC bar
dated Wednesday). Weights decided at close i earn i -> i+1; quantities
drift between decisions (no daily rebalance inside the week).
Our window: 2018-12-31 -> vault (2024-10-31), ~5.8 of the source's 7.3
years (the rest is sealed in the vault). 7-day calendar, GLD flat on
weekends. Costs 25bp per unit turnover (source: none).
PASS CRITERION FOR THE REPLICATION (pre-registered): replicated = composite
CAGR - BTC CAGR >= +9%/yr (half the source's +18%, net of our costs) AND
composite Sharpe > BTC's. The harness verdict vs BTC is recorded as the
idea's own result. If not replicated, I-2026-11-14-SLEEVEDM refuses to run.
trials: 1 (+ the source's grid of 10 lookbacks noted, not run); family
btc-gold-dualmom (new: R-2026-11-10-BOLD's btc-gold-mix family is a static
inverse-vol mix, a different hypothesis). No factor gate.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "R-2026-11-14-GLDBTCDM"
GLD, BTC = "GLD", "BTC-USD"
SYMS = [GLD, BTC]
START = "2018-12-31"
COST = 25.0
LOOKS = (4, 8, 12)
_CAL = {}


def us_days():
    """Real GLD pricing dates (NYSE calendar)."""
    if GLD not in _CAL:
        d, _ = rb.prices([GLD], "1990-01-01")
        _CAL[GLD] = set(d)
    return _CAL[GLD]


def is_decision(d):
    return d in us_days() and date.fromisoformat(d).weekday() == 2


def ret_back(sym, i, dates, px, weeks, pos):
    """X-week return measured on the bar dated i-1 vs 7X days before it."""
    j = i - 1
    if j < 0:
        return None
    lo = (date.fromisoformat(dates[j]) - timedelta(days=7 * weeks)).isoformat()
    k = pos.get(lo)
    if k is None:
        return None
    a, b = px[sym][k], px[sym][j]
    return b / a - 1 if (a and b) else None


def signal(i, dates, px, pos, looks):
    """Composite position {BTC: x, GLD: y}, each x, y in thirds; None = warm-up."""
    out = {BTC: 0.0, GLD: 0.0}
    for x in looks:
        rb_, rg = ret_back(BTC, i, dates, px, x, pos), ret_back(GLD, i, dates, px, x, pos)
        if rb_ is None or rg is None:
            return None
        if rb_ > rg and rb_ > 0:
            out[BTC] += 1 / len(looks)
        elif rg > rb_ and rg > 0:
            out[GLD] += 1 / len(looks)
    return out


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(looks=LOOKS):
    st = {}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["pos"] = {d: k for k, d in enumerate(dates)}
            st["w"] = {BTC: 1.0}          # warm-up (first 12 weeks) = the benchmark
        else:
            st["w"] = drift(st["w"], i, px)
        if is_decision(dates[i]):
            s = signal(i, dates, px, st["pos"], looks)
            if s is not None:
                st["w"] = {k: v for k, v in s.items() if v}
        return dict(st["w"])
    return weights


weights = make()

if __name__ == "__main__":
    res = rb.evaluate(
        IDEA, weights, SYMS, bench=BTC, start=START,
        asset_class="crypto", cost_bps=COST, trials=1, family="btc-gold-dualmom",
        notes="REPLICATION of Quantpedia 2026 gold/BTC dual momentum: weekly (Wednesday US close) composite "
              "of 4/8/12-week rules (hold the better of BTC/GLD if its X-week return > 0, else cash), thirds; "
              "returns read on bars dated the day before; bench BTC-USD; T-bills on cash; 25bp; window "
              "2018-12-31 -> vault (source to 2026-04); replication = CAGR >= BTC + 9%/yr and higher Sharpe")
    rep = {"cagr_gain": round(res["idea_cagr"] - res["bench_cagr"], 4),
           "sharpe_gain": round(res["idea_sharpe"] - res["bench_sharpe"], 3)}
    rep["replicated"] = rep["cagr_gain"] >= 0.09 and rep["sharpe_gain"] > 0
    print(json.dumps({"evaluate": res, "replication": rep}, indent=1))
