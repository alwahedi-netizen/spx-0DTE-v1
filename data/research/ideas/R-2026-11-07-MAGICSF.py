"""R-2026-11-07-MAGICSF — RETEST of I-2026-11-07-GREENBLATT (the "magic
formula") on survivorship-free, point-in-time data.

Source: Greenblatt (2006) "The Little Book That Beats the Market"; academic
replication Gray & Carlisle (2012) "Quantitative Value". Ledger row
I-2026-11-07-GREENBLATT was rejected only for lack of point-in-time data.
Why it should work: buying good businesses (high return on capital) at low
prices (high earnings yield) — quality and value together.

Rule (fixed before the first run):
  on the last trading day of each month, take the S&P 500 members on that
  day excluding Financial Services and Utilities (Greenblatt's exclusions;
  sector from Sharadar's ticker table); earnings yield = EBIT/EV (1 / DAILY
  `evebit` on that date, evebit > 0 only); return on capital = the latest
  trailing-twelve-month `roic` (fundamentals ART) whose `date` (the day it
  became public) is on or before the rebalance date; rank each, add the two
  ranks, hold the best 30 equal-weight to the next month end.
Benchmark SPY (Yahoo), 5bp/turnover, 2000-01 → vault.
Variants: best 20, best 50, best 40, and quarterly rebalance with 30.
"""
import bisect
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ROWS = rb.sp500_history(first_year=1999)
TICKERS = sorted({r["ticker"] for r in ROWS})
def _ticker_table():
    # rb.sharadar() cannot pass a `table=` filter (name clash) — page it directly
    out, off = [], 0
    while True:
        rows = rb._sh_fetch("tickers", {"table": "stocks", "limit": 10000, "offset": off})
        out += rows
        if len(rows) < 10000:
            return out
        off += 10000


SECTOR = {r["ticker"]: r.get("sector") for r in _ticker_table()}
EXCLUDE = {"Financial Services", "Utilities"}
_MEM, _EY, _ROIC = {}, {}, {}


def members(day):
    if day not in _MEM:
        _MEM[day] = rb.sp500_members(day, ROWS)
    return _MEM[day]


def earnings_yield(day):
    if day not in _EY:
        _EY[day] = {r["ticker"]: 1.0 / r["evebit"] for r in rb.sharadar("daily", None, date=day)
                    if r.get("evebit") is not None and r["evebit"] > 0}
    return _EY[day]


def roic_asof(t, day):
    if t not in _ROIC:
        # Sharadar's `date` = the day the figures became public (point-in-time key)
        rows = sorted((r["date"][:10], r["roic"]) for r in rb.sharadar("fundamentals", None, ticker=t,
                      dimension="ART") if r.get("date") and r.get("roic") is not None)
        _ROIC[t] = ([d for d, _ in rows], [v for _, v in rows])
    ds, vs = _ROIC[t]
    j = bisect.bisect_right(ds, day) - 1
    return vs[j] if j >= 0 else None


def make(n_hold=30, months=1):
    state = {"w": {}, "k": 0}

    def weights(i, dates, px):
        if i == 0:                                  # fresh state for every simulation
            state.update(w={}, k=0)
        if i + 1 < len(dates) and dates[i + 1][:7] == dates[i][:7]:
            return state["w"]
        state["k"] += 1
        if (state["k"] - 1) % months:
            return state["w"]
        ey = earnings_yield(dates[i])
        cand = []
        for t in members(dates[i]):
            if SECTOR.get(t) in EXCLUDE or t not in ey or px.get(t) is None or not px[t][i]:
                continue
            r = roic_asof(t, dates[i])
            if r is not None:
                cand.append((t, ey[t], r))
        by_ey = {t: k for k, (t, _, _) in enumerate(sorted(cand, key=lambda x: -x[1]))}
        by_rc = {t: k for k, (t, _, _) in enumerate(sorted(cand, key=lambda x: -x[2]))}
        best = sorted(by_ey, key=lambda t: by_ey[t] + by_rc[t])[:n_hold]
        state["w"] = {t: 1.0 / len(best) for t in best} if best else {}
        return state["w"]
    return weights


if __name__ == "__main__":
    import json
    out = rb.evaluate("R-2026-11-07-MAGICSF", make(), TICKERS, "SPY", start="2000-01-01",
                      asset_class="stocks", source="sharadar", family="GREENBLATT",
                      variants={"best20": make(20), "best40": make(40), "best50": make(50),
                                "quarterly30": make(30, 3)},
                      notes="Retest of GREENBLATT: EBIT/EV + point-in-time ROIC ranks, best 30 of the "
                            "point-in-time S&P 500 ex financials/utilities, monthly; Sharadar")
    print(json.dumps({k: out[k] for k in out if k not in ("equity",)}, indent=1)[:6000])
