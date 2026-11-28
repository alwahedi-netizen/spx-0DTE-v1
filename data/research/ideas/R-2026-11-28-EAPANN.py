"""R-2026-11-28-EAPANN — the earnings-announcement premium (Barber, De George,
Lehavy & Trueman 2013), U.S. annual-announcement construction, on the
point-in-time S&P 500 with TRUE release dates (Sharadar 8-K item 2.02).

Promotes the ledger row I-2026-11-11-EAP (scored 66, "idea"; blocked then
because Sharadar fundamentals carry SEC filing dates, not release dates).
Theme 37 (round 2) found Sharadar's EVENTS table: 8-K filings with event code
22 = item 2.02 "Results of Operations and Financial Condition" = the earnings
press release, from 2004-10. That unlocks a point-in-time test.
SOURCES:
  * Barber, B., De George, E., Lehavy, R. & Trueman, B. (2013), "The earnings
    announcement premium around the globe", Journal of Financial Economics
    108(1) 118-138 (working paper read:
    https://en-coller.tau.ac.il/sites/nihul_en.tau.ac.il/files/media_server/Recanati/management/seminars/account/barber.pdf).
    Headline used for replication (Table V, last row, "United States
    portfolios", 1991-2010, 240 months): expected annual announcers minus
    expected non-announcers, value-weighted at the firm level, +0.759%/month
    (t 3.35, monthly Sharpe 0.217); expected month = the month the firm
    released ANNUAL earnings in the prior fiscal year; a leg needs >= 10 firms.
  * Frazzini, A. & Lamont, O. (2007) NBER w13090 (the original: > 60bp/month
    1972-2004, strongest in large caps; quarterly announcements) — its window
    ends before our 8-K dates start, so it cannot be replicated here; its
    quarterly construction is the variant I-2026-11-28-EAPQTR.
RATIONALE (fixed before any run): stocks earn more in the month they are
expected to announce. Explanations in the sources: attention-driven buying
pressure before/at the release (Frazzini-Lamont: volume and returns rise
together) and priced announcement risk (Savor-Wilson 2016: announcers carry
systematic news). The dates are predictable a year ahead, so the long/short
book is known in advance and is nearly orthogonal to the FF5+Mom factors
(both sources: factor loadings small). A market-neutral, factor-orthogonal
sleeve is the shape the book lacks (STKBOOK added equity beta, corr 0.63).
Expected failure regime: post-2010 if the premium was arbitraged once
announcement calendars became free (theme 4: published calendar effects
decay); months with a thin long leg (annual releases bunch in Jan-Feb for
December year-ends, so the other months often fail the 10-firm rule and sit
in T-bills).

RULE (fixed before any run):
  * Announcements: for each ARQ row (Sharadar fundamentals, dimension ARQ)
    with reportperiod R, the announcement is the FIRST 8-K with event code 22
    dated in (R, R + 100 days]. Annual announcement = the one for a row whose
    fiscalperiod ends "Q4" (the fiscal-year-end quarter). An announcement is
    only usable on decision day D if its ARQ row is public (`date` <= D).
  * Decision day D = dates[i-1]; trade at the close of dates[i] = the last
    trading day of month t-1; hold through month t.
  * Universe: point-in-time S&P 500 members on D with prices on dates[i-1]
    and dates[i]. A firm is classified only if its latest usable annual
    announcement falls in calendar months t-12 .. t-1 (otherwise it has no
    expected month and is left out, as in the source):
    expected ANNOUNCER if that month is t-12, NON-ANNOUNCER otherwise.
  * Book: long announcers +1.0 total, short non-announcers -1.0 total,
    value-weighted by market cap on D (latest public ARQ marketcap scaled by
    the adjusted-price change since that row's date). Gross 2.0, net 0;
    short proceeds earn T-bills (harness). Positions drift inside the month;
    re-formed at each month's last close. Fewer than 10 firms in either leg
    -> no position that month (T-bills).
  * Variants (robustness gate): equal weight; >= 20 firms per leg; release
    window 60 and 150 days.
  * Benchmark T-bills (market-neutral), 5bp per unit of turnover, start
    2005-09 -> vault (2024-11). First book: 2005-10-31 for November 2005.
    8-K item 2.02 rows begin 2004-09 and are only partly covered until
    mid-October 2004 (checked: 194 code-22 rows 2004-09-01..15, 409 in
    10-01..15, 2,207 in 10-16..31), so the first month whose t-12 month is
    fully covered is 2005-11; earlier months hold T-bills. Strict bar +
    FF5+Mom factor-alpha gate (asset_class "stocks").
  * family "earnings-announcement-premium" (new). HONEST TRIALS: the same
    timing mechanism already ran once as L-2026-11-11-RNDEAP (RND book held in
    expected announcement months; 5 trials in family rnd-intensity), so
    trials = 5 (RNDEAP) + 1 + 4 variants = 10.
REPLICATION GATE (rule 1, pre-registered, runs BEFORE evaluate): source-
overlap window = the 62 months 2005-11 .. 2010-12. Gross of costs (the source
charges none), the mean monthly long-minus-short return over the months the
book is formed must be >= +0.3795% (half of 0.759%) and positive. Otherwise
print "harness/data suspect", do NOT call evaluate, spend no trial; the
quarterly variant I-2026-11-28-EAPQTR then does not run either.
Known differences: our universe is the S&P 500 (source: all U.S. firms with
Bloomberg/IBES dates, value-weighted, so large caps dominate both); our dates
are 8-K filing dates (item 2.02 must be furnished within 4 business days of
the release, usually the same day), so a release on the last day of a month
can be dated to the next month; only 62 months overlap (expected t ~1.7 even
if the source's premium is fully present).
PASS CRITERION (written before any run): replication gate met AND harness
verdict PASS vs T-bills with every world-class gate (99% confidence, held-out
last 30% Sharpe beats T-bills with positive return, DSR >= 0.95 at 10 trials,
active t >= 3, 2x costs, >= 70% of variants beat T-bills, FF5+Mom alpha
t >= 2). A PASS goes to the lead's red team, then ONE vault test (run by the
lead; never vault=True here).

DATA-TIMING: the book for month t is decided from dates[i-1] (the day before
the trade day dates[i], the last close of month t-1): membership, prices and
market caps of dates[i-1], 8-K dates in months t-12 .. t-1 (all strictly
before dates[i]) and ARQ rows public <= dates[i-1]. No price, filing or event
on or after the trade day is read. Weights decided at close i earn close i ->
close i+1 (harness), so the first return earned is month t's first day.
Delisted names: a held stock that delists returns 0 from its last price.
Runtime: ~2 Sharadar calls per ticker (EVENTS + ARQ, ~1,000 tickers, cached
per UTC day and shared with I-2026-11-28-EAPQTR) plus the price panel.
"""
import bisect
import importlib.util
import json
import sys
import time
import urllib.error
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("assetgrow_core", _here.with_name("R-2026-11-08-ASSETGROW.py"))
ag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ag)                      # members(), all_tickers(), _num()

