"""R-2026-11-07-CONSERV — the Conservative Formula (Van Vliet & Blitz 2018,
JPM, "The Conservative Formula: Quantitative Investing Made Easy", SSRN 3145152;
rules as summarised by CXO Advisory:
https://www.cxoadvisory.com/size-effect/simple-volatility-payout-momentum-stock-strategy
— and Robeco's 20-year live record, 2026-10-28:
https://www.robeco.com/en-int/insights/2026/10/what-20-years-of-defensive-equities-can-teach-investors).

VARIES G-STK-SUITE (LOWVOL, LVMOM: low volatility alone / with momentum on
Yahoo prices, failed the bar). Why the difference matters: (1) the net payout
yield leg is new — a shareholder-yield tilt that pure low-vol lacks and that
the authors credit for avoiding expensive "bond-proxy" low-vol stocks; (2) the
test is survivorship-free (Sharadar), the suite was not.

RATIONALE (fixed before any run): low-volatility stocks are under-priced
because leverage-constrained and benchmark-relative investors chase high-beta
names (Frazzini-Pedersen, Baker-Bradley-Wurgler); within them, momentum and
net payout (dividends + buybacks) add cheapness/under-reaction. The
combination is defensive equity with a return engine, not crash insurance.

RULE (fixed before any run; trials honest = 1 + 4 variants):
  * Universe: point-in-time S&P 500 members (paper: 1,000 largest US stocks;
    we scale N in proportion: top 100 of 1,000 -> top 50 of 500).
  * Decision: last close of March, June, September, December (quarterly).
  * Vol: stdev of the last 36 monthly returns (month-end closes, needs all 37
    month-ends). Keep the lower-volatility half of names with data.
  * Momentum: 12-1 = close at month-end t-1 / close at month-end t-12 - 1.
  * Net payout yield: (-ncfdiv - ncfcommon) / marketcap from the latest
    Sharadar ART (trailing 12 months) row with public `date` <= decision day
    and calendardate within 15 months. (Paper: dividend yield minus change in
    shares; cash-flow form avoids split artefacts in share counts. Deviation
    noted.) Names without it are dropped.
  * Within the low-vol half rank momentum and NPY (1 = best), average the two
    ranks, equal-weight the best 50; weights drift until the next quarter.
  * Warm-up before 37 month-ends exist: hold SPY.
  * Variants: N=40, N=60, vol window 24m, vol window 48m.
  * Benchmark SPY, 5bp/side, strict bar + FF5+Mom alpha gate (a low-vol +
    momentum portfolio may well be explained by RMW/CMA/UMD — that is the test).
"""
import bisect
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-07-CONSERV"
START = "1997-01-01"
BENCH = "SPY"
_H = {"rows": None, "mem": {}}
_F = {}


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
            rows = [r for r in rb.fundamentals_pit(ticker, "ART") if r.get("date")]
        except Exception:  # noqa: BLE001
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


def npy(ticker, day):
    ds, rows = fund(ticker)
    k = bisect.bisect_right(ds, day) - 1
    if k < 0:
        return None
    r = rows[k]
    if _months_between((r.get("calendardate") or r["date"])[:10], day) > 15:
        return None
    dv, cm, mc = _num(r.get("ncfdiv")), _num(r.get("ncfcommon")), _num(r.get("marketcap"))
    if dv is None or cm is None or not mc or mc <= 0:
        return None
    return (-dv - cm) / mc


def _ranks(vals):
    """{t: rank} with 1 = highest value."""
    order = sorted(vals, key=lambda t: -vals[t])
    return {t: k + 1 for k, t in enumerate(order)}


def make_weights(n_hold=50, vol_m=36):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["me"] = []
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            st["me"].append(i)
        me = st["me"]
        need = max(vol_m, 12) + 1
        if month_end and dates[i][5:7] in ("03", "06", "09", "12") and len(me) >= need:
            day = dates[i]
            vol, mom, pay = {}, {}, {}
            for t in members(day):
                if t not in px:
                    continue
                c = [px[t][k] for k in me[-(vol_m + 1):]]
                if None in c or min(c) <= 0:
                    continue
                r = [c[k] / c[k - 1] - 1 for k in range(1, len(c))]
                m = sum(r) / len(r)
                vol[t] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
                mom[t] = c[-2] / c[-13] - 1
            if len(vol) >= 40:
                low = sorted(vol, key=vol.get)[:len(vol) // 2]
                for t in low:
                    y = npy(t, day)
                    if y is not None:
                        pay[t] = y
                cand = list(pay)
                if len(cand) >= n_hold:
                    rm = _ranks({t: mom[t] for t in cand})
                    rp = _ranks(pay)
                    score = sorted(cand, key=lambda t: (rm[t] + rp[t]) / 2)
                    pick = score[:n_hold]
                    st["w"] = {t: 1.0 / n_hold for t in pick}
                    st["base"] = {t: px[t][i] for t in pick}
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


weights = make_weights(50, 36)
VARIANTS = {"n40": make_weights(40, 36), "n60": make_weights(60, 36),
            "vol24": make_weights(50, 24), "vol48": make_weights(50, 48)}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate(
        ID, weights, all_tickers(), BENCH, start=START, asset_class="stocks", trials=5,
        family="conservative-formula", variants=VARIANTS, source="sharadar",
        notes=("Van Vliet-Blitz Conservative Formula on point-in-time S&P 500: low 36m-vol half, "
               "avg rank of 12-1 momentum and TTM net payout yield (Sharadar ART, public date <= "
               "decision), equal-weight best 50, quarterly; SPY warm-up; variants N40/N60/vol24/vol48; "
               "survivorship-free")), indent=1))
