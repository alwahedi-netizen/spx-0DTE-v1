"""L-2026-11-10-RNDREV — lab original (queued 2026-11-10, scripted 2026-11-11):
beaten-down R&D spenders. Hold point-in-time S&P 500 firms that are BOTH in
the top 30% by R&D / market value AND in the bottom 30% by 3-year return.

INGREDIENTS (shortlist first, RESEARCH.md §2b):
  * R-2026-11-10-RND (potential 3): top-20% RD/ME book, +12.8%/yr vs SPY
    +7.6%, factor alpha t 2.7 (loadings CMA 0.58, RMW -0.32, HML -0.19),
    held-out Sharpe 0.716 vs 0.688, confidence 94%; failed DSR / t >= 3.
  * R-2026-11-10-LTREV (potential 2): 5-year losers alone FAIL (7.0%/yr,
    alpha t -1.0) — past losers are not an edge on their own in large caps.
  * The ledger row's revisit condition ("if either leg shows potential >= 3
    tonight") was met by RND on 2026-11-10.
Source of the interaction: Chan, Lakonishok & Sougiannis (2001) "The Stock
Market Valuation of Research and Development Expenditures", J. Finance 56(6)
2431-2456 (https://econpapers.repec.org/RePEc:bla:jfinan:v:56:y:2001:i:6:p:2431-2456):
the high RD/ME firms with POOR past returns earned the largest excess
returns (their headline cell). This is the paper's own conditioning, run as
a Boolean AND (arXiv 2611.09834, Wang-Rachev-Fabozzi: intersection rules
trade more and their premia shrink — expect higher turnover than RND).

RATIONALE (fixed before any run): R&D is expensed, so a firm that keeps
spending on research while its share price has fallen for three years looks
like a failing business on every accounting screen. That is exactly where
investors over-extrapolate (De Bondt-Thaler) AND where intangible capital is
most ignored (CLS) — two mispricings stacked on the same names. RND's alpha
loads on CMA (+0.58) not HML (-0.19); adding the loser screen tilts the book
toward the cheap/beaten-down cell where CLS found the mispricing, so the
test is whether the alpha survives (or grows) once the value loading rises.
Expected failure regime, stated before the run: secular losers whose R&D
fails (2000-02 telecom equipment, 2008 banks have no R&D so are excluded),
and small-book concentration (the AND can leave < 15 names).

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members (rb.sp500_members) on the
    SIGNAL day, priced on the signal day (Sharadar survivorship-free).
  * Trade day: the last close of June each year (dates[i]); SIGNAL day =
    the previous trading day (dates[i-1]).
  * R&D firms only: the latest ARY row whose public `date` <= signal day
    (calendardate <= 18 months old) shows rnd > 0 (RND's rnd_row).
  * RD/ME = rnd / market value on the signal day (Sharadar DAILY marketcap,
    x1e6; if DAILY has no rows for that day the whole date falls back to the
    ARY row's marketcap) — RND's definition.
  * Past return = close(signal day - 1 month) / close(signal day - 36
    months) - 1 from the ticker's own Sharadar closeadj history (LTREV's
    history/close_near: dates <= signal day only; last close on/before each
    target <= 10 days old, else first close after it <= 5 days).
  * Scored set = R&D firms with BOTH numbers; need >= 20, else keep the
    previous book. Hold every name in the top 30% of the scored set by RD/ME
    AND in the bottom 30% of the scored set by past return, equal weight,
    drifting with prices until next June. If the AND leaves < 10 names, hold
    SPY for that year (no concentrated book). SPY before the first book.
  * Variants (robustness gate): thresholds 25% and 40% (both screens), 60-
    month past-return window (t-60..t-1), and the 35% threshold.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault (lab original: the vault
    applies), strict bar + FF5+Mom alpha gate.
  * Family "rnd-intensity" (same RD/ME core as RND): lifetime 5 -> trials 10
    (the harness takes the larger of this and the recorded family count; if
    RNDSECT / RNDEAP run first, the count is higher — honest either way).
DATA-TIMING CHECK (theme 21): every signal input is dated on or before the
SIGNAL day dates[i-1], i.e. strictly before the trade day dates[i]: ARY rows
with public date <= dates[i-1]; DAILY marketcap of dates[i-1]; closes from
the ticker's history with date <= dates[i-1]; membership as of dates[i-1].
Nothing dated on/after the trade day is read. (RND/LTREV read the trade-day
close itself; this script is one day more conservative.)
DATA: the ARY and price queries are RND's/LTREV's (same cache on the same
UTC day). DAILY is queried for the day BEFORE each June month-end (~25 new
files), shared with L-2026-11-11-RNDSECT, -RNDEAP and R-2026-11-11-INTANGVAL
if they run the same UTC day.
Delisted names: a held stock that delists returns 0 from its last price.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, _here.with_name(fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rnd = _load("rnd_core", "R-2026-11-10-RND.py")        # rnd_row, mcap_on
lt = _load("ltrev_core", "R-2026-11-10-LTREV.py")      # history, close_near, _shift
ag = rnd.ag                                            # members, all_tickers, fund

ID = "L-2026-11-10-RNDREV"
START = rnd.START
BENCH = rnd.BENCH


def make_annual(select, month="06"):
    """Rebalance to select(dates, i, px) at the last close of `month`; the
    book drifts with prices in between; SPY before the first book."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()                                  # fresh state for every simulation
        if (i > 0 and i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
                and dates[i][5:7] == month):
            w = select(dates, i, px)
            if w:
                st["w"] = w
                st["base"] = {t: px[t][i] for t in w}
                st["last"] = dict(st["base"])
                return dict(w)
        if "w" not in st:
            return {BENCH: 1.0}
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t] if st["base"][t] else 0.0
        tot = sum(v.values())
        return {t: x / tot for t, x in v.items()} if tot > 0 else {}
    return weights


