"""R-2026-11-14-SPADDS — S&P 500 additions underperform after joining
(Bennett-Stulz-Wang): long SPY, short the stocks added to the index in the
last 12 months, dollar-neutral, on point-in-time Sharadar data.

Source: Bennett, Stulz & Wang (2020) "Does Joining the S&P 500 Index Hurt
Firms?", NBER w27593 / SSRN (https://www.nber.org/papers/w27593); summary
with the subperiod table: CXO Advisory 2020-08-11
(https://www.cxoadvisory.com/fundamental-valuation/sp-500-index-additions-underperform/).
659 additions 1997-2017. HEADLINE: in 2008-2017 additions earn negative
abnormal returns of -0.63% to -0.73% PER MONTH over the year after the
announcement (market-adjusted and 3/4/5-factor alphas); in 1997-2007 the
year-after abnormal return is approximately zero. Independent support:
Sandifer-Smith-Impink (matched-peer study, 1989-2019, additions trail
peers by 28% after one year; Morningstar 2026 coverage). Context: Chen &
Welch (2026, arXiv 2607.06502) — published accounting anomalies earn ~7bp
a month in non-micro stocks after 2005, so a FLOW effect created by index
mechanics is a better bet for our large-cap universe than another
accounting signal (themes 8, 20).

RATIONALE (fixed before any run): since ~2008 passive funds own a large
share of every S&P 500 member, so index inclusion forces buying at
announcement whatever the price; BSW find the over-pricing unwinds over
the following year (and the firm's ROA falls after joining). The trade is
the other side of that forced demand: short the recent additions, hedged
with the index. Expected failure regime: the pre-2008 years (no effect in
the source), mega-cap momentum additions that keep rising (TSLA 2020),
and sharp junk/beta rallies (additions are more volatile — the dollar-
neutral book is net short beta; I-2026-11-14-SPADDSBETA hedges beta).

REPLICATION FIRST (RESEARCH.md § LEAGUE rule 1): this evaluate run IS the
source's own construction on our universe — the market-adjusted return of
additions (SPY minus the additions basket) — so one run both reproduces
and tests. The script also prints the replication check over the source's
own subperiods (from rb.simulate on the same rule and data; same rule, no
extra trial):
  REPLICATION PASS iff mean monthly (SPY - additions) over 2008-01..2017-12
  is >= +0.30%/month (sign right, at least half the paper's 0.63-0.73%).
  (1998-2007, where the paper finds ~0, is printed for information.)
  If it fails: log "harness/data suspect", and the variant
  I-2026-11-14-SPADDSBETA refuses to run.

RULE (fixed before any run):
  * Events: Sharadar sp500 rows with action "added" whose note carries
    "Announced YYYY-MM-DD" (719 of 727 additions since 1997-06; rows
    without it are mergers / share-class changes, not new members — BSW
    study firms joining the index). Event date = the announcement date.
  * Basket on trade day dates[i]: every added ticker whose announcement
    date is <= dates[i-1] and within the last 12 months of dates[i-1]
    (365 days), priced on dates[i-1]. A stock stays in the basket for its
    12 months even if it later leaves the index or is delisted (no
    survivorship filter; a delisted short returns 0 from its last price).
  * Weights: SPY +1.0, each basket stock -1/n (equal weight, dollar-
    neutral; short proceeds earn T-bills — harness fix 2, theme 28).
    Re-equalised whenever the basket changes and at every month end;
    weights drift with prices in between. Fewer than 5 names -> all cash.
  * Variants (robustness gate): holding window 6, 9, 15, 18 months.
  * Benchmark T-bills (bench=None: a market-neutral book must beat cash),
    5bp/side (stocks), 1998-01 (first Sharadar SEP bar 1997-12-31) ->
    vault, strict bar + FF5+Mom alpha gate. Family "sp500-additions"
    (new): trials = 1 + 4 = 5.
  * SPY prices: Sharadar SFP (fund prices) — the SEP "stocks" table has no
    ETFs, so this script adds SPY from SFP onto the stock calendar
    (rb.sharadar_prices is wrapped at run time; research_bt.py unchanged).
  * Not charged: stock-borrow fees on the short leg (S&P 500 names are
    general collateral, ~0.25-0.5%/yr) — the lead should haircut the
    result by ~0.4%/yr when reading it.
PASS CRITERION (written before any run): the harness verdict PASS (all
world-class gates incl. factor alpha t >= 2) on 1998-01 -> 2024-10, AND the
replication check above passes. Anything else is FAIL / shortlist only.

DATA-TIMING: the basket for trade day dates[i] reads announcement dates
<= dates[i-1] (S&P announces after the close, so the earliest entry is the
close of the first full trading day after it is public) and prices on
dates[i-1]; px[.][i] is read only to drift the book already held. Weights
decided at close i earn close i -> close i+1 (harness).
"""
import bisect
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-14-SPADDS"
START = "1998-01-01"
HEDGE = "SPY"
FAMILY = "sp500-additions"
FUNDS = {"SPY"}
_ANN = re.compile(r"Announced (\d{4}-\d{2}-\d{2})")


# ── data ─────────────────────────────────────────────────────────────────────

_orig_sharadar_prices = rb.sharadar_prices


