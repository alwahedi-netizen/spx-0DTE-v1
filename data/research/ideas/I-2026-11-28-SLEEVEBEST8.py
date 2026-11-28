"""I-2026-11-28-SLEEVEBEST8 — sourced-idea VARIANT: our paper lane BTC10
(54% VT / 36% BND / 10% BTC, monthly) with the BTC slot in T-bills from June
through September ("Best Eight Months" for Bitcoin). Benchmark = BTC10 itself
(static, monthly — the paper lane in alloc_lab.py), per KNOWLEDGE themes
22/26: a crypto-sleeve rule must beat the static sleeve.

Source: Zdunczyk & Hirsch, "The Seasonality of Cryptocurrencies", Stock
Trader's Almanac 2023-09,
https://stocktradersalmanac.com/UploadedDocument/Seasonality%20_of_Cryptocurrency_Report.pdf
(Bitstamp 2011-2023: September the only negative month, -6.45% average;
Best Eight Months October-May, Worst Four June-September). Ledger row
I-2026-11-11-BTCBEST8 (queued by the crypto desk 2026-11-11, carried in the
round-3 queue). Replicated first in R-2026-11-28-BTCSEASON; this script
REFUSES to run its test unless that replication held.
Varies I-2026-11-14-SLEEVEANNUAL / I-2026-11-07-BTCSLEEVE (static control)
and R-2026-11-07-BEST6M (the equity version: safer, not better).

Hypothesis (written before any run): a recurring summer lull in crypto
demand (northern-hemisphere holiday season, low retail flows, the US equity
"sell in May" pattern BTC has tracked since ~2020) makes June-September BTC
returns lower than T-bills on average, so parking the 10% slot in T-bills for
those four months raises BTC10's Sharpe. Counter-hypothesis (stated up front,
and our prior): it is a 10-observation calendar pattern found by looking at
the same years we test (the source sample 2011-2023 covers our whole
development window 2014-09 -> 2024-10 except summer 2024); arithmetic
monthly means hide positive compounded summers (2016, 2017, 2020, 2021); and
BTC10's rebalancing already harvests some of any seasonality. The only
genuinely out-of-sample summers (2025, 2026) sit in the research vault, so a
harness PASS here is a ticket to the vault, never a result on its own.

RULE (fixed before any run):
  * Universe VT, BND, BTC-USD. In season (October-May) the target is BTC10's
    54/36/10; out of season (June-September) it is 54% VT / 36% BND / 10%
    T-bills (BTC 0; the cash earns the harness T-bill rate).
  * Rebalance to the month's target at the close of the FIRST US trading day
    (VT date) of every month — exactly BTC10's own schedule — so the seasonal
    switches happen at the close of the first US trading day of June (BTC
    out) and of October (BTC back in); drift in between; the first bar
    invests at the target of its month. The 1-3 day offset vs the source's
    calendar months is tested by the "exact_cal" variant.
  * Benchmark: BTC10 (54/36/10 on the first US trading day of every month),
    same 25bp, synthetic pseudo-ticker BENCH-BTC10M (same construction as
    I-2026-11-14-SLEEVEANNUAL's).
  * Variants (bench unchanged; each one neighbouring setting of the season):
      exact_cal — the BTC leg alone switches on BTC's 7-day calendar at the
                  close of the bar dated the last calendar day of May (out)
                  and of September (in), i.e. the source's exact months;
                  VT/BND keep the monthly US-day schedule;
      best6     — Best Six: BTC out May-October (switch on the first US
                  trading day of May / November);
      sep_only  — BTC out in September only (the source's single negative
                  month);
      midsep    — BTC back in at the close of the first US trading day on or
                  after September 15 ("buy in mid-late September").
DATA TIMING: calendar rule — no price is read for the signal. The target for
the bar dated i depends only on the date of bar i (its month, whether it is a
US trading day, and for exact_cal whether it is the last calendar day of the
month — known from the calendar, no price). Drift uses closes through bar i
(the holdings the trade at close i starts from). Weights decided at close i
earn i -> i+1. 7-day calendar (BTC); VT/BND are flat on weekends/holidays.
Costs 25bp per unit turnover on every leg. Period 2014-09-17 -> vault
(sealed from 2024-11-01; summers 2015-2024 in development).
PASS CRITERION (pre-registered): the harness verdict vs BENCH-BTC10M (PASS =
99% confidence + held-out win + full-period Sharpe >= bench + 0.10 + DSR >=
0.95 + t >= 3 + 2x costs + >= 70% of the 4 variants beat the bench).
PROMISING (>= 90% + held-out win) earns a shortlist note only. Also report
(information, not a gate) worst drop vs BTC10's and the replication's
summer-2024 figure. A harness PASS goes to the lead's red team and then the
one vault test (summers 2025-26 are the only unseen evidence).
trials: family btc-calendar holds 5 (BTCTOM) + 5 here = 10. No factor gate
(FF blind to BTC, red team 11-10).
"""
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "I-2026-11-28-SLEEVEBEST8"
REPL = "R-2026-11-28-BTCSEASON"
EQ, BD, BTC = "VT", "BND", "BTC-USD"
SYMS = [EQ, BD, BTC]
IN_SEASON = {EQ: 0.54, BD: 0.36, BTC: 0.10}
OUT_SEASON = {EQ: 0.54, BD: 0.36}          # 10% T-bills
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