ID = "R-2026-11-28-EAPANN"
START = "2005-09-01"
FIRST_MONTH = "2005-11"                          # first held month with a fully covered t-12
FAMILY = "earnings-announcement-premium"
TRIALS = 5 + 1 + 4
REPL = ("2005-11", "2010-12", 0.003795)          # months (inclusive), minimum mean monthly L-S

_raw_fetch = rb._sh_fetch


def _patient_fetch(table, params):
    """Sharadar call with back-off on HTTP 429 (shared key, busy Saturdays)."""
    for k in range(20):
        try:
            return _raw_fetch(table, params)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(min(15 * (k + 1), 120))
    return _raw_fetch(table, params)


rb._sh_fetch = _patient_fetch

_EV, _ARQ, _ANN = {}, {}, {}


def releases(t):
    """Sorted 8-K item 2.02 filing dates of ticker t."""
    if t not in _EV:
        try:
            rows = rb.sharadar("events", ticker=t)
        except Exception:  # noqa: BLE001 — a missing ticker is just no data
            rows = []
        _EV[t] = sorted({r["date"][:10] for r in rows
                         if "22" in str(r.get("eventcodes") or "").split("|")})
    return _EV[t]


def arq(t):
    """(sorted public dates, ARQ rows) of ticker t."""
    if t not in _ARQ:
        try:
            rows = [r for r in rb.fundamentals_pit(t, "ARQ") if r.get("date") and r.get("reportperiod")]
        except Exception:  # noqa: BLE001
            rows = []
        _ARQ[t] = ([r["date"][:10] for r in rows], rows)
    return _ARQ[t]


def _plus(d, n):
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def announcements(t, win=100):
    """[(release date, is_annual, public date of its ARQ row)] — the first
    item 2.02 8-K in (reportperiod, reportperiod + win days] per ARQ row."""
    key = (t, win)
    if key not in _ANN:
        ev = releases(t)
        out, seen = [], set()
        for r in arq(t)[1]:
            rp = r["reportperiod"][:10]
            if rp in seen:                        # later restated rows: keep the first public one
                continue
            seen.add(rp)
            k = bisect.bisect_right(ev, rp)
            if k < len(ev) and ev[k] <= _plus(rp, win):
                fp = str(r.get("fiscalperiod") or "")
                out.append((ev[k], fp.endswith("Q4"), r["date"][:10]))
        _ANN[key] = sorted(out)
    return _ANN[key]


def mindex(d):
    """Calendar month index of an ISO date or YYYY-MM."""
    return int(d[:4]) * 12 + int(d[5:7]) - 1


def mcap(t, sd, i, dates, px):
    """Market cap on signal day dates[i-1] = sd: latest public ARQ marketcap
    scaled by the adjusted-price change since that row's date."""
    ds, rows = arq(t)
    k = bisect.bisect_right(ds, sd)
    for r in reversed(rows[:k]):
        m = ag._num(r.get("marketcap"))
        if m and m > 0:
            j = bisect.bisect_right(dates, r["date"][:10]) - 1
            j = min(j, i - 1)
            p0 = px[t][j] if j >= 0 else None
            p1 = px[t][i - 1]
            return m * p1 / p0 if (p0 and p1) else m
    return None


