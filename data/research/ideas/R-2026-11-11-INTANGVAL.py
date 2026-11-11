"""R-2026-11-11-INTANGVAL — intangible-adjusted value (Arnott-Harvey-Kalesnik-
Linnainmaa 2021) on the point-in-time S&P 500 (survivorship-free).

Source: Arnott, Harvey, Kalesnik & Linnainmaa (2021) "Reports of Value's
Death May Be Greatly Exaggerated", Financial Analysts Journal 77(1) 44-67
(https://econpapers.repec.org/RePEc:taf:ufajxx:v:77:y:2021:i:1:p:44-67):
book value misses internally built intangibles; adding capitalised R&D and
30% of SG&A to book equity ("iHML") beats the traditional price-to-book
measure from the 1990s on and shortens value's 2007-20 drawdown from ~13.5
to ~3.5 years (summary of the paper; full text paywalled). Capitalisation
convention: Peters & Taylor (2017, JFE 123(2) 251-272): knowledge capital =
perpetual inventory of R&D; organisation capital = perpetual inventory of
30% of SG&A excluding R&D ("MainSG&A"); R&D and SG&A capital both decline
~20% a year (as summarised by Iqbal, Rajgopal et al., "Value of Internally
Generated Intangible Capital", Columbia CEASA working paper, §2:
https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/value_internally_generated_intangible_capital.pdf).
Initial stock: Eisfeldt-Papanikolaou (2013, JF 68(4)) O0 = first flow /
(g + delta) with g = 10%.
Ledger: new mechanism (no intangibles-adjusted value row; KNOWLEDGE.md queue
asks for "an intangible-adjusted MAGICSF" after RND's alpha t 2.7 — this is
the sourced, published form of that idea). Related rows: R-2026-11-10-RND
(R&D flow / ME, alpha t 2.7), I-2026-11-08-FSCORE / R-2026-11-09-FSCORE
(plain book-to-market screens), I-2026-10-28-TRENDVAL.

RATIONALE (fixed before any run): accounting expenses R&D and brand/
organisation spending, so the book equity of a software or drug company
omits most of what it owns; traditional B/M then labels intangible-heavy
firms "growth" and fills the value book with banks, energy and retailers —
the composition that lost 2007-20. Adding back the capitalised intangibles
measures value on what the firm really owns. Theme 8 bar: plain value is
HML (no alpha); the hope is that the intangible adjustment carries the part
of RND's alpha (t 2.7) that HML misses by construction.
Expected failure regime: deep-value rallies where tangible cheapness wins
(2000-06, 2021-22 energy) and intangible-heavy crashes (2000-02).

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the SIGNAL day, priced on it
    (all sectors, as HML).
  * Trade day: last close of June each year; SIGNAL day = previous trading
    day.
  * For each name, the ARY rows public on/before the signal day, ordered by
    fiscal period (`reportperiod`); the latest must be <= 18 months old
    (calendardate). Missing rnd / sgna count as 0 (Eisfeldt-Papanikolaou).
    Note: Sharadar `sgna` already EXCLUDES R&D (checked 2026-11-10 for
    CBOP), so it is Peters-Taylor's MainSG&A as is.
      K_t = (1 - 0.20) K_{t-1} + rnd_t;   O_t = (1 - 0.20) O_{t-1} + 0.30 sgna_t
      K_0 = rnd_first / (0.10 + 0.20);    O_0 = 0.30 sgna_first / (0.10 + 0.20)
      (gaps of n fiscal years depreciate n times).
  * Intangible-adjusted book = equity (latest ARY) + K + O; must be > 0.
  * iBM = adjusted book / signal-day market value (Sharadar DAILY marketcap
    x1e6; whole date falls back to the ARY marketcap if DAILY is empty).
  * Hold the top 20% by iBM, equal weight, drifting until next June; need
    >= 50 scored names, else keep the previous book; SPY before the first.
  * Variants (robustness gate): top 15% and 25%; depreciation 15% for both
    capitals (the BEA/EP rate); value-weighted top 20%.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha
    gate. Family "intangible-value" (new): trials = 1 + 4 = 5.
  * Red team: compare against the SAME book with K = O = 0 (plain B/M) — the
    adjustment, not value itself, is the hypothesis.
History caveat: Sharadar ARY starts 1993-97 for most names, so 2000-02
capitals rest on 3-7 years of flows plus the steady-state initial stock.
DATA-TIMING CHECK (theme 21): every input is dated <= dates[i-1], strictly
before the trade day dates[i]: ARY rows with public date <= dates[i-1];
DAILY market value of dates[i-1]; membership and price on dates[i-1].
Delisted names: a held stock that delists returns 0 from its last price.
"""
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