def rdme_scores(sd, i, px):
    """{ticker: RD/ME} for R&D firms on signal day sd (= dates[i-1])."""
    daily = rnd.mcap_on(sd)
    out = {}
    for t in ag.members(sd):
        if t not in px or px[t][i - 1] is None:          # priced on the signal day
            continue
        x = rnd.rnd_row(t, sd)
        if not x:
            continue
        me = daily.get(t) if daily else x[1]
        if me and me > 0:
            out[t] = x[0] / me
    return out


def past_ret(t, sd, months):
    old = lt.close_near(t, lt._shift(sd, months), sd)
    recent = lt.close_near(t, lt._shift(sd, 1), sd)
    if not old or not recent or old <= 0:
        return None
    return recent / old - 1


def make_weights(q=0.30, months=36):
    def select(dates, i, px):
        sd = dates[i - 1]
        rd = rdme_scores(sd, i, px)
        scored = [(rd[t], r, t) for t in rd for r in [past_ret(t, sd, months)] if r is not None]
        if len(scored) < 20:
            return None                                  # keep the previous book
        n = max(1, int(round(len(scored) * q)))
        hi_rd = {t for _, _, t in sorted(scored, key=lambda x: -x[0])[:n]}
        losers = {t for _, _, t in sorted(scored, key=lambda x: x[1])[:n]}
        pick = sorted(hi_rd & losers)
        if len(pick) < 10:
            return {BENCH: 1.0}                          # too few names: SPY for the year
        return {t: 1.0 / len(pick) for t in pick}
    return make_annual(select)


weights = make_weights()
VARIANTS = {"q25": make_weights(0.25), "q35": make_weights(0.35),
            "q40": make_weights(0.40), "win60": make_weights(months=60)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=10,
        family="rnd-intensity", variants=VARIANTS, source="sharadar",
        notes=("Lab RND x LTREV: point-in-time S&P 500 R&D firms in the top 30% by RD/ME (rnd / signal-day "
               "DAILY market value) AND the bottom 30% by t-36..t-1 month return (Sharadar closeadj), equal "
               "weight, each June; signals read the day BEFORE the trade; SPY if < 10 names; variants "
               "25/35/40% thresholds, 60-month window; survivorship-free"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
