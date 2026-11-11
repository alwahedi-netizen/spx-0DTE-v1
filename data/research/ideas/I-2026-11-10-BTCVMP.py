"""I-2026-11-10-BTCVMP — volatility-managed Bitcoin (Moreira & Muir 2017,
canon applied to BTC).

Source: https://doi.org/10.1111/jofi.12513 (Moreira & Muir, "Volatility-
Managed Portfolios", JF 2017). Counter-evidence: Cederburg, O'Doherty, Wang
& Yan, JFE 2020 https://doi.org/10.1016/j.jfineco.2020.04.015 (most vol-
managed strategies fail out of sample); Baur & Dimpfl, Economics Letters
2018 (crypto vol rises MORE after positive shocks — variance scaling may cut
rallies). Ledger row 2026-11-10, queued "next crypto script".

Rationale (written before any run): realised variance is persistent, but
expected return does not rise one-for-one with it, so exposure scaled by
1/variance earns a better return per unit of risk (Moreira-Muir). For BTC
the crash months (2018, Mar 2020, 2022 LUNA/FTX) start with variance spikes.
This isolates the SIZE leg of L-2026-11-07-BTCTRENDVOL (trend x vol: Sharpe
1.38 vs 1.12 corrected, worst drop -46%): is BTCTRENDVOL's crash cut coming
from vol or from trend? Counter-hypothesis: BTC's rallies are high-variance
too (2017, 2020 Q4, Baur-Dimpfl's inverted asymmetry), so the rule cuts the
best months and loses to buy-and-hold on Sharpe.

RULE (fixed before any run; the ledger's 2026-11-10 rule):
  * At the close of each month-end BTC bar (last calendar day, 00:00 UTC
    next day): RV_m = mean of squared daily BTC simple returns inside that
    calendar month (per-day variance, so 28- and 31-day months compare).
    w = min(1, median(last 36 RV readings incl. this one) / RV_m); the rest
    in T-bills. Fewer than 36 readings: w = 1 (warm-up = the benchmark).
  * BTC quantity fixed between decisions (weight drifts with price).
  * A month-end bar missing from the data: decide on the first bar of the
    next month instead (catch-up, uses only bars up to that bar).
DATA TIMING: the decision on bar i reads only bars <= i (the month just
closed); weights decided at bar i's close earn bar i -> i+1 (harness).
Benchmark BTC-USD buy & hold (RESEARCH.md §4). 25bp per unit turnover.
Variants: 24- and 60-month median; vol (not variance) scaling; weekly
(every Sunday close: RV over the last 30 bars vs the median of the last 156
weekly readings).
trials: 5 here + btc-trend-vol's 6 (BTCTRENDVOL, whose vol leg this
separates) = 11; family btc-vol-managed.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BTC = "BTC-USD"
START = "2014-09-17"


def _last_day(d):
    x = date.fromisoformat(d)
    return (x + timedelta(days=1)).month != x.month


def _median(x):
    s = sorted(x)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(n_ref=36, power=1.0, weekly=False, win=30):
    st = {}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["rv"], st["sq"], st["m"] = {BTC: 1.0}, [], [], None
            return dict(st["w"])
        st["w"] = drift(st["w"], i, px)
        a, b = px[BTC][i - 1], px[BTC][i]
        r2 = (b / a - 1) ** 2 if (a and b) else None
        d = dates[i]
        decide = False
        if weekly:
            if r2 is not None:
                st["sq"].append(r2)
            if date.fromisoformat(d).weekday() == 6 and len(st["sq"]) >= win:
                st["rv"].append(sum(st["sq"][-win:]) / win)
                decide = True
        else:
            if d[:7] != dates[i - 1][:7] and st["m"] != dates[i - 1][:7] and st["sq"]:
                # catch-up: last month had no month-end bar; close it now
                st["rv"].append(sum(st["sq"]) / len(st["sq"]))
                st["m"], st["sq"] = dates[i - 1][:7], []
                decide = True
            if d[:7] != dates[i - 1][:7]:
                st["sq"] = []             # a new month's returns start here
            if r2 is not None:
                st["sq"].append(r2)
            if _last_day(d):
                st["rv"].append(sum(st["sq"]) / len(st["sq"]))
                st["m"], st["sq"] = d[:7], []
                decide = True
        if decide:
            ref = st["rv"][-n_ref:]
            if len(ref) == n_ref and ref[-1] > 0:
                w = min(1.0, (_median(ref) / ref[-1]) ** power)
            else:
                w = 1.0                   # warm-up = the benchmark
            st["w"] = {BTC: w}
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "ref24": make(n_ref=24),
    "ref60": make(n_ref=60),
    "vol_scaling": make(power=0.5),
    "weekly": make(n_ref=156, weekly=True),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "I-2026-11-10-BTCVMP", weights, [BTC], bench=BTC, start=START,
        asset_class="crypto", cost_bps=25.0, trials=11, family="btc-vol-managed",
        variants=VARIANTS,
        notes="Moreira-Muir on BTC: month-end w = min(1, median of last 36 monthly realised variances / "
              "this month's), rest T-bills, quantity fixed between; warm-up w=1 (= bench); bench BTC-USD; "
              "25bp; variants 24/60-month median, vol scaling, weekly; isolates BTCTRENDVOL's vol leg; "
              "vault sealed from 2024-11"),
        indent=1))