def classify_annual(t, sd, tm, win=100):
    """True = expected announcer in month index tm, False = non-announcer,
    None = no usable annual announcement in months tm-12 .. tm-1."""
    last = None
    for e, annual, pub in announcements(t, win):
        if annual and pub <= sd and tm - 12 <= mindex(e) <= tm - 1:
            last = e if (last is None or e > last) else last
    if last is None:
        return None
    return mindex(last) == tm - 12


def book(classify, i, dates, px, vw=True, min_leg=10):
    """{ticker: signed weight} for the month starting after dates[i], or None."""
    if dates[i + 1][:7] < FIRST_MONTH:
        return None
    sd = dates[i - 1]
    tm = mindex(dates[i + 1])                     # the month being held (calendar is known)
    longs, shorts = [], []
    for t in ag.members(sd):
        if t not in px or px[t][i - 1] is None or px[t][i] is None:
            continue
        c = classify(t, sd, tm)
        if c is None:
            continue
        w = mcap(t, sd, i, dates, px) if vw else 1.0
        if not w:
            continue
        (longs if c else shorts).append((t, w))
    if len(longs) < min_leg or len(shorts) < min_leg:
        return None
    lt, st_ = sum(w for _, w in longs), sum(w for _, w in shorts)
    out = {t: w / lt for t, w in longs}
    for t, w in shorts:
        out[t] = out.get(t, 0.0) - w / st_
    return out


def make_weights(classify, vw=True, min_leg=10, log=None):
    """Monthly signed book (+1 long / -1 short), drifting inside the month."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i > 0 and i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            st.clear()
            w = book(classify, i, dates, px, vw, min_leg)
            if w:
                if log is not None:
                    log.add(dates[i + 1][:7])
                st["w"], st["base"] = w, {t: px[t][i] for t in w}
                st["last"] = dict(st["base"])
                return dict(w)
        if "w" not in st:
            return {}
        pos = {}
        for t, w0 in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            pos[t] = w0 * st["last"][t] / st["base"][t]
        nav = 1.0 + sum(pos[t] - st["w"][t] for t in pos)   # cash fixed at rebalance
        return {t: v / nav for t, v in pos.items()} if nav > 0 else {}
    return weights


def annual(win=100):
    return lambda t, sd, tm: classify_annual(t, sd, tm, win)


weights = make_weights(annual())
VARIANTS = {"ew": make_weights(annual(), vw=False), "min20": make_weights(annual(), min_leg=20),
            "win60": make_weights(annual(60)), "win150": make_weights(annual(150))}


def universe():
    return ag.all_tickers("2004-01-01")


def replication(tickers, make):
    """Gross mean monthly long-minus-short return over the formed months of
    the source-overlap window REPL."""
    dates, px = rb.sharadar_prices(tickers, START)
    keep = sum(1 for d in dates if d[:7] <= REPL[1])
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    formed = set()
    rets, _ = rb.simulate(make(formed), dates, px, rf, 0.0)
    by_m = {}
    for k, r in enumerate(rets):                  # rets[k] earns dates[k] -> dates[k+1]
        m = dates[k + 1][:7]
        a = by_m.setdefault(m, [1.0, 1.0])
        a[0] *= 1 + r
        a[1] *= 1 + rf[k + 1]
    ls = [by_m[m][0] - by_m[m][1] for m in sorted(by_m) if REPL[0] <= m <= REPL[1] and m in formed]
    mean = sum(ls) / len(ls) if ls else 0.0
    return {"window": [REPL[0], REPL[1]], "months_formed": len(ls),
            "mean_monthly_ls": round(mean, 5), "t": round(rb.t_stat(ls), 2) if len(ls) > 2 else None,
            "required": REPL[2], "replicated": bool(ls) and mean > 0 and mean >= REPL[2]}


if __name__ == "__main__":
    tick = universe()
    rep = replication(tick, lambda log: make_weights(annual(), log=log))
    print("REPLICATION", json.dumps(rep))
    if not rep["replicated"]:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "harness/data suspect: replication gate failed", "replication": rep}))
        sys.exit(0)
    out = rb.evaluate(
        ID, weights, tick, None, start=START, asset_class="stocks", trials=TRIALS,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Barber-De George-Lehavy-Trueman earnings-announcement premium, U.S. annual construction: "
               "PIT S&P 500; expected announcer in month t = annual release (first 8-K item 2.02 within "
               "100 days of the Q4 ARQ reportperiod) in month t-12; long announcers +1 / short classified "
               "non-announcers -1, value-weighted, monthly, drifting; >= 10 per leg else T-bills; signal "
               "day = day before trade; bench T-bills; variants EW, min 20, window 60/150; trials 10 incl. "
               f"RNDEAP's 5; first month 2005-11; replication 2005-11..2010-12 mean {rep['mean_monthly_ls']}/month "
               f"(t {rep['t']}, {rep['months_formed']} months) vs >= 0.003795"))
    out["replication"] = rep
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