ID = "R-2026-11-11-INTANGVAL"
START = rnd.START
BENCH = rnd.BENCH


def adj_book(t, sd, dep=0.20, g=0.10, share=0.30, max_age_m=18):
    """(intangible-adjusted book, ARY marketcap) from ARY rows public <= sd, or None."""
    import bisect
    ds, rows = ag.fund(t)
    k = bisect.bisect_right(ds, sd)
    by_fy = {}
    for r in rows[:k]:                                  # later public rows win per fiscal period
        fy = (r.get("reportperiod") or r.get("calendardate") or "")[:10]
        if fy:
            by_fy[fy] = r
    if not by_fy:
        return None
    fys = sorted(by_fy)
    last = by_fy[fys[-1]]
    cd = (last.get("calendardate") or last["date"])[:10]
    if ag._months_between(cd, sd) > max_age_m:
        return None
    eq = ag._num(last.get("equity"))
    if eq is None:
        return None
    K = O = None
    prev = None
    for fy in fys:
        r = by_fy[fy]
        rd = max(ag._num(r.get("rnd")) or 0.0, 0.0)
        sg = share * max(ag._num(r.get("sgna")) or 0.0, 0.0)
        if K is None:
            K, O = rd / (g + dep), sg / (g + dep)
        else:
            n = max(1, round(ag._months_between(prev, fy) / 12))
            K = K * (1 - dep) ** n + rd
            O = O * (1 - dep) ** n + sg
        prev = fy
    book = eq + K + O
    if book <= 0:
        return None
    return book, ag._num(last.get("marketcap"))


def make_weights(frac=0.20, dep=0.20, vw=False):
    def select(dates, i, px):
        sd = dates[i - 1]
        daily = rnd.mcap_on(sd)
        scored = []
        for t in ag.members(sd):
            if t not in px or px[t][i - 1] is None:     # priced on the signal day
                continue
            x = adj_book(t, sd, dep=dep)
            if not x:
                continue
            me = daily.get(t) if daily else x[1]
            if not me or me <= 0:
                continue
            scored.append((-x[0] / me, me, t))         # highest iBM first
        if len(scored) < 50:
            return None
        scored.sort()
        pick = scored[:max(1, int(round(len(scored) * frac)))]
        if vw:
            tot = sum(me for _, me, _ in pick)
            return {t: me / tot for _, me, t in pick}
        return {t: 1.0 / len(pick) for _, _, t in pick}
    return rev.make_annual(select)


weights = make_weights()
VARIANTS = {"top15": make_weights(0.15), "top25": make_weights(0.25),
            "dep15": make_weights(dep=0.15), "vw": make_weights(vw=True)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="intangible-value", variants=VARIANTS, source="sharadar",
        notes=("Arnott-Harvey-Kalesnik-Linnainmaa intangible-adjusted value: top 20% of the point-in-time "
               "S&P 500 by (equity + capitalised R&D + 30% SG&A capital, 20%/yr depreciation, EP initial "
               "stock) / signal-day DAILY market value, equal weight, each June; signals read the day before "
               "the trade; variants top 15/25%, 15% depreciation, value-weighted; survivorship-free"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
