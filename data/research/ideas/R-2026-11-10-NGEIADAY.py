"""R-2026-11-10-NGEIADAY — the natural-gas announcement-day premium, ETF form
(Prokopczuk, Wese Simen & Wichmann 2021). New sourced idea, scripted the day it
was scored.

Source: Marcel Prokopczuk, Chardin Wese Simen & Robert Wichmann, "The Natural
Gas Announcement Day Puzzle", The Energy Journal 42(2), 2021, 91-112
(https://ideas.repec.org/a/aen/journl/ej42-2-wichmann.html ; working paper
https://centaur.reading.ac.uk/90003/): more than 50% of the annual return of
natural-gas futures is earned on the weekly EIA storage-report day (Thursday
10:30 ET since 2002); standard risk explanations do not account for it; a
simple announcement-day strategy earns substantial returns after transaction
and funding costs; the authors note the anomaly has shrunk recently. Related:
the crude-oil EIA intraday row I-2026-11-08-EIAINTRA (different market,
intraday) — not the same mechanism.

Rationale (the paper's, hedged): an announcement-risk premium — holders of
gas exposure through the storage release bear a concentrated, unhedgeable
information shock (gas is the most inventory-sensitive major commodity), and
they are paid for it on that day, not on the quiet days. Under that reading
gas futures earn ~nothing (or lose to contango) on other days.

RULE (fixed before any run):
  at each daily close i: if the NEXT trading day dates[i+1] is a Thursday,
  hold 100% UNG over close i -> close i+1 (i.e. Wednesday close to Thursday
  close, which spans the 10:30 ET release); otherwise T-bills.
  Reading dates[i+1]'s weekday reads the exchange CALENDAR, never a price
  (the calendar is published in advance; same convention as every month-end
  rule in the ledger).
Benchmark: T-bills (bench=None), NOT UNG — and why: UNG lost ~99% from 2007 to
2024 to the gas glut and contango roll, so ANY mostly-flat UNG rule beats it
on Sharpe; the paper's claim is that announcement days carry a POSITIVE
premium, so the honest yardstick is cash. A NO-VERDICT diagnostic prints UNG
buy & hold and UNG's mean return by weekday.
Costs 5bp per unit of turnover: ~104 units a year (in and out every week),
i.e. ~5%/yr of drag — the rule must clear it.
History: UNG 2007-04-18+ (start 2007-05-01). Includes 2008, the 2009-20 glut,
2021-22 spike, 2023 collapse.
Variants (neighbours): window Wed+Thu (enter Tuesday close); window Thu+Fri;
the 12-month ladder UNL instead of UNG (less roll noise; T-bills until UNL
lists 2009-11); Thursdays only in full 5-day weeks (holiday weeks move the
EIA release). New family "ng-announcement" -> trials 5.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

START = "2007-05-01"
_WD = {}


def _wd(d):
    if d not in _WD:
        _WD[d] = date.fromisoformat(d).weekday()      # Mon 0 .. Fri 4
    return _WD[d]


def _full_week(dates, k):
    """Calendar only: True if dates[k]'s Mon-Fri week has 5 trading days."""
    y, w, _ = date.fromisoformat(dates[k]).isocalendar()
    n, j = 0, k
    while j >= 0 and date.fromisoformat(dates[j]).isocalendar()[:2] == (y, w):
        n, j = n + 1, j - 1
    j = k + 1
    while j < len(dates) and date.fromisoformat(dates[j]).isocalendar()[:2] == (y, w):
        n, j = n + 1, j + 1
    return n == 5


def make(days=(3,), sym="UNG", full_weeks_only=False):
    def weights(i, dates, px):
        if i + 1 >= len(dates) or _wd(dates[i + 1]) not in days or not px[sym][i]:
            return {}
        if full_weeks_only and not _full_week(dates, i + 1):
            return {}
        return {sym: 1.0}
    return weights


weights = make()


def weekday_report(start=START):
    """Diagnostic only (no verdict, no trial): UNG mean return by weekday of the
    return day, and UNG buy & hold, on development data."""
    dates, px = rb.prices(["UNG", "UNL"], start)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, p = dates[:keep], px["UNG"][:keep]
    rf = rb.tbill(dates)
    by = {k: [] for k in range(5)}
    allr = []
    for i in range(len(dates) - 1):
        if p[i] and p[i + 1]:
            r = p[i + 1] / p[i] - 1
            by[_wd(dates[i + 1])].append(r)
            allr.append(r)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    out = {names[k]: {"n": len(v), "mean_bp": round(1e4 * sum(v) / max(len(v), 1), 2)} for k, v in by.items()}
    out["UNG_buy_hold"] = {"cagr": round(rb.cagr(allr), 4), "sharpe": round(rb.sharpe(allr, rf[1:len(allr) + 1]), 3)}
    return out


if __name__ == "__main__":
    variants = {"wedthu": make((2, 3)), "thufri": make((3, 4)), "unl": make((3,), "UNL"),
                "fullweeks": make((3,), "UNG", True)}
    res = rb.evaluate("R-2026-11-10-NGEIADAY", weights, ["UNG", "UNL"], None, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="ng-announcement", variants=variants,
                      notes="daily: hold UNG Wednesday close -> Thursday close (EIA storage report day), "
                            "else T-bills; bench T-bills (UNG's -99% decay makes it a trivial yardstick); "
                            "Prokopczuk-Wese Simen-Wichmann EJ 2021")
    res["weekday_diagnostic"] = weekday_report()
    print(json.dumps(res, indent=1))