def _month_out(out_months):
    return lambda d: int(d[5:7]) in out_months


def make(out_months=(6, 7, 8, 9), midsep=False, exact_cal=False):
    """out_months: calendar months whose US-day reset targets OUT_SEASON.
    midsep: in September, switch back in on the first US day >= the 15th.
    exact_cal: the BTC leg switches on BTC's calendar at the close of the
    bar dated May 31 (out) / September 30 (in); VT/BND reset on US days."""
    st = {}
    outm = set(out_months)

    def target(d):
        return dict(OUT_SEASON) if int(d[5:7]) in outm else dict(IN_SEASON)

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                         # evaluate() re-runs simulate: reset state
            st.clear()
            st["m"] = d[:7]
            st["btc_on"] = int(d[5:7]) not in outm
            st["sep_in"] = False
            st["w"] = target(d)
            return dict(st["w"])
        st["w"] = drift(st["w"], i, px)
        if exact_cal:
            nxt = date.fromisoformat(d) + timedelta(days=1)
            if nxt.day == 1 and nxt.month in (6, 10):     # bar dated May 31 / Sep 30
                on = nxt.month == 10
                if on != st["btc_on"]:
                    st["btc_on"] = on
                    w = {s: x for s, x in st["w"].items() if s != BTC}
                    if on:
                        w[BTC] = IN_SEASON[BTC]           # buy 10% of NAV from cash
                    st["w"] = w
            if d in us_days() and d[:7] != st["m"]:
                st["m"] = d[:7]
                w = {EQ: IN_SEASON[EQ], BD: IN_SEASON[BD]}
                if st["btc_on"]:
                    w[BTC] = IN_SEASON[BTC]
                st["w"] = w
            return dict(st["w"])
        if d in us_days():
            if d[:7] != st["m"]:
                st["m"] = d[:7]            # first US trading day of the month
                st["sep_in"] = False
                if midsep and int(d[5:7]) == 9:
                    st["w"] = dict(OUT_SEASON)
                else:
                    st["w"] = target(d)
            elif midsep and int(d[5:7]) == 9 and not st["sep_in"] and int(d[8:10]) >= 15:
                st["sep_in"] = True        # first US trading day on/after Sep 15
                st["w"] = dict(IN_SEASON)
        return dict(st["w"])
    return weights


weights = make((6, 7, 8, 9))

VARIANTS = {
    "exact_cal": make((6, 7, 8, 9), exact_cal=True),
    "best6": make((5, 6, 7, 8, 9, 10)),
    "sep_only": make((9,)),
    "midsep": make((6, 7, 8, 9), midsep=True),
}


def bench_series():
    d, p = rb.prices(SYMS, START)
    rets, _ = rb.simulate(make(()), d, p, [0.0] * len(d), COST)   # no out months = BTC10
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else rb._fetch(sym)


def replication_ok():
    """League rule 1: test the variant only if the source's headline held."""
    p = Path(__file__).resolve().parent / f"{REPL}.py"
    spec = importlib.util.spec_from_file_location("btcseason", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = mod.replicated()
    return rep["replicated"], rep


if __name__ == "__main__":
    ok, why = replication_ok()
    if not ok:
        print(json.dumps({"idea": IDEA, "skipped": True, "tests": 0,
                          "reason": "replication of the source failed", "detail": why},
                         indent=1))
        sys.exit(0)
    print(json.dumps(rb.evaluate(
        IDEA, weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=10, family="btc-calendar",
        variants=VARIANTS, fetch=fetch,
        notes="variant of Zdunczyk & Hirsch 2023 (replicated in R-2026-11-28-BTCSEASON): BTC10 (54% VT / "
              "36% BND / 10% BTC, first US trading day monthly) with the BTC slot in T-bills June-September "
              "vs BTC10 static monthly (synthetic BENCH-BTC10M = the paper lane); 25bp all legs; variants "
              "exact_cal (BTC-calendar switch May 31 / Sep 30), best6 (out May-Oct), sep_only, midsep (back "
              "in on the first US day >= Sep 15); calendar rule, no price read; no FF gate; trials 10 "
              "family btc-calendar; source sample covers the dev window except summer 2024; vault sealed "
              "from 2024-11 (summers 2025-26 unseen)"),
        indent=1))
