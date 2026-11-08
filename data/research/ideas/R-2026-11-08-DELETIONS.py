"""R-2026-11-08-DELETIONS — buy the S&P 500's discretionary deletions and hold
them for five years ("Nixed": the upside of getting dumped).

Source: Research Affiliates (Arnott et al.), webinar 2024-10-24 reported in
Financial Planning, "Trash or treasure? Dumped index stocks could be
investing opportunity"
(https://www.financial-planning.com/news/trash-or-treasure-dumped-index-stocks-could-be-investing-opportunity):
S&P 500 additions and discretionary deletions Oct 1989 - Jun 2021; in the 12
months after the trade date deletions beat additions by >22%, and deletions
beat the market by ~28% (cumulative) over the following five years; the
Research Affiliates Deletions ETF (NIXT) holds deleted names ~5 years or until
they re-enter a benchmark. Caveats: the firm sells a product on it; its 2024
commentary says deletions have NOT beaten the S&P 500 over the last decade.
New mechanism for the ledger (index-flow overshoot / contrarian discards);
not a variant of any row. Nearest cousins: long-term reversal / value.

RATIONALE (fixed before any run): index funds must sell a deleted stock on
the trade date regardless of price, after a year in which it already lagged
badly; the forced selling and the "loser" label push it below fair value,
and it mean-reverts over years as the selling pressure ends. Sharadar's
membership table (with delisted prices) lets us test it without
survivorship bias — the deleted names that later went bankrupt are in.

RULE (fixed before any run):
  * Events: every `removed` row of Sharadar's S&P 500 table. A deletion is
    DISCRETIONARY unless its note (public on the removal date) matches
    acquired | merg | spin | spun | share class | tracking stock | non-U.S. |
    reorganiz | redomesticat | reincorporat | incorporation | split |
    exchange the shares | ticker changed | listed on New York. Distress
    deletions (bankruptcy, delisting, FDIC seizure, float) are KEPT.
  * At each month's last close D: hold, equal-weight, every discretionary
    deletion whose removal date is in (D - 60 months, D], that has a price on
    D (still trading) and is not an S&P 500 member on D (re-added -> sold).
    Weights drift between month ends.
  * No eligible names (warm-up): hold SPY.
  * Cost 10bp/side (deleted names are mid/small caps; RESEARCH.md §4 sets
    >= 10bp for small caps).
  * Variants (robustness gate): holding window 30, 45, 75, 90 months.
  * Benchmark SPY, 1998-01 -> vault, strict bar + FF5+Mom alpha gate.
  * family "sp500-deletions" (new): trials = 1 + 4 = 5.
Delisted names: a held stock that delists returns 0 from its last price
until the next month end (no delisting return in the harness) — noted.
"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-08-DELETIONS"
BENCH = "SPY"
START = "1998-01-01"
NOT_DISCRETIONARY = re.compile(
    r"acquired|merg|spin|spun|share class|tracking stock|non-U\.S\.|reorganiz|redomesticat|"
    r"reincorporat|incorporation|split|exchange the shares|ticker changed|listed on New York",
    re.I)
_U = {"rows": None, "mem": {}, "events": None}


def hist():
    if _U["rows"] is None:
        _U["rows"] = rb.sp500_history(first_year=1990)
    return _U["rows"]


def members(day):
    if day not in _U["mem"]:
        _U["mem"][day] = rb.sp500_members(day, hist())
    return _U["mem"][day]


def events():
    """[(removal date, ticker)] of discretionary deletions, sorted."""
    if _U["events"] is None:
        seen = set()
        for r in hist():
            if r.get("action") != "removed" or NOT_DISCRETIONARY.search(r.get("note") or ""):
                continue
            seen.add((r["date"][:10], r["ticker"]))
        _U["events"] = sorted(seen)
    return _U["events"]


def _months_back(day, m):
    y, mo = int(day[:4]), int(day[5:7]) - m
    while mo <= 0:
        mo += 12
        y -= 1
    return f"{y:04d}-{mo:02d}{day[7:10]}"


def make(hold_m=60):
    st = {}

    def weights(i, dates, px):
        if i == 0:                                    # fresh state for every simulation
            st.clear()
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            day = dates[i]
            lo = _months_back(day, hold_m)
            mem = members(day)
            pick = sorted({t for d, t in events() if lo < d <= day
                           and t not in mem and t in px and px[t][i] is not None})
            if pick:
                st["w"] = {t: 1.0 / len(pick) for t in pick}
                st["base"] = {t: px[t][i] for t in pick}
                st["last"] = dict(st["base"])
                return dict(st["w"])
            st.pop("w", None)
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


weights = make(60)
VARIANTS = {f"hold{m}m": make(m) for m in (30, 45, 75, 90)}


if __name__ == "__main__":
    import json
    tickers = sorted({t for _, t in events()})
    out = rb.evaluate(ID, weights, tickers, BENCH, start=START, cost_bps=10.0,
                      asset_class="stocks", source="sharadar", family="sp500-deletions",
                      trials=5, variants=VARIANTS,
                      notes=("S&P 500 discretionary deletions (non-M&A/spin/share-class notes), "
                             "equal weight, held 60 months after removal or until re-added, "
                             "monthly; SPY when none; 10bp; variants 30/45/75/90 months; "
                             "Sharadar survivorship-free"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
