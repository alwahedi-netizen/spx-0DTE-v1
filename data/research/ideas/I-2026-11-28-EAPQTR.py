"""I-2026-11-28-EAPQTR — the earnings-announcement premium with QUARTERLY
releases (Frazzini & Lamont 2007 construction), point-in-time S&P 500, true
release dates (Sharadar 8-K item 2.02). Variant of R-2026-11-28-EAPANN.

VARIES R-2026-11-28-EAPANN (same family, same hypothesis): every quarterly
release instead of the annual one only. Why the difference matters: annual
releases bunch in Jan-Feb for December year-ends, so EAPANN's long leg is thin
(or empty: < 10 firms -> T-bills) in most months; with quarterly releases every
month has a balanced book, so the same premium is measured with ~3x the
announcer-months (power) — the construction of the ORIGINAL source.
SOURCE: Frazzini, A. & Lamont, O. (2007), "The earnings announcement premium
and trading volume", NBER w13090 (https://www.nber.org/papers/w13090):
buying stocks expected to announce in the coming month and shorting the rest
earned > 60bp/month, CRSP/Compustat 1972-2004, strongest in large caps; a firm
is predicted to announce in month t if it announced in month t-12 (the paper
also uses t-3). Their window ends before our 8-K dates start (2004-10), so the
replication is EAPANN's gate on Barber et al. (2013, US 1991-2010), which
overlaps 2005-11 .. 2010-12. THIS SCRIPT RUNS ONLY IF THAT GATE IS MET.
RATIONALE (fixed before any run): as EAPANN — attention/price pressure and
priced announcement risk in the release month, predictable a year ahead, so
the long/short book is nearly orthogonal to FF5+Mom; a market-neutral sleeve
for the book. Expected failure regime: decay after announcement calendars
became free and machine-readable (theme 4); crash months when the short leg
(two thirds of the index) rebounds harder than announcers.

RULE (fixed before any run):
  * Announcements as in EAPANN: per ARQ row (reportperiod R), the first 8-K
    with event code 22 in (R, R + 100 days]; usable on decision day D only if
    its ARQ row is public (`date` <= D).
  * Decision day D = dates[i-1]; trade at the close of dates[i] = the last
    trading day of month t-1; hold through month t.
  * Universe: point-in-time S&P 500 members on D priced on dates[i-1] and
    dates[i], with >= 2 usable announcements dated in months t-12 .. t-3
    (data coverage: a firm missing from the 8-K feed is left out rather than
    counted as a non-announcer).
    Expected ANNOUNCER if it has a usable announcement dated in month t-12;
    otherwise NON-ANNOUNCER.
  * Book: long announcers +1.0 total, short non-announcers -1.0 total,
    value-weighted by market cap on D (EAPANN's mcap), drifting inside the
    month, re-formed at each month's last close; < 10 firms in either leg ->
    T-bills that month. Gross 2.0, net 0; short proceeds earn T-bills.
  * Variants (robustness gate): equal weight; >= 20 firms per leg; predictor
    t-3 instead of t-12 (FL's alternative); announcer only if BOTH t-12 and
    t-3 announcements are present.
  * Benchmark T-bills, 5bp per unit of turnover (expected ~35-45 units/yr:
    the long third of the index rotates every month), 2005-09 -> vault, first
    held month 2005-11 (EAPANN's FIRST_MONTH: the 8-K feed is fully covered
    from mid-October 2004), strict bar + FF5+Mom factor-alpha gate.
  * family "earnings-announcement-premium": the harness adds EAPANN's 5;
    passed trials = 5 (RNDEAP) + 5 (EAPANN) + 1 + 4 = 15.
PASS CRITERION (written before any run): EAPANN's replication gate met AND
harness verdict PASS vs T-bills with every world-class gate (99% confidence,
held-out last 30% Sharpe beats T-bills with positive return, DSR >= 0.95 at 15
trials, active t >= 3, 2x costs, >= 70% of variants beat T-bills, FF5+Mom
alpha t >= 2). A PASS goes to the lead's red team, then ONE vault test for the
family (run by the lead; never vault=True here).

DATA-TIMING: the book for month t is decided from dates[i-1] (the day before
the trade day dates[i], the last close of month t-1): membership, prices and
market caps of dates[i-1], 8-K dates in months t-12 .. t-3 (all before
dates[i]) and ARQ rows public <= dates[i-1]. No price, filing or event on or
after the trade day is read. Weights decided at close i earn close i -> close
i+1 (harness).
Run AFTER R-2026-11-28-EAPANN on the same UTC day (shared Sharadar cache).
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("eapann_core", _here.with_name("R-2026-11-28-EAPANN.py"))
ea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ea)    # announcements(), mindex(), make_weights(), replication(), universe()

ID = "I-2026-11-28-EAPQTR"
START = ea.START
FAMILY = ea.FAMILY
TRIALS = 5 + 5 + 1 + 4


def quarterly(pred=(12,)):
    """Classifier: True if usable announcements exist in every month t-k
    (k in pred), False otherwise; None if < 2 usable in months t-12 .. t-3."""
    def classify(t, sd, tm):
        ms = {ea.mindex(e) for e, _, pub in ea.announcements(t) if pub <= sd}
        if sum(1 for x in ms if tm - 12 <= x <= tm - 3) < 2:
            return None
        return all(tm - k in ms for k in pred)
    return classify


weights = ea.make_weights(quarterly())
VARIANTS = {"ew": ea.make_weights(quarterly(), vw=False),
            "min20": ea.make_weights(quarterly(), min_leg=20),
            "pred_t3": ea.make_weights(quarterly((3,))),
            "pred_t12_and_t3": ea.make_weights(quarterly((12, 3)))}


if __name__ == "__main__":
    tick = ea.universe()
    rep = ea.replication(tick, lambda log: ea.make_weights(ea.annual(), log=log))
    print("EAPANN REPLICATION", json.dumps(rep))
    if not rep["replicated"]:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "R-2026-11-28-EAPANN did not replicate; variant not tested, no trial spent",
                          "replication": rep}))
        sys.exit(0)
    out = rb.evaluate(
        ID, weights, tick, None, start=START, asset_class="stocks", trials=TRIALS,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Frazzini-Lamont earnings-announcement premium, quarterly: PIT S&P 500; expected announcer "
               "in month t = a release (first 8-K item 2.02 within 100 days of an ARQ reportperiod) in "
               "month t-12; covered firms need >= 2 releases in t-12..t-3; long announcers +1 / short "
               "non-announcers -1, value-weighted, monthly, drifting; >= 10 per leg else T-bills; signal day "
               "= day before trade; bench T-bills; variants EW, min 20, predictor t-3, t-12 AND t-3; trials 15 "
               f"(RNDEAP 5 + EAPANN 5 + 5); EAPANN replication mean {rep['mean_monthly_ls']}/month "
               f"(t {rep['t']})"))
    out["replication_eapann"] = rep
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
