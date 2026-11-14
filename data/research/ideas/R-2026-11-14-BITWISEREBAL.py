"""R-2026-11-14-BITWISEREBAL — REPLICATION (league rule 1) of Bitwise's
rebalancing-frequency table for a small Bitcoin sleeve in a VT/BND 60/40.

Source: Bitwise Asset Management, "The Case for Bitcoin in an Institutional
Portfolio" (2020), section "What is the best rebalancing frequency for a
bitcoin allocation?" — https://www.lopp.net/pdf/Bitwise-The-Case-For-Bitcoin-In-An-Institutional-Portfolio.pdf
(summary: https://bitwiseinvestments.com/crypto-market-insights/bitcoins-role-in-a-traditional-portfolio).
Published headline (2014-01-01 -> 2020-03-31, 60% VT / 40% BND, 2.5% BTC):
    Traditional 60/40           3.51%/yr  Sharpe 0.270
    2.5% BTC, no rebalancing    5.80%/yr  Sharpe 0.358
    2.5% BTC, yearly            8.59%/yr  Sharpe 0.711
    2.5% BTC, quarterly         6.13%/yr  Sharpe 0.535
    2.5% BTC, monthly           5.30%/yr  Sharpe 0.453
i.e. LESS frequent calendar rebalancing (yearly) earned MORE than monthly
(the frequency our paper lane BTC10 uses). Bitwise adds that a 2018
tolerance-band study gave results "largely in line with quarterly".

Hypothesis (written before any run): BTC has positive medium-horizon
time-series momentum (Liu & Tsyvinski RFS 2021: 1-8 week; our own DD-TREND),
so trimming the sleeve every month sells winners too early inside bull legs;
yearly rebalancing lets the sleeve run for months yet still harvests the
mean-reversion at multi-year horizons (2018, 2022) that no-rebalance misses.
Counter-hypothesis: the yearly result is one lucky anchor (Jan 2018 sold
near the Dec 2017 peak by chance) — this is why the follow-up
I-2026-11-14-SLEEVEANNUAL tests several anchors.

THIS SCRIPT only replicates. Our data cannot reproduce the source's exact
period: Yahoo BTC-USD starts 2014-09-17 (source: 2014-01-01; BTC fell
~$755 -> ~$457 in the missing 8.5 months, which flatters our BTC legs).
Replication window = 2014-09-17 -> 2020-03-31 (source end), built with
pseudo-tickers (suffix @2020Q1) whose series stop at 2020-03-31.

RULE (the source's, fixed before any run):
  * Traditional = 60% VT / 40% BND, rebalanced on the first US trading day
    (VT date) of each calendar quarter -> synthetic benchmark
    BENCH-VTBND6040Q@2020Q1 (same 25bp), because evaluate() needs a ticker.
  * Idea (the source's headline row) = 58.5% VT / 39% BND / 2.5% BTC-USD,
    rebalanced to target on the first US trading day of each JANUARY;
    weights drift in between; the first bar invests at target.
  * Descriptive table (printed after the evaluate run, not a separate test):
    the same sleeve with monthly / quarterly / yearly / no rebalancing.
DATA TIMING: no signal is read. A rebalance at close i trades back to fixed
target weights; holdings drift through bar i only. VT/BND fill at their
4pm ET close on day i; the BTC leg at the BTC-USD bar dated i (00:00 UTC
next day). Weights decided at close i earn i -> i+1 (harness).
Calendar: 7-day union; VT/BND carried flat over weekends (harness fix 11-09).
Costs 25bp per unit turnover on every leg (crypto floor; source: none).

PASS CRITERION FOR THE REPLICATION (pre-registered): replicated = BOTH
  (a) yearly 2.5% sleeve CAGR - Traditional CAGR >= +2.5%/yr (source +5.1;
      half counts as "rough size") AND its Sharpe > Traditional's; and
  (b) the frequency sign: yearly-rebalanced CAGR > monthly-rebalanced CAGR.
If not replicated: log "harness/data suspect" and I-2026-11-14-SLEEVEANNUAL
refuses to run (it checks this file's result). The harness verdict
(PASS/FAIL vs Traditional) is NOT the replication test — 5.5 years cannot
reach 99%; it is reported for the record only.
trials: 4 configurations looked at (yearly + the 3 descriptive rows);
family btc-sleeve-rebal (new: no existing family tests rebalance frequency;
btc-sleeve-static counted sleeve SIZE). No factor gate (FF blind to BTC).
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "R-2026-11-14-BITWISEREBAL"
TAG = "@2020Q1"
END = "2020-03-31"
EQ, BD, BTC = "VT" + TAG, "BND" + TAG, "BTC-USD" + TAG
SYMS = [EQ, BD, BTC]
START = "2014-09-17"
COST = 25.0
SLEEVE = 0.025
BENCH = "BENCH-VTBND6040Q" + TAG
FREQ = {"M": set(range(1, 13)), "Q": {1, 4, 7, 10}, "A": {1}, "N": set()}
_CAL = {}


def fetch_base(sym):
    """Real Yahoo series; tagged pseudo-tickers stop at the source's end."""
    if sym.endswith(TAG):
        base = sym[: -len(TAG)]
        return {d: v for d, v in rb._fetch(base).items() if d <= END}
    return rb._fetch(sym)


