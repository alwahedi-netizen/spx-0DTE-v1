"""L-2026-11-11-RNDEAP — lab original: hold the R&D-intensity book's names
ONLY in the months they are expected to report earnings; T-bills otherwise.
A cash-hedged (not short-hedged) R&D sleeve with roughly a third of the
equity exposure (KNOWLEDGE.md theme 18: add to the book without equity beta;
theme 21: no short legs while simulate() charges T-bills on shorts).

INGREDIENTS:
  * R-2026-11-10-RND (potential 3, alpha t 2.7): the book whose mispricing
    we want to harvest — top 20% of point-in-time S&P 500 R&D firms by RD/ME.
  * Earnings-announcement premium: Frazzini & Lamont (2007) "The Earnings
    Announcement Premium and Trading Volume", NBER w13090
    (https://www.nber.org/papers/w13090): "On the last trading day of month
    t-1, buy every stock expected to announce earnings in month t ... Hold
    this portfolio until the last day of month t"; last year's announcement
    month predicts this year's (80%; 93% with 4 announcements last year);
    premium "particularly among large cap securities". Replicated
    internationally by Barber, De George, Lehavy & Trueman (2013) JFE 108(1)
    118-138.
  * Mispricing corrects at announcements: La Porta, Lakonishok, Shleifer &
    Vishny (1997) "Good News for Value Stocks", J. Finance 52(2) 859-874 —
    a large share of the value-glamour return spread is earned in the few
    days around earnings announcements.
RATIONALE (fixed before any run): if RND's premium is a correction of the
market's neglect of R&D (CLS 2001), the correction should arrive when the
firm reports — that is when the payoff from past research shows up in sales
and margins (LSV 1997's mechanism for value). Announcement months also
carry the systematic announcement premium. So holding the book only in its
names' announcement months should keep a large share of RND's active return
while holding equities only ~1/3 of the time: a lower-beta, cash-hedged
sleeve. Expected failure: the premium is spread evenly through the year
(then this earns ~1/3 of RND plus T-bills and loses on Sharpe to SPY), or
announcement-month estimates are off (Sharadar dates are SEC FILING dates,
which lag the press release by days to weeks; see the window2 variant).

RULE (fixed before any run):
  * Book: each June (last close; signal day = previous trading day) the
    RND book exactly as R-2026-11-10-RND defines it (top 20% of S&P 500 R&D
    firms by RD/ME), with signals read on the signal day (RNDREV's
    rdme_scores). Need >= 20 eligible names, else keep the previous book.
  * Expected-report months: from the ticker's Sharadar ART rows (one per
    quarterly/annual filing; `date` = when the filing became public). A name
    is "expected" in calendar month m if it had a filing whose public date
    fell in month m twelve months earlier (Frazzini-Lamont's last-year rule,
    on filing dates).
  * Each month end (trade day dates[i]; signal day dates[i-1]): for next
    month m, hold every book name expected in m at weight 1/N (N = book
    size); the rest of the capital is in T-bills. Weights drift with prices
    within the month; reset at the next month end. SPY before the first book.
  * Variants (robustness gate): window2 (expected if last year's filing was
    in m OR m+1, since the release precedes the filing); lag3 (expected if
    a filing fell in m-3: the latest quarter's cadence); book top 15% and
    25%.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault (lab original), strict bar +
    FF5+Mom alpha gate. Turnover: ~monthly in/out of a third of the book.
  * Family "rnd-intensity" (same core): lifetime 5 (+5 RNDREV, +5 RNDSECT
    if they run first) -> trials 20; the harness takes the larger count.
DATA-TIMING CHECK (theme 21): at trade day dates[i] the rule reads filing
dates <= dates[i-1] (all ~12 months old; lag3 ~3 months old), ARY rows
public <= dates[i-1], DAILY market value of dates[i-1] (June only) and
membership as of dates[i-1]. Nothing dated on/after the trade day is read.
DATA: ART per ticker is the query MAGICSF/QVPARITY already run (same cache on
the same UTC day); ARY/DAILY as RNDREV.
Delisted names: a held stock that delists returns 0 from its last price.
"""
import bisect
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("rndrev", _here.with_name("L-2026-11-10-RNDREV.py"))
rev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rev)
rnd, ag = rev.rnd, rev.ag

ID = "L-2026-11-11-RNDEAP"
START = rnd.START
BENCH = rnd.BENCH
_FD = {}                                              # ticker -> sorted filing dates (ART)


def filing_dates(t):
    if t not in _FD:
        try:
            rows = rb.fundamentals_pit(t, "ART")
        except Exception:  # noqa: BLE001 — a missing ticker is just no data
            rows = []
        _FD[t] = sorted({r["date"][:10] for r in rows if r.get("date")})
    return _FD[t]


def _ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m <= 0:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def expected(t, m, sd, offsets):
    """True if a filing public on/before sd fell in month m + k for some k."""
    ds = filing_dates(t)
    ds = ds[:bisect.bisect_right(ds, sd)]
    months = {d[:7] for d in ds}
    return any(_ym_add(m, k) in months for k in offsets)


def make_weights(frac=0.20, offsets=(-12,)):
    st = {}

    def pick_book(dates, i, px):
        rd = rev.rdme_scores(dates[i - 1], i, px)
        if len(rd) < 20:
            return None
        ranked = sorted(rd, key=lambda t: -rd[t])
        return ranked[:max(1, int(round(len(ranked) * frac)))]

    def weights(i, dates, px):
        if i == 0:
            st.clear()                                    # fresh state for every simulation
        month_end = i > 0 and i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if dates[i][5:7] == "06":
                b = pick_book(dates, i, px)
                if b:
                    st["book"] = b
            if "book" in st:
                sd, m = dates[i - 1], dates[i + 1][:7]
                book = st["book"]
                on = [t for t in book if px[t][i - 1] is not None and expected(t, m, sd, offsets)]
                st["w"] = {t: 1.0 / len(book) for t in on}
                st["cash"] = 1.0 - sum(st["w"].values())
                st["base"] = {t: px[t][i] for t in on}
                st["last"] = dict(st["base"])
                return dict(st["w"])
        if "book" not in st:
            return {BENCH: 1.0}
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t] if st["base"][t] else 0.0
        tot = sum(v.values()) + st["cash"]
        return {t: x / tot for t, x in v.items()} if tot > 0 else {}
    return weights


weights = make_weights()
VARIANTS = {"window2": make_weights(offsets=(-12, -11)), "lag3": make_weights(offsets=(-3,)),
            "top15": make_weights(0.15), "top25": make_weights(0.25)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=20,
        family="rnd-intensity", variants=VARIANTS, source="sharadar",
        notes=("Lab RND x earnings-announcement premium: the RND book (top 20% RD/ME, each June) held only in "
               "each name's expected report month (an ART filing public in the same month last year), "
               "1/N per name, T-bills otherwise; signals read the day before the trade; variants window2, "
               "lag3, top15/25; survivorship-free"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
