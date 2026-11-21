"""I-2026-11-21-QQQBTCOOS — sourced-idea VARIANT (out-of-sample period) of
R-2026-11-21-QQQBTCBRK: the same QQQ/BTC breakout rotation on the years the
source NEVER saw, 2014-09-17 (first Yahoo BTC bar) -> 2018-12-31.

Source: https://quantpedia.com/silicon-vs-satoshi-tactical-asset-rotation-between-nasdaq-100-and-bitcoin/
(Quantpedia 2026-07-02, window 2019-01 -> 2025-12). This script REFUSES to
run its test unless the replication in R-2026-11-21-QQQBTCBRK held (league
rule 1).

Hypothesis (written before any run): if the rotation's edge is a real trend
effect (theme 1/10) and not a fit to 2019-25, it also beats the static 50/50
QQQ/BTC mix before 2019: higher Sharpe and a smaller worst drop through the
2014-15 BTC bear, the 2017 bubble and the 2018 crash (BTC -84%, QQQ -23% in
Q4 2018). Counter-hypothesis: before 2019 BTC's breakouts were whipsaw-prone
(2014-15 grind) and QQQ held most of the time, so the rule is roughly QQQ
with cash gaps and loses to a mix that owned the 2017 BTC run outright.

RULE (identical to R-2026-11-21-QQQBTCBRK step 2, fixed before any run):
variant A, w = 20, decided at the close of each US trading day: QQQ if QQQ's
close > max of its prior 20 US-day closes, elif BTC if BTC's last completed
bar before the QQQ close (Yahoo bar dated the previous calendar day) > max of
the same sample on the prior 20 US days, else T-bills. 100% in one asset;
unchanged over weekends/holidays.
DATA TIMING: the decision on US day i reads QQQ closes dated <= i and BTC
bars dated < i only; weights decided at close i earn i -> i+1 (harness).
QQQ's signal history before 2014-09-17 is read from the same Yahoo series
(dates <= i). The window is cut at 2018-12-31 with pseudo-tickers
(suffix @2018) whose series stop there, so no 2019+ bar enters the run.
Benchmark: STATIC 50/50 QQQ/BTC reset on the first US trading day of each
month (synthetic BENCH-QQQBTC5050M@2018), same 15bp. Cost 15bp per unit of
turnover (QQQ 5bp / BTC 25bp blend; 2x-cost gate = 30bp).
Variants (neighbours, as in the replication run): w = 10, 15, 25, 30.
PASS CRITERION (pre-registered): the harness verdict vs
BENCH-QQQBTC5050M@2018 (99% confidence + held-out win + DSR >= 0.95 + t >= 3
+ 2x costs + >= 70% of the 4 variants). Learning read-out (pre-registered,
not a PASS): "edge exists out of sample" iff full-period Sharpe >= bench
Sharpe + 0.10 AND worst drop shallower than the bench's; else "the source's
edge is sample-specific". ~4.3 years cannot reach t >= 3 on a modest edge —
said now, so a FAIL on t alone is read with the learning criterion.
trials: 16 (source grid) + 5 (replication run) = 21; family qqq-btc-breakout.
No factor gate.
"""
import importlib.util
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "I-2026-11-21-QQQBTCOOS"
REPL = "R-2026-11-21-QQQBTCBRK"
TAG = "@2018"
END = "2018-12-31"
START = "2014-09-17"
COST = 15.0


def _load_repl():
    p = Path(__file__).resolve().parent / f"{REPL}.py"
    spec = importlib.util.spec_from_file_location("qqqbtcbrk", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load_repl()
Q, B = R.Q + TAG, R.B + TAG
BENCH = "BENCH-QQQBTC5050M" + TAG


def fetch_base(sym):
    """Real Yahoo series; tagged pseudo-tickers stop at END."""
    if sym.endswith(TAG):
        return {d: v for d, v in rb._fetch(sym[: -len(TAG)]).items() if d <= END}
    return rb._fetch(sym)


weights = R.make(20, qsym=Q, bsym=B)
VARIANTS = {f"w{w}": R.make(w, qsym=Q, bsym=B) for w in (10, 15, 25, 30)}


def bench_series():
    d, p = rb.prices([Q, B], START, fetch_base)
    rets, _ = rb.simulate(R.static_mix(Q, B), d, p, [0.0] * len(d), COST)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else fetch_base(sym)


if __name__ == "__main__":
    rep = R.replicated(R.table(lag=False))
    if not rep["replicated"]:
        print(json.dumps({"idea": IDEA, "skipped": True,
                          "reason": "replication of the source failed (league rule 1)", "detail": rep},
                         indent=1))
        sys.exit(0)
    res = rb.evaluate(
        IDEA, weights, [Q, B], bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=21, family=R.FAMILY,
        variants=VARIANTS, fetch=fetch,
        notes="OUT-OF-SAMPLE period for Quantpedia 'Silicon vs Satoshi' (source window 2019-25): same rule "
              "as R-2026-11-21-QQQBTCBRK (variant A w=20, honest BTC timestamp, T-bills when neither breaks "
              "out) on 2014-09-17 -> 2018-12-31 (pseudo-tickers @2018); vs static 50/50 QQQ/BTC monthly "
              "(BENCH-QQQBTC5050M@2018); 15bp; variants w 10/15/25/30; trials 21 family qqq-btc-breakout")
    edge_oos = (res["idea_sharpe"] >= res["bench_sharpe"] + 0.10
                and res["idea_maxdd"] > res["bench_maxdd"])
    learning = ("edge exists out of sample" if edge_oos else "the source's edge is sample-specific")
    print(json.dumps({"evaluate": res, "learning_readout": learning, "replication": rep}, indent=1))
