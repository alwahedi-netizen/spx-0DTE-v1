"""L-2026-11-14-RNDQUAL — lab original (queued 2026-11-11 as
L-2026-11-11-RNDQUAL): profitable R&D spenders. Hold point-in-time S&P 500
firms in the top 30% by R&D / market value that are ALSO in the top half of
the index by cash-based operating profitability.

INGREDIENTS (shortlist first, RESEARCH.md §2b):
  * R-2026-11-10-RND (potential 3): +12.8%/yr vs SPY +7.6%, alpha t 2.7,
    but loads RMW -0.32 (a junk tilt: cash-burning biotech/tech) and fails
    DSR / t >= 3. Its four relatives (RNDREV, RNDSECT, RNDEAP, RDINC) kept
    alpha t 2.0-2.4 and also failed t >= 3.
  * R-2026-11-10-CBOP (potential 3): Ball-Gerakos-Linnainmaa-Nikolaev cash
    profitability, RMW +0.27, alpha t 1.0; its active return correlates
    -0.08 with RND's (ledger series, monthly, 2000-2024).
  * Opposing evidence, stated up front: Li (2011, RFS 24(9)) finds the R&D
    premium lives in financially CONSTRAINED firms — a profitability screen
    would then remove it; Wang-Rachev-Fabozzi (2026, arXiv 2611.09834)
    find intersection ("AND") portfolios earn lower premia and trade more
    than single-signal sorts. STKBOOK (L-2026-11-14-STKBOOK) is the blend
    ("OR") form of the same two signals; this run is the AND form, so the
    pair answers which construction keeps the alpha.
RATIONALE (fixed before any run): the CLS mispricing is that expensed R&D
is priced as if it built nothing. Among R&D spenders that ALSO generate
cash today, the low price for their R&D is least likely to be a fair
distress discount — so if RND's alpha is mispricing rather than junk
risk, it should survive (or improve) with RMW neutralised.
Expected failure regime: the 2000-02 tech unwind (high RD/ME AND high
cash profit names were cheap mega-cap tech) and if Li's constrained-firm
story is right (then alpha t falls).

RULE (fixed before any run):
  * Trade day: the last close of June each year (dates[i]); SIGNAL day =
    dates[i-1].
  * RD/ME: RNDREV's rdme_scores (S&P 500 members on the signal day, priced
    on it, rnd > 0 in the latest ARY row public <= signal day and <= 18
    months old, divided by signal-day DAILY market value).
  * CbOP: R-2026-11-10-CBOP's cbop(t, signal day) over ALL members priced
    on the signal day, ex Sharadar sector "Financial Services".
  * Hold: firms in the top 30% of the R&D firms by RD/ME AND with CbOP >=
    the cross-sectional median CbOP of the scored members; equal weight;
    drift until next June. Needs >= 20 R&D firms, else keep the previous
    book; < 10 picked -> SPY for the year; SPY before the first book.
  * Variants (robustness gate): RD/ME top 20% / 40% (CbOP half); CbOP top
    third / top two-thirds (RD/ME 30%).
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha
    gate. Family "rnd-intensity" (same RD/ME core): lifetime 20 + 5 ->
    trials 25.
PASS CRITERION (written before any run): harness verdict PASS with every
world-class gate. Learning criterion (not a pass): RMW loading > -0.10 AND
alpha t >= 2.7 (RND's) -> RND's alpha was not junk exposure.

DATA-TIMING: all inputs dated <= dates[i-1], strictly before the trade
day dates[i]: ARY rows public <= dates[i-1], DAILY market value of
dates[i-1], membership and price on dates[i-1]. px[.][i] only drifts the
held book. Weights decided at close i earn close i -> close i+1.
Delisted names: a held stock that delists returns 0 from its last price.
"""
import importlib.util
import json
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


rr = _load("rndrev_core", "L-2026-11-10-RNDREV.py")   # make_annual (strict), rdme_scores
cb = _load("cbop_core", "R-2026-11-10-CBOP.py")       # cbop(), sector()
ag = rr.ag

ID = "L-2026-11-14-RNDQUAL"
START = rr.START
BENCH = rr.BENCH


def cbop_scores(sd, i, px):
    out = {}
    for t in ag.members(sd):
        if t not in px or px[t][i - 1] is None or cb.sector(t) in cb.EXCLUDE:
            continue
        x = cb.cbop(t, sd)
        if x:
            out[t] = x[0]
    return out


def make_weights(q_rd=0.30, q_cb=0.50):
    def select(dates, i, px):
        sd = dates[i - 1]
        rd = rr.rdme_scores(sd, i, px)
        if len(rd) < 20:
            return None                                  # keep the previous book
        cbs = cbop_scores(sd, i, px)
        if len(cbs) < 20:
            return None
        n = max(1, int(round(len(rd) * q_rd)))
        hi_rd = [t for t, _ in sorted(rd.items(), key=lambda x: -x[1])[:n]]
        k = max(1, int(round(len(cbs) * q_cb)))
        good = {t for t, _ in sorted(cbs.items(), key=lambda x: -x[1])[:k]}
        pick = sorted(t for t in hi_rd if t in good)
        if len(pick) < 10:
            return {BENCH: 1.0}                          # too few names: SPY for the year
        return {t: 1.0 / len(pick) for t in pick}
    return rr.make_annual(select)


weights = make_weights()
VARIANTS = {"rd20": make_weights(0.20), "rd40": make_weights(0.40),
            "cb33": make_weights(q_cb=1 / 3), "cb67": make_weights(q_cb=2 / 3)}


if __name__ == "__main__":
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=25,
        family="rnd-intensity", variants=VARIANTS, source="sharadar",
        notes=("Lab RND x CBOP (AND): point-in-time S&P 500 R&D firms in the top 30% by RD/ME that are "
               "also in the top half of members by cash-based operating profitability (ex financials), "
               "equal weight, each June; signals read the day BEFORE the trade; SPY if < 10 names; "
               "variants RD 20/40%, CbOP third/two-thirds; survivorship-free; queued as "
               "L-2026-11-11-RNDQUAL"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