def sharadar_prices_with_funds(tickers, start="1997-01-01", fetch=None):
    """Sharadar SEP for stocks + Sharadar SFP for the fund tickers in FUNDS,
    on the stock calendar (inner gaps carried, as rb.prices does)."""
    stocks = [t for t in tickers if t not in FUNDS]
    dates, px = _orig_sharadar_prices(stocks, start, fetch)
    for f in [t for t in tickers if t in FUNDS]:
        rows = rb.sharadar("sfp", fetch, ticker=f, fields="date,closeadj")
        m = {r["date"][:10]: r["closeadj"] for r in rows if r.get("closeadj")}
        px[f] = rb._ffill_inside([m.get(d) for d in dates])
    return dates, px


rb.sharadar_prices = sharadar_prices_with_funds   # run-time wrapper only


def events():
    """[(announcement date, ticker)] for genuine additions, sorted."""
    out = []
    for r in rb.sp500_history(first_year=1996):
        if r["action"] != "added":
            continue
        m = _ANN.search(r.get("note") or "")
        if m:
            out.append((m.group(1), r["ticker"]))
    return sorted(set(out))


EVENTS = events()
EV_DATES = [d for d, _ in EVENTS]
TICKERS = sorted({t for d, t in EVENTS if d >= "1996-06-01"})


def _minus_days(day, n):
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()


def basket(sd, i, px, months=12):
    """Tickers announced in (sd - window, sd], priced on signal day index i-1."""
    lo = _minus_days(sd, int(round(months * 365 / 12)))
    a, b = bisect.bisect_right(EV_DATES, lo), bisect.bisect_right(EV_DATES, sd)
    return sorted({t for _, t in EVENTS[a:b] if t in px and px[t][i - 1] is not None})


# ── weights ──────────────────────────────────────────────────────────────────

def make_weights(months=12, hedge_fn=None, min_names=5):
    """Long HEDGE x h, short the basket -1/n; h = 1 (dollar-neutral) or
    hedge_fn(names, i, px) (beta hedge). Re-set on basket change / month
    end, drift in between."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            return {}
        names = basket(dates[i - 1], i, px, months)
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if names != st.get("names") or month_end or "w" not in st:
            st["names"] = names
            if len(names) < min_names or px[HEDGE][i] is None:
                st["w"], st["base"] = {}, {}
                return {}
            h = hedge_fn(names, i, px) if hedge_fn else 1.0
            w = {t: -1.0 / len(names) for t in names}
            w[HEDGE] = h
            st["w"] = w
            st["base"] = {t: px[t][i] for t in w}
            st["last"] = dict(st["base"])
            return dict(w)
        if not st["w"]:
            return {}
        val = {}
        for t, w0 in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            val[t] = w0 * st["last"][t] / st["base"][t] if st["base"][t] else 0.0
        nav = 1.0 + sum(val[t] - st["w"][t] for t in val)
        return {t: v / nav for t, v in val.items()} if nav > 0 else {}
    return weights


weights = make_weights(12)
VARIANTS = {f"hold{m}m": make_weights(m) for m in (6, 9, 15, 18)}


# ── replication check (source subperiods; same rule, not a new trial) ────────

def _monthly_excess(rets, rf, dates):
    """{YYYY-MM: sum of daily (ret - rf)} (dates[k+1] is the day ret k lands)."""
    out = {}
    for k, r in enumerate(rets):
        m = dates[k + 1][:7]
        out[m] = out.get(m, 0.0) + r - rf[k + 1]
    return out


def replication_check(weights_fn=None, threshold=0.0030):
    weights_fn = weights_fn or make_weights(12)
    dates, px = rb.sharadar_prices(TICKERS + [HEDGE], START)
    keep = sum(1 for d in dates if d < "2018-01-01")
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(weights_fn, dates, px, rf, rb.COST_BPS["stocks"])
    mx = _monthly_excess(rets, rf, dates)

    def stat(lo, hi):
        xs = [v for m, v in mx.items() if lo <= m <= hi]
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
        return {"months": len(xs), "mean_monthly": round(mu, 5),
                "t": round(mu / sd * len(xs) ** 0.5, 2) if sd else None}
    early, late = stat("1998-01", "2007-12"), stat("2008-01", "2017-12")
    ok = late["mean_monthly"] >= threshold
    return {"source_headline": "2008-2017: additions -0.63..-0.73%/month abnormal; 1997-2007 ~0",
            "ours_1998_2007": early, "ours_2008_2017": late,
            "threshold_2008_2017": threshold, "replicated": ok,
            "verdict": "REPLICATED" if ok else "harness/data suspect"}


if __name__ == "__main__":
    rep = replication_check()
    print("REPLICATION", json.dumps(rep))
    out = rb.evaluate(
        ID, weights, TICKERS + [HEDGE], None, start=START, asset_class="stocks", trials=5,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Bennett-Stulz-Wang S&P 500 additions: long SPY (Sharadar SFP) / short equal-weight "
               "basket of stocks announced as additions in the last 12 months (announcement <= "
               "dates[i-1]), dollar-neutral, bench T-bills; variants hold 6/9/15/18m; borrow fees "
               "not charged (~0.4%/yr); replication " + rep["verdict"] + " (2008-17 mean "
               + str(rep["ours_2008_2017"]["mean_monthly"]) + "/month vs paper +0.63..0.73%)"))
    out["replication"] = rep
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
