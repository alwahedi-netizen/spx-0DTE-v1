"""R-2026-11-21-QQQBTCBRK — REPLICATION of "Silicon vs Satoshi: tactical asset
rotation between the Nasdaq-100 and Bitcoin" (Quantpedia, 2026-07-02), the
queued ledger row I-2026-11-07-QQQBTCBRK (blocked 11-07 by the mixed-calendar
defect, fixed 2026-11-09: prices carry over gaps).

Source: https://quantpedia.com/silicon-vs-satoshi-tactical-asset-rotation-between-nasdaq-100-and-bitcoin/
Source rule: daily at QQQ's close; an asset is "in breakout" when its close is
above the highest close of the prior w trading days. Variant A: hold QQQ if
QQQ is in breakout, else BTC if BTC is, else cash (0%). Long-only, no costs,
BTC sampled (Bitfinex hourly) at QQQ's closing time. Grid w = 5..50 and
priorities A/B (16 configurations). Window 2019-01 -> 2025-12.
Source headline (variant A, w = 20): CAGR 39.5%, vol 23.5%, Sharpe 1.68,
worst drop -17.6%; benchmarks 50/50 BTC/QQQ (daily mix) Sharpe 1.19 / -59%,
QQQ 0.90 / -36%, BTC 0.89 / -77%. Variant A Sharpe across the 8 lookbacks:
1.15 - 1.69 (median ~1.52).

Hypothesis (written before any run): breakouts are a trend filter that holds
whichever of two high-beta growth assets is trending and goes to cash when
neither is; theme 1/10 says this cuts crashes. Versus a STATIC 50/50 mix
(theme 22: a crypto rule must beat the static allocation it replaces) the
claim is a higher Sharpe and a much smaller worst drop.
Counter-hypothesis: the source's grid (16 configs, best ~1.7) is in-sample on
one 7-year window dominated by 2020-21; with costs (frequent switches), an
honest BTC timestamp and T-bills on cash the edge over the static mix shrinks
below materiality.

STEP 1 — REPLICATION (league rule 1; rb.simulate only, NOT a test):
  window 2019-01-02 -> 2024-10-31 (our development data; the source's last
  14 months sit in the sealed vault), zero costs, 0% cash, source-like BTC
  timestamp (latest BTC bar dated <= the QQQ day: the 00:00 UTC bar that
  closes ~4 h AFTER QQQ — the nearest Yahoo sample to the source's 16:00
  Bitfinex sample; it peeks ~4 h and is used ONLY for this check).
  REPLICATED (pre-registered, "sign and rough size") iff ALL of:
    (a) variant A w=20 Sharpe > 50/50 daily-mix Sharpe;
    (b) variant A w=20 Sharpe >= 1.0 (~60% of the source's 1.68);
    (c) median variant-A Sharpe over the 8 lookbacks > 50/50 Sharpe.
  Not replicated -> print "harness/data suspect", no evaluate() call.
STEP 2 — TEST (one evaluate() call, only if replicated):
  RULE (fixed before any run): variant A, w = 20 (the round middle of the
  source grid), decided at the close of each US trading day (a real QQQ bar):
    QQQ breakout = QQQ close today > max of its prior 20 US-day closes;
    BTC breakout = BTC's last COMPLETED bar before today's QQQ close (Yahoo
    bar dated the previous calendar day, closed 00:00 UTC = 19:00/20:00 ET
    yesterday) > max of the same sample on the prior 20 US days;
    QQQ if QQQ breakout, elif BTC breakout BTC, else T-bills. 100% in one
    asset; held unchanged over weekends/holidays (BTC keeps moving).
DATA TIMING: the decision on US day i reads QQQ closes dated <= i (its own
close, traded at that close) and BTC bars dated < i only; weights decided at
close i earn i -> i+1 (harness). Signal history before the evaluate start is
read from the same Yahoo series (dates <= i only), so there is no warm-up
gap. A BTC trade is filled at the harness's BTC bar-i close (~4 h after the
16:00 decision): a delay, not a peek.
Benchmark: STATIC 50/50 QQQ/BTC reset on the first US trading day of each
month (synthetic BENCH-QQQBTC5050M, same 15bp). Cost 15bp per unit of
turnover on every leg = blend of QQQ (5bp, ETF floor) and BTC (25bp, crypto
default); the harness's 2x-cost gate (30bp) covers BTC-at-25bp on both legs.
Window 2019-01-01 -> vault (sealed from 2024-11-01).
Variants (neighbours): w = 10, 15, 25, 30.
PASS CRITERION (pre-registered): the harness verdict vs BENCH-QQQBTC5050M
(99% confidence + held-out win + DSR >= 0.95 + t >= 3 + 2x costs + >= 70% of
the 4 variants beat the bench). This window is the SOURCE'S OWN sample, so
even a PASS here is in-sample: it reaches the shortlist only if the
pre-sample run I-2026-11-21-QQQBTCOOS (2014-09 -> 2018-12) also holds.
trials: 16 (the source's own grid) — the harness also counts family
qqq-btc-breakout (new): 1 + 4 variants. No factor gate (FF blind to BTC).
"""
import bisect
import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "R-2026-11-21-QQQBTCBRK"
FAMILY = "qqq-btc-breakout"
Q, B = "QQQ", "BTC-USD"
START = "2019-01-01"
COST = 15.0
BENCH = "BENCH-QQQBTC5050M"
LOOKS = (5, 10, 15, 20, 25, 30, 40, 50)
SRC = {"A20_sharpe": 1.68, "mix_sharpe": 1.188, "A20_maxdd": -0.1759, "mix_maxdd": -0.5903}
_H = {}


