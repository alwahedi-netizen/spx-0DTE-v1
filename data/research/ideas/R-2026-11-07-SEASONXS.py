"""R-2026-11-07-SEASONXS — cross-sectional return seasonality (Heston & Sadka
2008, JFE 87(2) 418-445, "Seasonality in the Cross-Section of Stock Returns";
https://econpapers.repec.org/RePEc:eee:jfinec:v:87:y:2008:i:2:p:418-445;
international replication Heston-Sadka 2010 JFQA; Keloharju-Linnainmaa-Nyberg
2016 JF "Return Seasonalities"). Canon mining; survivorship-free via Sharadar.

Not a variant of any ledger row: BEST6M / TOY / TOM are MARKET calendar
effects; this ranks STOCKS against each other by their own same-calendar-month
history (each stock has its own seasonal, e.g. retailers, dividend months).

RATIONALE (fixed before any run): a stock's return in a given calendar month
predicts its return in the same month in later years, for up to 20 annual
lags, independent of size, industry, earnings months and dividends. Keloharju
et al. attribute it to recurring, seasonal variation in risk premia /
investor flows that is not arbitraged because it requires a long memory.

RULE (fixed before any run; trials honest = 1 + 4 variants):
  * Universe: point-in-time S&P 500 members on the decision day.
  * Decision: last close of each month (month m-1) for the coming month m.
  * Score: average of the stock's return in calendar month m over each of the
    past K = 5 years (month-end to month-end closes; all K years required).
    K=5 is our fixed choice inside HS's documented range (lags 1-20 years all
    positive; HS group lags 2-5, 6-10...): the data start (1997) leaves a
    usable sample.
  * Hold the top decile, equal-weight, for one month (drifting), then re-rank.
  * Warm-up until K years of month-ends exist: hold SPY.
  * Variants: K = 3, 4, 6, 7.
  * Benchmark SPY, 5bp/side (turnover ~ full book each month: ~1.2%/yr cost,
    exactly what the double-cost gate probes), FF5+Mom alpha gate.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-07-SEASONXS"
START = "1997-01-01"
BENCH = "SPY"
_H = {"rows": None, "mem": {}}


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


def _prev_key(y, m):
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def make_weights(k_years=5, top=0.10):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["me"] = {}
        st["me"][dates[i][:7]] = i            # last index seen in each month so far
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            nxt = dates[i + 1]
            Y, m = int(nxt[:4]), int(nxt[5:7])
            keys = [(f"{Y - y}-{m:02d}", _prev_key(Y - y, m)) for y in range(1, k_years + 1)]
            me = st["me"]
            if all(a in me and b in me for a, b in keys):
                score = {}
                for t in members(dates[i]):
                    if t not in px or px[t][i] is None:
                        continue
                    rs = []
                    for a, b in keys:
                        pa, pb = px[t][me[a]], px[t][me[b]]
                        if not pa or not pb:
                            break
                        rs.append(pa / pb - 1)
                    if len(rs) == k_years:
                        score[t] = sum(rs) / k_years
                if len(score) >= 50:
                    pick = sorted(score, key=lambda t: -score[t])[:max(1, int(round(len(score) * top)))]
                    st["w"] = {t: 1.0 / len(pick) for t in pick}
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


weights = make_weights(5)
VARIANTS = {f"k{k}": make_weights(k) for k in (3, 4, 6, 7)}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate(
        ID, weights, all_tickers(), BENCH, start=START, asset_class="stocks", trials=5,
        family="xs-seasonality", variants=VARIANTS, source="sharadar",
        notes=("Heston-Sadka same-calendar-month seasonality on point-in-time S&P 500: top decile "
               "by avg return in the coming calendar month over the past 5 years, equal-weight, "
               "monthly; SPY warm-up; variants K=3/4/6/7; survivorship-free")), indent=1))
