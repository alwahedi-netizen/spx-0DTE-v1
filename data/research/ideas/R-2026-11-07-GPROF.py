"""R-2026-11-07-GPROF — gross-profitability premium (Novy-Marx 2013, JFE 108(1)
1-28, "The Other Side of Value: The Gross Profitability Premium";
https://www.nber.org/papers/w15940). Canon mining: the first quality-factor test
in the ledger, made possible by the Sharadar point-in-time fundamentals
connected 2026-11-07. Not a variant of any ledger row (I-2026-11-07-GREENBLATT
is quality x VALUE; this is profitability alone).

RATIONALE (fixed before any run): firms with high gross profits relative to
assets earn higher future returns even though they look expensive; the market
under-prices durable productive capacity (gross profit is the cleanest,
least-manipulated profitability line). Novy-Marx finds the effect strongest in
large, liquid stocks and value-weighted — exactly an S&P 500 setting.

RULE (fixed before any run; trials honest = 1 + 4 variants):
  * Universe: point-in-time S&P 500 members on the decision day
    (rb.sp500_members on rb.sp500_history), Sharadar survivorship-free prices.
  * Decision day: the last close of June each year (Novy-Marx's timing).
  * Signal: GP/A = gp / assets from the latest Sharadar ARY (annual, as
    reported) row whose public `date` <= decision day and whose
    `calendardate` is within 18 months of it (stale rows ignored).
  * Hold the top 20% by GP/A, value-weighted by that row's `marketcap`
    (Novy-Marx's headline portfolios are value-weighted), until next June;
    weights drift with prices between rebalances.
  * Before the first June with data: hold SPY (warm-up, equals benchmark).
  * Deviation: Novy-Marx drops financials; our connector has no sector field.
    Banks/insurers have GP/A ~0.01-0.05, so they cannot reach a long-only top
    quintile anyway.
  * Variants (robustness gate): top 10%, 15%, 25%, 30%.
  * Benchmark SPY, 5bp/side (stocks), strict bar + FF5+Mom alpha gate.
Delisted names: a held stock that delists returns 0 from its last price (the
harness has no delisting return) — slightly conservative or not, noted.
"""
import bisect
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-07-GPROF"
START = "1997-01-01"
BENCH = "SPY"
_H = {"rows": None, "mem": {}}
_F = {}          # ticker -> (sorted public dates, rows)


def hist():
    if _H["rows"] is None:
        _H["rows"] = rb.sp500_history()
    return _H["rows"]


def members(asof):
    if asof not in _H["mem"]:
        _H["mem"][asof] = rb.sp500_members(asof, hist())
    return _H["mem"][asof]


def all_tickers(start=START):
    rows = hist()
    t = set(members(start))
    t |= {r["ticker"] for r in rows if r["date"][:10] >= start}
    return sorted(t)


def fund(ticker):
    if ticker not in _F:
        try:
            rows = [r for r in rb.fundamentals_pit(ticker, "ARY") if r.get("date")]
        except Exception:  # noqa: BLE001 — a missing ticker is just no data
            rows = []
        _F[ticker] = ([r["date"][:10] for r in rows], rows)
    return _F[ticker]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _months_between(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def latest_row(ticker, day, max_age_m=18):
    ds, rows = fund(ticker)
    k = bisect.bisect_right(ds, day) - 1
    if k < 0:
        return None
    r = rows[k]
    cd = r.get("calendardate") or r["date"]
    return r if _months_between(cd[:10], day) <= max_age_m else None


def make_weights(top=0.20):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        rebalance = (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
                     and dates[i][5:7] == "06")
        if rebalance:
            day = dates[i]
            scored = []
            for t in members(day):
                if t not in px or px[t][i] is None:
                    continue
                r = latest_row(t, day)
                if not r:
                    continue
                gp, a, mc = _num(r.get("gp")), _num(r.get("assets")), _num(r.get("marketcap"))
                if gp is None or not a or a <= 0 or not mc or mc <= 0:
                    continue
                scored.append((gp / a, mc, t))
            if len(scored) >= 20:
                scored.sort(reverse=True)
                pick = scored[:max(1, int(round(len(scored) * top)))]
                tot = sum(mc for _, mc, _ in pick)
                st["w"] = {t: mc / tot for _, mc, t in pick}
                st["base"] = {t: px[t][i] for t in st["w"]}
                st["last"] = dict(st["base"])
                return dict(st["w"])
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


weights = make_weights(0.20)
VARIANTS = {f"top{int(q * 100)}": make_weights(q) for q in (0.10, 0.15, 0.25, 0.30)}


if __name__ == "__main__":
    import json
    syms = all_tickers()
    print(json.dumps(rb.evaluate(
        ID, weights, syms, BENCH, start=START, asset_class="stocks", trials=5,
        family="gross-profitability", variants=VARIANTS, source="sharadar",
        notes=("Novy-Marx GP/A: top 20% of point-in-time S&P 500 by gross profits/assets "
               "(Sharadar ARY, public date <= decision day), value-weighted, rebalanced each "
               "June; SPY warm-up; variants top 10/15/25/30%; survivorship-free")), indent=1))
