"""R-2026-11-11-RDINC — significant R&D increases (Eberhart-Maxwell-Siddique
2004), long-only, on the point-in-time S&P 500 (survivorship-free).

Source: Eberhart, Maxwell & Siddique (2004) "An Examination of Long-Term
Abnormal Stock Returns and Operating Performance Following R&D Increases",
J. Finance 59(2) 623-650 (doi 10.1111/j.1540-6261.2004.00644.x; SSRN
https://papers.ssrn.com/abstract_id=560043): 8,313 unexpected R&D increases
1951-2001 are followed by significantly positive long-run abnormal stock
returns AND improved operating performance — the market under-reacts to the
benefit of the extra R&D. Sample criteria as restated by the papers that
replicate it (Himmelmann, EFMA 2011, "Systematic risk dynamics following R&D
increases", https://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2011-Braga/papers/0462.pdf;
Bayes/City "Market underestimation of the implications of R&D increases",
https://www.bayes.citystgeorges.ac.uk/__data/assets/pdf_file/0004/86476/1-RD-increase29april2011s.pdf):
R&D/sales >= 5% and R&D/assets >= 5% (economically meaningful R&D), dollar
R&D up >= 5% AND R&D/assets up >= 5% on the prior year.
Ledger: new mechanism — a CHANGE in R&D, not its level (R-2026-11-10-RND
ranks the level RD/ME). The two books overlap only partly: RND favours low
market value; RDINC favours rising research effort regardless of price.

RATIONALE (fixed before any run): an R&D increase is an investment the
accounts treat as a pure cost — it depresses this year's earnings exactly
when the firm is betting most on its future. Investors anchored on earnings
under-react; EMS show the payoff arrives later in operating performance and
returns. Unlike most investment signals (asset growth, capex: CMA says
investing firms earn LESS), R&D increases point the other way, so the FF5
CMA factor cannot absorb it — a real chance at factor alpha (theme 8/20).
Expected failure regime: R&D-sector crashes (2000-02, 2022 biotech) and
empire-building increases at mature firms; the book is tech/pharma-heavy.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the SIGNAL day, priced on it.
  * Trade day: last close of June each year; SIGNAL day = previous trading
    day.
  * Latest ARY row public on/before the signal day (calendardate <= 18
    months old) and the prior fiscal-year row (calendardate 9-15 months
    earlier) — NETISS's two_rows().
  * Event if ALL of: rnd/revenue >= 5%, rnd/assets >= 5% (latest row);
    rnd_t / rnd_{t-1} - 1 >= 5%; (rnd_t/assets_t) / (rnd_{t-1}/assets_{t-1})
    - 1 >= 5%.
  * Hold every event firm, equal weight, drifting until next June. Fewer
    than 10 events -> hold SPY that year (no concentrated book). SPY before
    the first book.
  * Variants (robustness gate): thresholds 3% and 7.5% (all four tests);
    3-year cohorts (hold the union of the last three Junes' event firms,
    because EMS measure 5-year returns); value-weighted by signal-day market
    value.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha
    gate. Family "rnd-increase" (new; related to rnd-intensity, flagged for
    the red team): trials = 1 + 4 = 5.
DATA-TIMING CHECK (theme 21): inputs are dated <= dates[i-1], strictly
before the trade day dates[i]: ARY rows public <= dates[i-1]; DAILY market
value of dates[i-1] (vw variant only); membership and price on dates[i-1].
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
ni = rnd.ni                                           # NETISS two_rows()

ID = "R-2026-11-11-RDINC"
START = rnd.START
BENCH = rnd.BENCH


def is_event(t, sd, th=0.05):
    pair = ni.two_rows(t, sd)
    if not pair:
        return None
    r, p = pair
    n = ag._num
    rd1, rd0, a1, a0, s1 = n(r.get("rnd")), n(p.get("rnd")), n(r.get("assets")), n(p.get("assets")), n(r.get("revenue"))
    if not rd1 or not rd0 or rd1 <= 0 or rd0 <= 0 or not a1 or not a0 or a1 <= 0 or a0 <= 0 or not s1 or s1 <= 0:
        return False
    return (rd1 / s1 >= th and rd1 / a1 >= th and rd1 / rd0 - 1 >= th
            and (rd1 / a1) / (rd0 / a0) - 1 >= th)


def make_weights(th=0.05, cohorts=1, vw=False):
    hist = {}

    def select(dates, i, px):
        sd = dates[i - 1]
        ev = sorted(t for t in ag.members(sd)
                    if t in px and px[t][i - 1] is not None and is_event(t, sd, th))
        hist[dates[i][:4]] = ev
        years = sorted(hist)[-cohorts:]
        names = sorted({t for y in years for t in hist[y] if t in px and px[t][i - 1] is not None})
        if len(names) < 10:
            return {BENCH: 1.0}
        if vw:
            daily = rnd.mcap_on(sd)
            mc = {t: daily.get(t) for t in names if daily.get(t)}
            if len(mc) >= 10:
                tot = sum(mc.values())
                return {t: v / tot for t, v in mc.items()}
        return {t: 1.0 / len(names) for t in names}
    inner = rev.make_annual(select)

    def weights(i, dates, px):
        if i == 0:
            hist.clear()                                 # fresh cohort memory for every simulation
        return inner(i, dates, px)
    return weights


weights = make_weights()
VARIANTS = {"th3": make_weights(0.03), "th75": make_weights(0.075),
            "coh3": make_weights(cohorts=3), "vw": make_weights(vw=True)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="rnd-increase", variants=VARIANTS, source="sharadar",
        notes=("Eberhart-Maxwell-Siddique R&D increases: point-in-time S&P 500 firms with R&D/sales and "
               "R&D/assets >= 5% whose R&D dollars and R&D/assets both rose >= 5% in the latest fiscal year "
               "(ARY public before the signal day), equal weight, each June; SPY if < 10 events; variants "
               "3/7.5% thresholds, 3-year cohorts, value-weighted; survivorship-free"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
