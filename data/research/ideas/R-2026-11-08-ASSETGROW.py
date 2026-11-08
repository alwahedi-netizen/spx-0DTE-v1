"""R-2026-11-08-ASSETGROW — the asset-growth anomaly, long-only, on the
point-in-time S&P 500 (survivorship-free).

Promoted from the queue row I-2026-11-07-ASSETGROW (scored 68 on 2026-11-07,
over that day's 5-script cap). Same mechanism, first test — not a new idea.
Source: Cooper, Gulen & Schill (2008) "Asset Growth and the Cross-Section of
Stock Returns", J. Finance 63(4) 1609-1651
(https://econpapers.repec.org/RePEc:bla:jfinan:v:63:y:2008:i:4:p:1609-1651).

RATIONALE (fixed before any run): firms that grow total assets fast (debt- or
equity-financed expansion, acquisitions) earn LOWER subsequent returns; the
market extrapolates past growth and over-pays for empire building, then is
disappointed. Cooper-Gulen-Schill find the effect in large caps too (weaker),
which is our S&P 500 setting. Known risk: it is close to the Fama-French CMA
(investment) factor, so the factor-alpha gate may call it a known factor.
Also: an SMU working paper attributes much of the published effect to missing
CRSP delisting returns — our Sharadar universe includes delisted names.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the decision day
    (rb.sp500_members on rb.sp500_history), Sharadar survivorship-free prices.
  * Decision day: the last close of June each year (CGS timing).
  * Signal: asset growth AG = assets(latest ARY row with public `date` <=
    decision day, calendardate within 18 months) / assets(the ARY row before
    it, whose calendardate is 9-15 months earlier) - 1.
  * Hold the LOWEST 20% by AG, value-weighted by the latest row's `marketcap`,
    until next June; weights drift with prices between rebalances.
  * Before the first June with data: hold SPY (warm-up, equals benchmark).
  * Variants (robustness gate): lowest 10%, 15%, 25%, 30%.
  * Benchmark SPY, 5bp/side (stocks), strict bar + FF5+Mom alpha gate.
  * family "asset-growth" (new family): trials = 1 + 4 = 5.
Delisted names: a held stock that delists returns 0 from its last price (the
harness has no delisting return) — noted.
"""
import bisect
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-08-ASSETGROW"
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


def growth_row(ticker, day, max_age_m=18):
    """(asset growth, marketcap) from the two latest public ARY rows, or None."""
    ds, rows = fund(ticker)
    k = bisect.bisect_right(ds, day) - 1          # only rows public on/before day
    if k < 1:
        return None
    r = rows[k]
    cd = (r.get("calendardate") or r["date"])[:10]
    if _months_between(cd, day) > max_age_m:
        return None
    prev = None
    for j in range(k - 1, -1, -1):                # the prior fiscal-year row
        cdj = (rows[j].get("calendardate") or rows[j]["date"])[:10]
        gap = _months_between(cdj, cd)
        if 9 <= gap <= 15:
            prev = rows[j]
            break
        if gap > 15:
            break
    if prev is None:
        return None
    a1, a0, mc = _num(r.get("assets")), _num(prev.get("assets")), _num(r.get("marketcap"))
    if not a1 or not a0 or a0 <= 0 or a1 <= 0 or not mc or mc <= 0:
        return None
    return a1 / a0 - 1, mc


def make_weights(frac=0.20):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()                             # fresh state for every simulation
        rebalance = (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
                     and dates[i][5:7] == "06")
        if rebalance:
            day = dates[i]
            scored = []
            for t in members(day):
                if t not in px or px[t][i] is None:
                    continue
                g = growth_row(t, day)
                if g:
                    scored.append((g[0], g[1], t))
            if len(scored) >= 20:
                scored.sort()                      # lowest asset growth first
                pick = scored[:max(1, int(round(len(scored) * frac)))]
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
VARIANTS = {f"low{int(q * 100)}": make_weights(q) for q in (0.10, 0.15, 0.25, 0.30)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, all_tickers(), BENCH, start=START, asset_class="stocks", trials=5,
        family="asset-growth", variants=VARIANTS, source="sharadar",
        notes=("Cooper-Gulen-Schill asset growth: lowest 20% of point-in-time S&P 500 by "
               "annual total-asset growth (Sharadar ARY, public date <= decision day), "
               "value-weighted, rebalanced each June; SPY warm-up; variants low 10/15/25/30%; "
               "survivorship-free; promoted from I-2026-11-07-ASSETGROW"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
