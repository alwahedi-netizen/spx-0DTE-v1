"""R-2026-11-07-VALMOMSF — RETEST of I-2026-10-28-TRENDVAL (value x momentum)
on survivorship-free, point-in-time data.

Source: Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere",
J. Finance 68(3); the ledger row I-2026-10-28-TRENDVAL was rejected only
because single-stock data was survivorship-biased (KNOWLEDGE.md retest list).
Why it should work: value and momentum are each rewarded and NEGATIVELY
correlated with each other, so a stock cheap AND rising combines two
independent premia with a smoother ride than either.

Rule (fixed before the first run):
  on the last trading day of each month, take the S&P 500 members on that
  day; value = EBIT/EV (1 / Sharadar DAILY `evebit` on that date, which uses
  the fundamentals public by then; names with evebit <= 0 excluded);
  momentum = close[t-21]/close[t-252] - 1; score = average of the two
  percentile ranks; hold the top decile equal-weight to the next month end.
Benchmark SPY (Yahoo), 5bp/turnover, 2000-01 → vault.
Variants: top 5% / top 20%, value-weighted 2:1, momentum-weighted 2:1.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ROWS = rb.sp500_history(first_year=1999)
TICKERS = sorted({r["ticker"] for r in ROWS})
_MEM, _EY = {}, {}


def members(day):
    if day not in _MEM:
        _MEM[day] = rb.sp500_members(day, ROWS)
    return _MEM[day]


def earnings_yield(day):
    if day not in _EY:
        ey = {}
        for r in rb.sharadar("daily", None, date=day):
            v = r.get("evebit")
            if v is not None and v > 0:
                ey[r["ticker"]] = 1.0 / v
        _EY[day] = ey
    return _EY[day]


def pct_rank(d):
    keys = sorted(d, key=d.get)
    n = len(keys)
    return {k: (j + 1) / n for j, k in enumerate(keys)} if n else {}


def make(frac=0.10, wv=1.0, wm=1.0):
    state = {"w": {}}

    def weights(i, dates, px):
        if i == 0:                                  # fresh state for every simulation
            state.update(w={}, k=0)
        if i + 1 < len(dates) and dates[i + 1][:7] == dates[i][:7]:
            return state["w"]
        if i < 252:
            return {}
        ey = earnings_yield(dates[i])
        mom, val = {}, {}
        for t in members(dates[i]):
            s = px.get(t)
            if s is None or t not in ey:
                continue
            a, b = s[i - 252], s[i - 21]
            if a and b and s[i]:
                mom[t], val[t] = b / a - 1, ey[t]
        rm, rv = pct_rank(mom), pct_rank(val)
        score = sorted(((wv * rv[t] + wm * rm[t], t) for t in mom), reverse=True)
        n = max(1, int(len(score) * frac))
        top = [t for _, t in score[:n]]
        state["w"] = {t: 1.0 / len(top) for t in top} if top else {}
        return state["w"]
    return weights


if __name__ == "__main__":
    import json
    out = rb.evaluate("R-2026-11-07-VALMOMSF", make(), TICKERS, "SPY", start="2000-01-01",
                      asset_class="stocks", source="sharadar", family="TRENDVAL",
                      variants={"top5%": make(0.05), "top20%": make(0.20),
                                "value2:1": make(wv=2.0), "mom2:1": make(wm=2.0)},
                      notes="Retest of TRENDVAL: EBIT/EV x 12-1 momentum rank, top decile of the "
                            "point-in-time S&P 500, monthly; Sharadar survivorship-free")
    print(json.dumps({k: out[k] for k in out if k not in ("equity",)}, indent=1)[:6000])
