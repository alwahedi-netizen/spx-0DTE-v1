"""L-2026-11-14-STKBOOK — lab original: ONE stock book made of the four
honest-data stock sleeves that each beat SPY on survivorship-free data
through different channels, held in equal parts.

INGREDIENTS (shortlist first, RESEARCH.md §2b; all point-in-time S&P 500,
Sharadar, 2000-01 -> vault):
  * R-2026-11-10-RND  (R&D / market value, top 20%, June)   +12.8%/yr, alpha t 2.7, active t 2.3
  * R-2026-11-07-MAGICSF (EBIT/EV + ROIC, best 30, monthly) +14.2%/yr, alpha t 2.8, active t >= 3
  * R-2026-11-09-NETISS (lowest net share issuance 20%, June) +11.5%/yr, 99.8% conf., alpha t 1.0
  * R-2026-11-10-CBOP (cash operating profitability 20%, June) +9.5%/yr, alpha t 1.0
  (SPY +7.6%/yr.) Their ACTIVE returns are nearly uncorrelated (ledger
  monthly series, 2000-2024: RND-NETISS 0.09, RND-CBOP -0.08, NETISS-CBOP
  -0.03; MAGICSF has no saved series) and they load on different factors
  (RND: CMA +0.58 / RMW -0.32; CBOP: RMW +0.27; MAGICSF: value-quality;
  NETISS: issuance/CMA).
  * Construction evidence: Wang-Rachev-Fabozzi (2026, arXiv 2611.09834):
    blends ("OR"/rank-sum) of signals keep premia and trade less than
    intersections ("AND"); theme 13 (gating value destroyed its alpha) and
    theme 23 (books of shortlisted blocks are the strongest results in
    commodities and rates) point the same way. Practitioner standard:
    multi-signal composites (AQR, Robeco) rather than single anomalies.
RATIONALE (fixed before any run): every single stock anomaly on honest
data fails the t >= 3 / DSR bars because its active return is too noisy
for 25 years (themes 8, 20). If four mispricing channels with ~zero
correlation of active returns are held together, the active return's
noise falls by ~1/2 while its mean is the average — the active t should
rise toward sqrt(4) x the average sleeve t, and the alphas (RND, MAGICSF)
are kept, not gated away. This is the stocks analogue of CMDBOOK/RATESLEV.
Expected failure regime: the 2017-24 mega-cap era (MAGICSF and RND both
lagged in it — theme 19) and 2000-02 tech for RND; the book is fully
invested equities, so 2008 is not softened.

RULE (fixed before any run):
  * Four sleeves, each 1/4 of the book (sleeve weights reset to 1/4 daily
    by averaging the sleeves' normalised weights; inside each sleeve the
    names drift between that sleeve's rebalances):
    - RND: top 20% of R&D firms by RD/ME, equal weight, each June
      (RNDREV's rdme_scores);
    - QV: members ex "Financial Services"/"Utilities", rank-sum of EBIT/EV
      (DAILY evebit > 0) and latest ART roic, best 30, equal weight, each
      month end (MAGICSF's inputs; MAGICSF itself kept equal weights
      constant inside the month — here they drift, which trades less);
    - NETISS: lowest 20% by ln(sharesbas / prior-year sharesbas),
      value-weighted by ARY marketcap, each June (NETISS's issuance());
    - CBOP: highest 20% by cash operating profitability / assets ex
      "Financial Services", value-weighted, each June (CBOP's cbop()).
    A sleeve without a book yet holds SPY (warm-up).
  * STRICTER TIMING than the ingredients' original runs: every sleeve
    reads its signal on the day BEFORE its trade day (as RNDREV/RNDSECT).
  * Variants (robustness gate): drop-one — the four 3-sleeve books.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha
    gate. Family "stk-composite" (new). HONEST TRIALS: the ingredients
    were picked after their results, so trials = their families' lifetime
    counts (rnd-intensity 20 + GREENBLATT 20 + net-issuance 5 +
    cash-profitability 5 = 50) + 1 + 4 variants = 55.
PASS CRITERION (written before any run): harness verdict PASS with every
world-class gate (99% confidence vs SPY, held-out win, DSR >= 0.95 at 55
trials, active t >= 3, 2x costs, >= 70% of drop-one books beat SPY, factor
alpha t >= 2). A PASS goes to the lead's red team, then ONE vault test
(the lead runs it; never vault=True here).

DATA-TIMING: each sleeve's trade day is dates[i] (last close of June or
of the month); its signal day is dates[i-1]: ARY/ART rows public <=
dates[i-1], DAILY evebit / marketcap of dates[i-1], membership and price
on dates[i-1]. px[.][i] only drifts the held book. Weights decided at
close i earn close i -> close i+1.
Delisted names: a held stock that delists returns 0 from its last price.
Runtime: ~300 DAILY calls (one per month-end signal day, ~0.9 s each)
on top of the shared ARY / ART / price queries; run on the same UTC day as
the other stock scripts to share the per-day cache.
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


rr = _load("rndrev_core", "L-2026-11-10-RNDREV.py")   # strict make_annual, rdme_scores
cb = _load("cbop_core", "R-2026-11-10-CBOP.py")       # cbop(), sector(), EXCLUDE
ni = cb.ni                                             # NETISS: issuance()
mg = _load("magicsf_core", "R-2026-11-07-MAGICSF.py")  # earnings_yield, roic_asof, members, SECTOR
ag = rr.ag

ID = "L-2026-11-14-STKBOOK"
START = "2000-01-01"
BENCH = "SPY"
FAMILY = "stk-composite"
TRIALS = 20 + 20 + 5 + 5 + 1 + 4


# ── sleeves (each returns a weights fn, normalised to 1) ─────────────────────

def sleeve_rnd(q=0.20):
    def select(dates, i, px):
        rd = rr.rdme_scores(dates[i - 1], i, px)
        if len(rd) < 20:
            return None
        n = max(1, int(round(len(rd) * q)))
        pick = [t for t, _ in sorted(rd.items(), key=lambda x: -x[1])[:n]]
        return {t: 1.0 / len(pick) for t in pick}
    return rr.make_annual(select)


def sleeve_netiss(q=0.20):
    def select(dates, i, px):
        sd = dates[i - 1]
        scored = []
        for t in ni.ag.members(sd):
            if t not in px or px[t][i - 1] is None:
                continue
            x = ni.issuance(t, sd)
            if x:
                scored.append((x[0], x[1], t))
        if len(scored) < 20:
            return None
        scored.sort()                                   # most negative issuance first
        pick = scored[:max(1, int(round(len(scored) * q)))]
        tot = sum(mc for _, mc, _ in pick)
        return {t: mc / tot for _, mc, t in pick}
    return rr.make_annual(select)


def sleeve_cbop(q=0.20):
    def select(dates, i, px):
        sd = dates[i - 1]
        scored = []
        for t in cb.ag.members(sd):
            if t not in px or px[t][i - 1] is None or cb.sector(t) in cb.EXCLUDE:
                continue
            x = cb.cbop(t, sd)
            if x:
                scored.append((-x[0], x[1], t))         # highest CbOP first
        if len(scored) < 20:
            return None
        scored.sort()
        pick = scored[:max(1, int(round(len(scored) * q)))]
        tot = sum(mc for _, mc, _ in pick)
        return {t: mc / tot for _, mc, t in pick}
    return rr.make_annual(select)


def sleeve_qv(n_hold=30):
    """MAGICSF inputs on the signal day dates[i-1]; re-formed at every month's
    last close; names drift inside the month."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i > 0 and i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            sd = dates[i - 1]
            ey = mg.earnings_yield(sd)
            cand = []
            for t in mg.members(sd):
                if (mg.SECTOR.get(t) in mg.EXCLUDE or t not in ey or t not in px
                        or px[t][i - 1] is None or px[t][i] is None):
                    continue
                r = mg.roic_asof(t, sd)
                if r is not None:
                    cand.append((t, ey[t], r))
            if cand:
                by_ey = {t: k for k, (t, _, _) in enumerate(sorted(cand, key=lambda x: -x[1]))}
                by_rc = {t: k for k, (t, _, _) in enumerate(sorted(cand, key=lambda x: -x[2]))}
                best = sorted(by_ey, key=lambda t: (by_ey[t] + by_rc[t], t))[:n_hold]
                st["w"] = {t: 1.0 / len(best) for t in best}
                st["base"] = {t: px[t][i] for t in best}
                st["last"] = dict(st["base"])
                return dict(st["w"])
        if "w" not in st:
            return {BENCH: 1.0}
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t]
        tot = sum(v.values())
        return {t: x / tot for t, x in v.items()} if tot > 0 else {BENCH: 1.0}
    return weights


