"""L-2026-11-11-SLEEVEVOL — original (RESEARCH.md §2b): the 10% Bitcoin
sleeve in a 60/40, re-sized every month by BTC's volatility relative to its
own recent norm (a risk budget, not a trend switch). Benchmark = the STATIC
10% sleeve (KNOWLEDGE theme 22), not the bare 60/40.

Ingredients:
  * I-2026-11-07-BTCSLEEVE / red team of L-2026-11-10-SLEEVETREND: a static
    10% BTC sleeve in VBINX did as well as the trend-gated one (15.3%/yr,
    Sharpe 1.02 vs VBINX 0.61); "sizing BTC is the real question".
  * Moreira & Muir, JF 2017 https://doi.org/10.1111/jofi.12513 (variance
    timing) — the same lever as I-2026-11-10-BTCVMP, here inside a sleeve.
  * R-2026-10-28-VTSPYL (shortlist 5: vol-managed S&P) and
    L-2026-11-07-BTCTRENDVOL (vol sizing cut BTC's worst drop -83% -> -46%).
Varies L-2026-11-10-SLEEVETREND: replaces the on/off trend gate (which the
red team showed costs the rebounds) with a continuous vol budget whose
AVERAGE size is ~10% by construction (sized relative to the median), so the
comparison with the static 10% sleeve isolates timing of size, not "more BTC".

Rationale (written before any run): BTC's sleeve losses are concentrated in
high-vol stretches (2018, Mar 2020, May 2021, 2022), and BTC's vol is
persistent month to month; holding a constant RISK budget instead of a
constant weight trims the sleeve into those stretches and adds to it in calm
up-trends (2016, 2019 H1, 2023), without ever leaving BTC (the static sleeve's
strength: it never misses the rebound). Counter-hypothesis: Baur-Dimpfl's
inverted asymmetry — BTC's vol rises after UP moves — so vol sizing trims
exactly the blow-off rallies (2017, 2020 Q4) that made the static sleeve's
return; Cederburg et al. 2020: vol management mostly fails out of sample.

RULE (fixed before any run):
  * Universe VBINX (Vanguard Balanced Index, 60/40) and BTC-USD.
  * At the close of the FIRST US trading day (VBINX date) of each month:
    sigma = sd of BTC daily returns over the 90 calendar days ending the day
    before (bars dated < today) x sqrt(365); append it to the history of
    monthly readings; ref = median of the last 36 readings (incl. this one).
    Sleeve s = clip(0.10 x ref / sigma, 0.025, 0.20); weights VBINX 1 - s,
    BTC s; drift in between. Fewer than 12 readings: s = 0.10 (= benchmark).
  * Benchmark = static 90% VBINX + 10% BTC, rebalanced on the same first US
    trading day each month, same 25bp — the red team's control, built inside
    this script as a synthetic series (pseudo-ticker BENCH-VBINX90BTC10M)
    because evaluate() needs a ticker.
DATA TIMING: sigma uses only BTC bars dated before the decision day; trades
at the decision day's close (VBINX 4pm NAV; BTC bar 00:00 UTC next day).
Calendar: 7-day union, VBINX carried flat over weekends (harness fix 11-09).
Costs 25bp per unit turnover on every leg.
Variants (bench unchanged): cap 15%; 60- and 180-day vol window; 24-month ref.
trials: 5 here + BTCVMP's 5 (same vol-timing hypothesis on BTC, run today)
+ btc-trend-vol's 6 = 16; family btc-sleeve-vol. No factor gate (FF is blind
to BTC beta — red team 11-10; the static-sleeve bench is the control).
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

CORE, BTC = "VBINX", "BTC-USD"
SYMS = [CORE, BTC]
START = "2014-09-17"
COST = 25.0
BENCH = "BENCH-VBINX90BTC10M"
_CAL = {}


def us_days():
    """Real VBINX pricing dates (a public calendar)."""
    if CORE not in _CAL:
        d, _ = rb.prices([CORE], "1990-01-01")
        _CAL[CORE] = set(d)
    return _CAL[CORE]


def set_us_days(ds):                     # smoke tests inject a calendar
    _CAL[CORE] = set(ds)


def _sd(x):
    m = sum(x) / len(x)
    return (sum((v - m) ** 2 for v in x) / (len(x) - 1)) ** 0.5


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


def btc_vol(i, dates, px, window):
    j = i - 1                             # bars dated strictly before today
    if j < 1:
        return None
    lo = (date.fromisoformat(dates[j]) - timedelta(days=window)).isoformat()
    if dates[0] > lo:
        return None
    p = [px[BTC][k] for k in range(j, -1, -1) if dates[k] >= lo][::-1]
    if None in p or len(p) < 0.85 * window:
        return None
    return _sd([b / a - 1 for a, b in zip(p, p[1:])]) * 365 ** 0.5


def make(base=0.10, lo=0.025, hi=0.20, window=90, n_ref=36, static=False):
    st = {}

    def target(s):
        return {CORE: 1 - s, BTC: s}

    def weights(i, dates, px):
        d = dates[i]
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["sig"], st["month"] = target(base), [], d[:7]
            return dict(st["w"])
        st["w"] = drift(st["w"], i, px)
        if d in us_days() and d[:7] != st["month"]:
            st["month"] = d[:7]           # first US trading day of the month
            s = base
            if not static:
                v = btc_vol(i, dates, px, window)
                if v:
                    st["sig"].append(v)
                    ref = st["sig"][-n_ref:]
                    if len(ref) >= 12:
                        s = min(hi, max(lo, base * _median(ref) / v))
            st["w"] = target(s)
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "cap15": make(hi=0.15),
    "win60": make(window=60),
    "win180": make(window=180),
    "ref24": make(n_ref=24),
}


def bench_series(fn=None, syms=SYMS, start=START, cost=COST, prices=None):
    """Synthetic price index of the static 10% sleeve (monthly rebalance)."""
    prices = prices or rb.prices
    d, p = prices(syms, start)
    rets, _ = rb.simulate(fn or make(static=True), d, p, [0.0] * len(d), cost)
    idx = [100.0]
    for r in rets:
        idx.append(idx[-1] * (1 + r))
    return dict(zip(d, idx))


def fetch(sym):
    return bench_series() if sym == BENCH else rb._fetch(sym)


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-11-SLEEVEVOL", weights, SYMS, bench=BENCH, start=START,
        asset_class="crypto", cost_bps=COST, trials=16, family="btc-sleeve-vol",
        variants=VARIANTS, fetch=fetch,
        notes="lab original: VBINX + BTC sleeve s = clip(10% x median(36 monthly 90-day BTC vols)/current, "
              "2.5%, 20%), first US trading day monthly, BTC bars dated before today; BENCH = static 10% "
              "sleeve, same monthly rebalance (synthetic BENCH-VBINX90BTC10M, theme 22); 25bp all legs; "
              "variants cap 15%, 60/180-day vol, 24-month ref; no FF gate (blind to BTC); "
              "vault sealed from 2024-11"),
        indent=1))
