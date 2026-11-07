"""R-2026-11-07-FOMCUSD — short the dollar on scheduled FOMC decision days.

SOURCE: Mueller, Tahbaz-Salehi & Vedolin, "Exchange Rates and Monetary Policy
Uncertainty", Journal of Finance 72(3), 2017
(https://econpapers.repec.org/RePEc:ehl:lserod:77256): a short-USD / long-G10
basket earns ~14.5bp on FOMC announcement days vs ~1.7bp on other days — a
premium for monetary-policy uncertainty. Independent replication: QuantSeeker
"The FOMC-day puzzle: why every G10 currency..." (2025-12-11,
https://www.quantseeker.com/p/the-fomc-day-puzzle-why-every-g10): 1992-2025
daily spot, every G10 currency appreciates vs USD on average on FOMC days;
mostly a post-2000 effect.

RATIONALE: uncertainty about the Fed's decision is resolved on the day; the
dollar carries a premium that is paid to whoever is short it into the
announcement. Not the same bet as R-2026-11-07-PREFOMC (equity drift before the
statement, which faded after 2015): this is the dollar leg, earned through the
statement, on a different asset and driver — whether it decayed too is the
question.

RULE (fixed before any run, trials=1 + 4 window variants):
  * Decided at the close of the bar BEFORE each scheduled FOMC decision day:
    long an equal-weighted basket of the nine G10 currencies vs USD (EUR, GBP,
    AUD, NZD, JPY, CHF, CAD, SEK, NOK; whichever have prices), gross 1.0,
    held for the decision day's bar only; otherwise all cash (T-bills).
  * Long a USD-quoted pair (USDJPY=X etc.) = weight -1/n on the pair (first-
    order equal to long the currency).
  * FOMC dates = the scheduled-decision list already in the ledger
    (R-2026-11-07-PREFOMC.py, from federalreserve.gov), loaded from that file.
  * DATE FIX: Yahoo FX daily bars are stamped 23:00 UTC of the PREVIOUS day
    while the UK is on summer time (research_bt turns the stamp into a UTC
    date), so a bar labelled L between the last Sunday of March and the last
    Sunday of October is the London trading day L+1. The rule maps each label
    to its true day before matching FOMC dates. The bar closes ~midnight
    London, i.e. after the 14:00 ET statement.
  * Variants (neighbouring windows): PRE (day before + decision day), POST
    (decision day + day after), WIDE (-1..+1), PRE2 (-2..0).
Benchmark: T-bills (an 8-days-a-year strategy is judged on its own Sharpe).
asset_class="fx" (2bp), Yahoo spot pairs 2004+ (USD pairs start 2003-12;
AUDUSD 2006-05). Data note: spot only — no interest on the legs, which is
immaterial for one-day holds.
"""
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "prefomc", Path(__file__).resolve().parent / "R-2026-11-07-PREFOMC.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FOMC = set(_mod.FOMC)

# currency -> (yahoo symbol, sign of the weight that is LONG the currency)
LEGS = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "AUD": ("AUDUSD=X", 1),
        "NZD": ("NZDUSD=X", 1), "JPY": ("USDJPY=X", -1), "CHF": ("USDCHF=X", -1),
        "CAD": ("USDCAD=X", -1), "SEK": ("USDSEK=X", -1), "NOK": ("USDNOK=X", -1)}
SYMS = [s for s, _ in LEGS.values()]


def _last_sunday(y, m):
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def true_day(label):
    """Yahoo FX bar label (UTC date of the stamp) -> London trading day."""
    d = date.fromisoformat(label)
    if _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10):
        d += timedelta(days=1)
    return d.isoformat()


def make(offsets):
    """Hold the basket over bar k when true_day(bar k) is an FOMC day + o, o in offsets."""
    fomc_dates = sorted(date.fromisoformat(x) for x in FOMC)
    hold_days = set()               # offsets are in weekdays (FX trades Mon-Fri)
    for d in fomc_dates:
        for o in offsets:
            x, step = d, (1 if o > 0 else -1)
            for _ in range(abs(o)):
                x += timedelta(days=step)
                while x.weekday() >= 5:
                    x += timedelta(days=step)
            hold_days.add(x.isoformat())

    def weights(i, dates, px):
        if i + 1 >= len(dates) or true_day(dates[i + 1]) not in hold_days:
            return {}
        live = [(s, sg) for s, sg in LEGS.values() if px[s][i]]
        if not live:
            return {}
        return {s: sg / len(live) for s, sg in live}
    return weights


weights = make([0])

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-FOMCUSD", weights, SYMS, None, start="2004-01-01",
                    asset_class="fx", trials=1, family="fx-fomc-dollar",
                    variants={"PRE": make([-1, 0]), "POST": make([0, 1]),
                              "WIDE": make([-1, 0, 1]), "PRE2": make([-2, -1, 0])},
                    notes="long equal-weight G10 basket vs USD on the scheduled FOMC decision-day bar "
                          "(Yahoo BST label shift corrected), else T-bills; 2004+; spot pairs; "
                          "variants = holding windows")
    print(json.dumps(r, indent=1))