SLEEVES = {"rnd": sleeve_rnd, "qv": sleeve_qv, "netiss": sleeve_netiss, "cbop": sleeve_cbop}


def make_book(names=tuple(SLEEVES)):
    """Equal parts of the named sleeves (fresh sleeve state per book)."""
    fns = [SLEEVES[n]() for n in names]

    def weights(i, dates, px):
        out = {}
        for fn in fns:
            w = fn(i, dates, px) or {}
            tot = sum(w.values())
            if tot <= 0:
                w, tot = {BENCH: 1.0}, 1.0
            for t, x in w.items():
                out[t] = out.get(t, 0.0) + x / tot / len(fns)
        return out
    return weights


weights = make_book()
VARIANTS = {f"drop_{n}": make_book(tuple(k for k in SLEEVES if k != n)) for n in SLEEVES}


def universe():
    return sorted(set(ag.all_tickers(START)) | set(ni.ag.all_tickers(START))
                  | set(cb.ag.all_tickers(START)) | set(mg.TICKERS))


if __name__ == "__main__":
    out = rb.evaluate(
        ID, weights, universe(), BENCH, start=START, asset_class="stocks", trials=TRIALS,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Lab stock book: equal parts RND (RD/ME top 20%, June), QV (MAGICSF EBIT/EV + ROIC best "
               "30, monthly, drifting), NETISS (lowest issuance 20%, VW, June), CBOP (cash profitability "
               "top 20% ex fin., VW, June); every sleeve reads its signal the day before its trade; "
               "variants drop-one; trials 55 = ingredient families' lifetime counts + 5"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