def us_days():
    """Real VT pricing dates (a public exchange calendar)."""
    if EQ not in _CAL:
        d, _ = rb.prices([EQ], "1990-01-01", fetch_base)
        _CAL[EQ] = set(d)
    return _CAL[EQ]


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(sleeve=SLEEVE, freq="A"):
    st = {}
    target = {EQ: 0.6 * (1 - sleeve), BD: 0.4 * (1 - sleeve)}
    if sleeve:
        target[BTC] = sleeve
    months = FREQ[freq]

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["m"] = dict(target), d[:7]
            return dict(st["w"])
        st["w"] = drift(st["w"], i, px)
        if d in us_days() and d[:7] != st["m"]:
            st["m"] = d[:7]               # first US trading day of the month
            if int(d[5:7]) in months:
                st["w"] = dict(target)
        return dict(st["w"])
    return weights


weights = make()


def bench_series():
    d, p = rb.prices(SYMS, START, fetch_base)
    rets, _ = rb.simulate(make(sleeve=0.0, freq="Q"), d, p, [0.0] * len(d), COST)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else fetch_base(sym)


def table():
    """The source's frequency table on our window (descriptive)."""
    d, p = rb.prices(SYMS, START, fetch_base)
    rb.PPY = rb.periods_per_year(d)
    rf = rb.tbill(d)
    out = {}
    for name, fn in [("traditional_Q", make(0.0, "Q")), ("none", make(freq="N")),
                     ("yearly", make(freq="A")), ("quarterly", make(freq="Q")),
                     ("monthly", make(freq="M"))]:
        r, _ = rb.simulate(fn, d, p, rf, COST)
        out[name] = {"cagr": round(rb.cagr(r), 4), "sharpe": round(rb.sharpe(r, rf[1:]), 3),
                     "maxdd": round(rb.max_dd(r), 4)}
    out["period"] = [d[0], d[-1]]
    return out


def replicated(tab):
    y, t, m = tab["yearly"], tab["traditional_Q"], tab["monthly"]
    a = (y["cagr"] - t["cagr"] >= 0.025) and (y["sharpe"] > t["sharpe"])
    b = y["cagr"] > m["cagr"]
    return {"a_size_and_sharpe": a, "b_yearly_beats_monthly": b, "replicated": a and b}


if __name__ == "__main__":
    res = rb.evaluate(
        IDEA, weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=4, family="btc-sleeve-rebal",
        fetch=fetch,
        notes="REPLICATION of Bitwise 2020 rebalancing table: 58.5% VT / 39% BND / 2.5% BTC rebalanced "
              "yearly (first US trading day of January) vs 60/40 VT/BND quarterly (synthetic "
              "BENCH-VTBND6040Q@2020Q1); window 2014-09-17 -> 2020-03-31 (source 2014-01-01; Yahoo BTC "
              "starts 2014-09-17); 25bp all legs; replication criterion = yearly CAGR >= trad + 2.5%/yr "
              "and higher Sharpe, and yearly CAGR > monthly CAGR; harness verdict for the record only")
    tab = table()
    print(json.dumps({"evaluate": res, "frequency_table": tab, "replication": replicated(tab)},
                     indent=1))
