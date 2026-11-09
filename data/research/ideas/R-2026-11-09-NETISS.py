"""R-2026-11-09-NETISS — net share issuance (Pontiff-Woodgate), long-only, on
the point-in-time S&P 500 (survivorship-free).

Promoted from the queue row I-2026-11-08-NETISS (scored 76 on 2026-11-08,
held back by that night's 5-script cap). Same mechanism, first test.
Source: Pontiff & Woodgate (2008) "Share Issuance and Cross-sectional
Returns", J. Finance 63(2) 921-945
(https://econpapers.repec.org/RePEc:bla:jfinan:v:63:y:2008:i:2:p:921-945);
also Fama-French (2008) "Dissecting Anomalies" (net issues is one of the
anomalies that survives in big stocks). Independent point-in-time large-cap
check: Quanter Lab 2026-08-19 "Paid in fewer shares" — top-30 low-issuance
S&P 500 book 10.6%/yr vs RSP 9.5% (2006-25), led 9 of 15 windows before
2021 and none after: EXPECT a weak recent half.

RATIONALE (fixed before any run): managers issue shares when their stock is
over-valued and buy back when it is cheap (market timing), and the market
under-reacts to both signals. Firms that shrink their share count earn more
afterwards; heavy issuers earn less. Known risk: overlaps the FF5 investment
(CMA) factor and ASSETGROW (both are external-financing signals), so the
factor-alpha gate may call it a known factor (theme 8).

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the decision day
    (rb.sp500_members on rb.sp500_history), Sharadar survivorship-free prices;
    only names with a price on the decision day.
  * Decision day: the last close of June each year.
  * Signal: NS = ln(sharesbas of the latest ARY row whose public `date` <=
    decision day and calendardate <= 18 months old / sharesbas of the prior
    fiscal-year ARY row, calendardate 9-15 months earlier).
  * Hold the LOWEST 20% by NS (biggest net repurchasers), value-weighted by
    the latest row's `marketcap`, until next June; weights drift with prices.
  * Before the first June decision: hold SPY (warm-up, equals benchmark).
  * Variants (robustness gate): lowest 10%, 15%, 25%, 30%.
  * Benchmark SPY, 5bp/side (stocks), 2000-01 -> vault, strict bar + FF5+Mom
    alpha gate. family "net-issuance" (new): trials = 1 + 4 = 5.
CHANGE vs the I- row, made BEFORE any run (data check, not a result): the
I- row planned to split-adjust `sharesbas` with SEP closeunadj/close. Sharadar
already restates `sharesbas` for later splits (checked on the cached ARY rows:
AAPL 2014 7:1 and 2020 4:1, NVDA, GOOGL/AMZN 2022 20:1, TSLA 2020/2022 show no
jumps), so a second adjustment would double-count. NS uses `sharesbas` as is.
Delisted names: a held stock that delists returns 0 from its last price (the
harness has no delisting return) — noted.
Data sharing: uses the same Sharadar queries as R-2026-11-08-ASSETGROW
(fundamentals ARY per ticker, prices per ticker), so runs on the same UTC day
share the cache.
"""
import importlib.util
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("assetgrow", Path(__file__).with_name("R-2026-11-08-ASSETGROW.py"))
ag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ag)

ID = "R-2026-11-09-NETISS"
START = "2000-01-01"
BENCH = "SPY"


def two_rows(ticker, day, max_age_m=18):
    """(latest ARY row public on/before day, the prior fiscal-year row) or None."""
    import bisect
    ds, rows = ag.fund(ticker)
    k = bisect.bisect_right(ds, day) - 1
    if k < 1:
        return None
    r = rows[k]
    cd = (r.get("calendardate") or r["date"])[:10]
    if ag._months_between(cd, day) > max_age_m:
        return None
    for j in range(k - 1, -1, -1):
        cdj = (rows[j].get("calendardate") or rows[j]["date"])[:10]
        gap = ag._months_between(cdj, cd)
        if 9 <= gap <= 15:
            return r, rows[j]
        if gap > 15:
            return None
    return None


def make_annual(select, month="06"):
    """Weights fn: rebalance to select(day, i, px) at the last close of `month`,
    drift with prices in between, SPY before the first book."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()                             # fresh state for every simulation
        if (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
                and dates[i][5:7] == month):
            w = select(dates[i], i, px)
            if w:
                st["w"] = w
                st["base"] = {t: px[t][i] for t in w}
                st["last"] = dict(st["base"])
                return dict(w)
        if "w" not in st:
            return {BENCH: 1.0}
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t]
        tot = sum(v.values())
        return {t: x / tot for t, x in v.items()} if tot > 0 else {}
    return weights


def issuance(t, day):
    pair = two_rows(t, day)
    if not pair:
        return None
    r, prev = pair
    s1, s0, mc = ag._num(r.get("sharesbas")), ag._num(prev.get("sharesbas")), ag._num(r.get("marketcap"))
    if not s1 or not s0 or s1 <= 0 or s0 <= 0 or not mc or mc <= 0:
        return None
    return math.log(s1 / s0), mc


def make_weights(frac=0.20):
    def select(day, i, px):
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None:    # only names priced on the decision day
                continue
            x = issuance(t, day)
            if x:
                scored.append((x[0], x[1], t))
        if len(scored) < 20:
            return None
        scored.sort()                              # most negative issuance first
        pick = scored[:max(1, int(round(len(scored) * frac)))]
        tot = sum(mc for _, mc, _ in pick)
        return {t: mc / tot for _, mc, t in pick}
    return make_annual(select)


weights = make_weights(0.20)
VARIANTS = {f"low{int(q * 100)}": make_weights(q) for q in (0.10, 0.15, 0.25, 0.30)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="net-issuance", variants=VARIANTS, source="sharadar",
        notes=("Pontiff-Woodgate net issuance: lowest 20% of point-in-time S&P 500 by ln(sharesbas "
               "latest ARY / prior-year ARY) (Sharadar, public date <= decision day; sharesbas already "
               "split-restated), value-weighted, rebalanced each June; SPY warm-up; variants low "
               "10/15/25/30%; survivorship-free; promoted from I-2026-11-08-NETISS"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
