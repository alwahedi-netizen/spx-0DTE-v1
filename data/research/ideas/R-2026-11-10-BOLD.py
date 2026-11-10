"""R-2026-11-10-BOLD — Vinter ByteTree BOLD1: bitcoin and gold held together,
weighted by inverse 360-day volatility, rebalanced on the last business day
of each month. A BTC sleeve whose crash protection comes from a permanent
gold partner instead of a timing signal.

Sources (rule fixed from these, before any run):
  Index methodology (Vinter / ByteTree, v1.1 of 2021-03-01):
    https://cdn.21shares.com/uploads/current-documents/21SharesVinter%20ByteTree%20BOLD%20Indexes.pdf
    "The weight in bitcoin is proportional to its inverse volatility:
     (1/sB) / (1/sB + 1/sG), sB, sG = 360 days volatility"; "Rebalanced:
     monthly on the last business day of the month"; "data up to five
     business days prior to the rebalancing date is used".
  Live product: 21Shares ByteTree BOLD ETP (SIX, 2022). Monthly reports:
    https://bytetree.com/research/2023/08/bytetree-bold-index (weights
    24.5% BTC / 75.5% gold at 2023-07-31; 5-year +130% vs BTC +280%,
    gold +60%). Provider claim: worst drop 16% over 2014-11 -> 2021-11.
No independent peer-reviewed test (evidence = a live index + issuer reports).

Varies: I-2026-11-07-GLDBTCDM (gold vs Bitcoin DUAL MOMENTUM — a switch;
never tested) and I-2026-11-07-BTCSLEEVE (static BTC sleeve in 60/40;
rejected 11-07 for the calendar defect fixed 2026-11-09). Here both assets
are ALWAYS held; only the mix moves, by relative risk. Theme 16: every
crypto TIMING rule cut crashes but lost to BTC; this tests the other route —
diversification + a rebalancing return between two volatile, nearly
uncorrelated stores of value (BTC-gold daily correlation ~0.1).

Rationale (written before any run): (1) equal risk budgets keep BTC's
upside while gold carries the book through BTC's bears (2018, 2022 — gold
roughly flat); (2) monthly rebalancing between two assets with low
correlation and very different volatility harvests a rebalancing premium
(sells BTC after rallies, buys after crashes) — a plausible return source,
not a timing call. Expected: far lower return than BTC (~25-35% BTC
weight), Sharpe at or above BTC's, worst drop a fraction of BTC's, low
correlation to equities. Judge it as a portfolio sleeve (portfolio.marginal),
not on beating BTC's CAGR. Counter-hypothesis: the 360-day vol lags, so the
weight is highest right after calm bull years (late 2021: BTC weight up just
before -77%), and gold's 2013-15 and 2022 weakness gives no offset.

RULE (fixed before any run; index defaults):
  * Business day = a day GLD trades (US exchange calendar; the index uses
    SIX days — stated difference). Rebalance at the close of the LAST
    business day of each calendar month.
  * Volatility: as of the business day 5 business days before the rebalance
    day (index rule), sB = st.dev. of BTC-USD daily returns over the
    previous 360 calendar days x sqrt(365); sG = st.dev. of GLD returns
    between consecutive business days in the same 360 days x sqrt(252).
    Weight BTC = (1/sB) / (1/sB + 1/sG); GLD = 1 - weight BTC. Fully
    invested, no cash.
  * Between rebalances the quantities are fixed (weights drift).
  * Warm-up (before 360 days of both histories, data start 2014-09-17):
    hold 100% BTC = the benchmark (neutral: no free crash avoidance).
  * Prices: BTC-USD 00:00 UTC close, GLD US close (index: Vinter BTC rate
    and LBMA PM gold at 3 pm London — stated difference). GLD's 0.40% fee
    is inside its price (the index has none).
Benchmark = buy & hold BTC-USD (lead's crypto rule); the result must ALSO be
read against GLD and for its correlation to SPY. 25bp per unit turnover on
both legs (asset_class crypto; GLD really costs ~2bp — conservative).
Variants (neighbours of the one parameter + schedule): vol window 180 /
540 / 720 days; quarterly rebalance (Mar/Jun/Sep/Dec).
trials: 1 + 4 = 5; new family btc-gold-mix (GLDBTCDM was never run).
Tradeable at Schwab as IBIT + GLD (or IAU) from 2024-01; before that the
BTC leg is spot (GBTC carried a premium/discount). Calendar: harness fix
2026-11-09 carries GLD's price over weekends, so GLD earns 0 on BTC-only
dates and the full Friday->Monday move on Monday (no lost weekend)."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BTC, GOLD = "BTC-USD", "GLD"
LAG_BDAYS = 5
_DAYS = {}


def bdays():
    """Real GLD trading dates (the exchange calendar is public in advance)."""
    if GOLD not in _DAYS:
        d, _ = rb.prices([GOLD], "1990-01-01")
        _DAYS[GOLD] = set(d)
    return _DAYS[GOLD]


def set_bdays(ds):                       # smoke tests inject a calendar
    _DAYS[GOLD] = set(ds)


def _sd(x):
    m = sum(x) / len(x)
    return (sum((v - m) ** 2 for v in x) / (len(x) - 1)) ** 0.5


def is_rebalance(i, dates, quarterly=False):
    d = dates[i]
    bd = bdays()
    if d not in bd:
        return False
    if quarterly and int(d[5:7]) % 3:
        return False
    for k in range(i + 1, len(dates)):    # dates are a public calendar, not prices
        if dates[k][:7] != d[:7]:
            break
        if dates[k] in bd:
            return False
    if i + 1 >= len(dates):               # last row of the sample: next month unknown here
        nxt = date.fromisoformat(d) + timedelta(days=1)
        while nxt.isoformat()[:7] == d[:7]:
            if nxt.isoformat() in bd:
                return False
            nxt += timedelta(days=1)
    return True


def btc_weight(i, dates, px, window=360):
    """Inverse-vol BTC weight as of LAG_BDAYS business days before index i."""
    bd = bdays()
    j, seen = i, 0
    while j > 0 and seen < LAG_BDAYS:
        j -= 1
        if dates[j] in bd:
            seen += 1
    if seen < LAG_BDAYS:
        return None
    lo = (date.fromisoformat(dates[j]) - timedelta(days=window)).isoformat()
    if dates[0] > lo:                     # not enough history yet
        return None
    k0 = j                                # window = dates in [lo, dates[j]]
    while k0 > 0 and dates[k0 - 1] >= lo:
        k0 -= 1
    b = [px[BTC][k] for k in range(k0, j + 1)]
    g = [px[GOLD][k] for k in range(k0, j + 1) if dates[k] in bd]
    if None in b or None in g or len(b) < 0.9 * window or len(g) < 0.6 * window:
        return None
    rb_ = [y / x - 1 for x, y in zip(b, b[1:])]
    rg_ = [y / x - 1 for x, y in zip(g, g[1:])]
    sb, sg = _sd(rb_) * 365 ** 0.5, _sd(rg_) * 252 ** 0.5
    if sb <= 0 or sg <= 0:
        return None
    return (1 / sb) / (1 / sb + 1 / sg)


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(window=360, quarterly=False):
    st = {}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"] = {BTC: 1.0}          # warm-up = benchmark (neutral)
        else:
            st["w"] = drift(st["w"], i, px)
        if is_rebalance(i, dates, quarterly):
            wb = btc_weight(i, dates, px, window)
            if wb is not None:
                st["w"] = {BTC: wb, GOLD: 1 - wb}
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "vol180": make(window=180),
    "vol540": make(window=540),
    "vol720": make(window=720),
    "quarterly": make(quarterly=True),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-10-BOLD", weights, [BTC, GOLD], bench=BTC, start="2014-09-17",
        asset_class="crypto", trials=5, family="btc-gold-mix", variants=VARIANTS,
        notes="Vinter ByteTree BOLD1: BTC/GLD inverse 360-day vol, last US business day of each month, "
              "vol measured 5 business days before, quantities fixed between rebalances; warm-up holds "
              "BTC (neutral); 25bp both legs; bench BTC-USD (also read vs GLD and corr to SPY); "
              "vault sealed from 2024-11"),
        indent=1))