def history():
    """Real Yahoo series used ONLY for signals (always read at dates <= i)."""
    if not _H:
        dq, pq = rb.prices([Q], "1999-01-01")
        _H["us"] = dq                                  # US trading days (real QQQ bars)
        _H["usset"] = set(dq)
        _H["q"] = dict(zip(dq, pq[Q]))
        db, pb = rb.prices([B], "2014-01-01")
        _H["bd"] = [d for d, v in zip(db, pb[B]) if v]
        _H["bv"] = [v for v in pb[B] if v]
    return _H


def btc_at(d, lag=True):
    """BTC close known at US day d's 16:00 close. lag=True: last bar dated
    BEFORE d (honest). lag=False: last bar dated <= d (source-like, ~4 h peek)."""
    h = history()
    k = bisect.bisect_left(h["bd"], d) if lag else bisect.bisect_right(h["bd"], d)
    return h["bv"][k - 1] if k > 0 else None


def breakout(series_today, prior):
    if series_today is None or len(prior) == 0 or any(x is None for x in prior):
        return False
    return series_today > max(prior)


def decide(d, w, prio="A", lag=True):
    """Target asset ('Q', 'B' or None) at the close of US day d."""
    h = history()
    k = bisect.bisect_left(h["us"], d)
    assert h["us"][k] == d                              # d is a US day
    if k < w:
        return None
    prev = h["us"][k - w:k]                             # the prior w US days (all < d)
    qb = breakout(h["q"][d], [h["q"][x] for x in prev])
    bb = breakout(btc_at(d, lag), [btc_at(x, lag) for x in prev])
    order = [("Q", qb), ("B", bb)] if prio == "A" else [("B", bb), ("Q", qb)]
    for name, on in order:
        if on:
            return name
    return None


def make(w=20, prio="A", lag=True, qsym=Q, bsym=B):
    st = {}

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["pick"] = None
        if d in history()["usset"]:
            st["pick"] = decide(d, w, prio, lag)
        p = st["pick"]
        return {qsym: 1.0} if p == "Q" else {bsym: 1.0} if p == "B" else {}
    return weights


