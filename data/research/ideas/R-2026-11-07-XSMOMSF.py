"""R-2026-11-07-XSMOMSF — RETEST of G-MOM on survivorship-free data.

Source: Jegadeesh & Titman (1993) "Returns to Buying Winners and Selling
Losers", J. Finance 48(1); the lab's G-MOM row (graveyard: "false pass from
survivorship bias"). KNOWLEDGE.md "Data unlocked — retest first" #1.
Why it should work: investors under-react to firm news, so 12-month winners
keep winning for months (the best-documented equity anomaly).
Why retest: G-MOM failed because its universe was today's survivors. This run
uses Sharadar (delisted names included) and the POINT-IN-TIME S&P 500.

Rule (fixed before the first run; classic form, not G-MOM's stop/add/trail):
  on the last trading day of each month, take the S&P 500 members on that
  day; rank by 12-1 momentum = close[t-21] / close[t-252] - 1 (skip the last
  month); hold the top decile equal-weight until the next month end.
Benchmark SPY (Yahoo, dividends), 5bp/turnover, 2000-01 → vault.
Variants (robustness, counted in trials): 9-1 and 15-1 lookbacks, top 5%
and top 20%.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ROWS = rb.sp500_history(first_year=1999)
TICKERS = sorted({r["ticker"] for r in ROWS})
_MEM = {}


def members(day):
    if day not in _MEM:
        _MEM[day] = rb.sp500_members(day, ROWS)
    return _MEM[day]


def make(look=252, frac=0.10):
    state = {"w": {}}

    def weights(i, dates, px):
        if i == 0:                                  # fresh state for every simulation
            state.update(w={}, k=0)
        if i + 1 < len(dates) and dates[i + 1][:7] == dates[i][:7]:
            return state["w"]                       # hold between month ends
        if i < look:
            return {}
        scores = []
        for t in members(dates[i]):
            s = px.get(t)
            if s is None:
                continue
            a, b = s[i - look], s[i - 21]
            if a and b and s[i]:
                scores.append((b / a - 1, t))
        scores.sort(reverse=True)
        n = max(1, int(len(scores) * frac))
        top = [t for _, t in scores[:n]]
        state["w"] = {t: 1.0 / len(top) for t in top} if top else {}
        return state["w"]
    return weights


if __name__ == "__main__":
    import json
    out = rb.evaluate("R-2026-11-07-XSMOMSF", make(), TICKERS, "SPY", start="2000-01-01",
                      asset_class="stocks", source="sharadar", family="XSMOM",
                      variants={"9-1": make(189), "15-1": make(315),
                                "top5%": make(frac=0.05), "top20%": make(frac=0.20)},
                      notes="Retest of G-MOM: 12-1 top decile of the point-in-time S&P 500, "
                            "monthly, equal weight; Sharadar survivorship-free")
    print(json.dumps({k: out[k] for k in out if k not in ("equity",)}, indent=1)[:6000])
