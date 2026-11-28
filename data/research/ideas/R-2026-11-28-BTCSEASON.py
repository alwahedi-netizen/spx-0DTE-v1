"""R-2026-11-28-BTCSEASON — REPLICATION (no evaluate() call, 0 tests) of the
Stock Trader's Almanac Bitcoin seasonality study. It gates
I-2026-11-28-SLEEVEBEST8 (league rule 1: replicate first).

Source: A. Zdunczyk CMT & J. A. Hirsch, "The Seasonality of Cryptocurrencies:
Analysis of Recurring Price Trends in Bitcoin", Stock Trader's Almanac,
2023-09, https://stocktradersalmanac.com/UploadedDocument/Seasonality%20_of_Cryptocurrency_Report.pdf
(ledger row I-2026-11-11-BTCBEST8). Source data: Bitstamp BTC/USD monthly,
2011 -> 2023 (written in late September 2023).
Source headline (page 3-4, read from the PDF 2026-11-28):
  * "September is the only negative month (-6.45% average loss) over the
    last 13 years"; September is "the worst performer of all months";
  * "The Best Eight Months from October through May and Worst Four Months
    from June through September stand out on all the historical pattern
    lines" (no table of Best-8 vs Worst-4 returns is published);
  * October averages "over 10%", up "67% of the time since 2011".

OUR DATA: Yahoo BTC-USD (an exchange composite, not Bitstamp), first bar
2014-09-17, so the overlap with the source is 2014-10 -> 2023-09 (9
Septembers, 2015-2023; the source's own 2023 September was still partial).
Month return = last close of month m / last close of month m-1 - 1 on BTC's
7-day calendar (the bar dated D closes at 00:00 UTC D+1, so the bar dated the
last calendar day closes the calendar month).

REPLICATED (pre-registered, "sign and rough size", KNOWLEDGE theme 33) iff ALL
of, on 2014-10 -> 2023-09:
  (a) September's mean monthly return is negative and of rough size:
      between -12.90% (2x the source) and -2.00%;
  (b) September has the LOWEST mean of the 12 calendar months;
  (c) the mean monthly return of Oct-May months exceeds the mean of Jun-Sep
      months (Best Eight vs Worst Four, arithmetic, the source's chart basis).
Printed for information only (never a gate): the 12 monthly means and up
shares; whether September is the ONLY negative month; October's mean and up
share (source >10%, 67%); compounded Jun-Sep and Oct-May returns per season
(geometric, the basis a holding rule actually earns); summer 2024
(2024-06 -> 2024-09), the only out-of-source summer before the research
vault (2024-11); the same table on the whole development window 2014-10 ->
2024-10.
DATA TIMING: descriptive statistics of completed calendar months only; no
trading rule, no evaluate() call, no trial added.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb
from datetime import datetime, timezone

IDEA = "R-2026-11-28-BTCSEASON"
BTC = "BTC-USD"
SRC = {"sep_mean": -0.0645, "oct_mean_min": 0.10, "oct_up_share": 0.67,
       "period": "Bitstamp 2011-2023"}
GATE = ("2014-10", "2023-09")
BEST8 = {10, 11, 12, 1, 2, 3, 4, 5}
WORST4 = {6, 7, 8, 9}


def monthly():
    """[(yyyy-mm, return)] from month-end closes of BTC-USD."""
    d, p = rb.prices([BTC], "2014-09-17")
    last = {}
    for day, v in zip(d, p[BTC]):
        if v:
            last[day[:7]] = v                 # last close seen in that month
    ms = sorted(last)
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    out = []
    for k in range(1, len(ms)):
        if ms[k] >= today:                    # drop the incomplete current month
            break
        out.append((ms[k], last[ms[k]] / last[ms[k - 1]] - 1))
    return out


def _mean(x):
    return sum(x) / len(x) if x else None


def table(first, last):
    rows = [(m, r) for m, r in monthly() if first <= m <= last]
    by = {k: [r for m, r in rows if int(m[5:7]) == k] for k in range(1, 13)}
    means = {k: _mean(v) for k, v in by.items()}
    best = [r for m, r in rows if int(m[5:7]) in BEST8]
    worst = [r for m, r in rows if int(m[5:7]) in WORST4]
    seasons = {}
    for m, r in rows:                         # compounded per season
        y, mo = int(m[:4]), int(m[5:7])
        if mo in WORST4:
            key = f"{y} Jun-Sep"
        else:
            key = f"{y if mo >= 10 else y - 1}/{(y + 1 if mo >= 10 else y) % 100:02d} Oct-May"
        seasons[key] = seasons.get(key, 1.0) * (1 + r)
    return {
        "period": [first, last], "months": len(rows),
        "mean_by_month": {k: round(v, 4) for k, v in means.items() if v is not None},
        "up_share_by_month": {k: round(sum(1 for r in v if r > 0) / len(v), 2)
                              for k, v in by.items() if v},
        "n_by_month": {k: len(v) for k, v in by.items()},
        "best8_mean": round(_mean(best), 4), "worst4_mean": round(_mean(worst), 4),
        "season_compounded": {k: round(v - 1, 4) for k, v in seasons.items()},
        "_means": means, "_best": _mean(best), "_worst": _mean(worst),
    }


def replicated(t=None):
    t = t or table(*GATE)
    m = t["_means"]
    sep = m[9]
    a = sep is not None and -0.129 <= sep <= -0.02
    b = sep is not None and all(sep <= v for k, v in m.items() if v is not None)
    c = t["_best"] > t["_worst"]
    return {"sep_mean": round(sep, 4), "a_sep_negative_rough_size": a,
            "b_sep_lowest_month": b, "c_best8_beats_worst4": c,
            "replicated": bool(a and b and c)}


def _public(t):
    return {k: v for k, v in t.items() if not k.startswith("_")}


if __name__ == "__main__":
    g = table(*GATE)
    rep = replicated(g)
    neg = [k for k, v in g["_means"].items() if v is not None and v < 0]
    s24 = [r for mo, r in monthly() if "2024-06" <= mo <= "2024-09"]
    c24 = 1.0
    for r in s24:
        c24 *= 1 + r
    print(json.dumps({
        "idea": IDEA, "tests": 0, "source": SRC,
        "replication": rep,
        "info": {"negative_months": neg, "sep_only_negative": neg == [9],
                 "oct_mean": round(g["_means"][10], 4),
                 "oct_up_share": g["up_share_by_month"].get(10),
                 "summer_2024_btc_compounded": round(c24 - 1, 4) if len(s24) == 4 else None},
        "source_overlap": _public(g),
        "dev_window_2014_10_2024_10": _public(table("2014-10", "2024-10")),
    }, indent=1))