def static_mix(qsym=Q, bsym=B, monthly=True):
    """50/50 QQQ/BTC: reset on the first US trading day of each month
    (monthly=True) or every day (the source's daily mix)."""
    st = {}
    target = {qsym: 0.5, bsym: 0.5}

    def weights(i, dates, px):
        d = dates[i]
        if not monthly:
            return dict(target)
        if i == 0:
            st.clear()
            st["w"], st["m"] = dict(target), d[:7]
            return dict(st["w"])
        grow = {}
        for s, x in st["w"].items():
            a, b = px[s][i - 1], px[s][i]
            grow[s] = x * (b / a) if (a and b) else x
        tot = sum(grow.values()) + (1 - sum(st["w"].values()))
        st["w"] = {s: g / tot for s, g in grow.items()}
        if d in history()["usset"] and d[:7] != st["m"]:
            st["m"] = d[:7]
            st["w"] = dict(target)
        return dict(st["w"])
    return weights


weights = make(20)

VARIANTS = {f"w{w}": make(w) for w in (10, 15, 25, 30)}


def bench_series():
    d, p = rb.prices([Q, B], START)
    rets, _ = rb.simulate(static_mix(), d, p, [0.0] * len(d), COST)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else rb._fetch(sym)


def _stats(r, rf):
    return {"cagr": round(rb.cagr(r), 4), "sharpe": round(rb.sharpe(r, rf), 3),
            "maxdd": round(rb.max_dd(r), 4)}


def table(lag=False):
    """Source's table on our development window: zero costs, 0% cash."""
    d, p = rb.prices([Q, B], START)
    keep = sum(1 for x in d if x < rb.VAULT_FROM)
    d, p = d[:keep], {s: v[:keep] for s, v in p.items()}
    rb.PPY = rb.periods_per_year(d)
    rf0 = [0.0] * len(d)
    out = {"period": [d[0], d[-1]], "btc_timestamp": "bar dated < day (honest)" if lag
           else "bar dated <= day (source-like, ~4 h peek)"}
    for w in LOOKS:
        r, to = rb.simulate(make(w, "A", lag), d, p, rf0, 0.0)
        out[f"A{w}"] = dict(_stats(r, rf0[1:]), turnover_per_yr=round(to / (len(r) / rb.PPY), 1))
    for name, fn in [("mix5050_daily", static_mix(monthly=False)),
                     ("mix5050_monthly", static_mix()),
                     ("QQQ", lambda i, dd, px: {Q: 1.0}), ("BTC", lambda i, dd, px: {B: 1.0})]:
        r, _ = rb.simulate(fn, d, p, rf0, 0.0)
        out[name] = _stats(r, rf0[1:])
    return out


def replicated(tab):
    a20, mix = tab["A20"]["sharpe"], tab["mix5050_daily"]["sharpe"]
    med = statistics.median(tab[f"A{w}"]["sharpe"] for w in LOOKS)
    a = a20 > mix
    b = a20 >= 1.0
    c = med > mix
    return {"a_A20_beats_mix": a, "b_A20_sharpe_ge_1": b, "c_median_beats_mix": c,
            "median_A_sharpe": round(med, 3), "source": SRC, "replicated": a and b and c}


if __name__ == "__main__":
    tab = table(lag=False)
    rep = replicated(tab)
    honest = table(lag=True)             # descriptive: what the 4 h peek was worth
    if not rep["replicated"]:
        print(json.dumps({"idea": IDEA, "skipped": True,
                          "reason": "replication failed: harness/data suspect (league rule 1)",
                          "replication": rep, "table_source_like": tab, "table_honest": honest},
                         indent=1))
        sys.exit(0)
    res = rb.evaluate(
        IDEA, weights, [Q, B], bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=16, family=FAMILY,
        variants=VARIANTS, fetch=fetch,
        notes="REPLICATION run of Quantpedia 'Silicon vs Satoshi' (2026-07): variant A w=20 daily at the "
              "QQQ close (QQQ if at a 20-day closing high, elif BTC, else T-bills); BTC signal = last bar "
              "dated before the US day (honest timestamp); vs static 50/50 QQQ/BTC monthly (synthetic "
              "BENCH-QQQBTC5050M); 15bp all legs; variants w 10/15/25/30; source's own window 2019-01 -> "
              "vault (in-sample: needs I-2026-11-21-QQQBTCOOS); trials 16 = source grid; vault 2024-11")
    print(json.dumps({"evaluate": res, "replication": rep, "table_source_like": tab,
                      "table_honest": honest}, indent=1))
