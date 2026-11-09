"""L-2026-11-09-QVBOOK — lab original: Greenblatt quality-value held ALWAYS,
plus a safe-haven currency sleeve held ALONGSIDE it in S&P 500 downtrends
(KNOWLEDGE.md combination queue "L-QVBOOK": MAGICSF + SAFEHAVEN/HAVENVOL).

INGREDIENTS (shortlist first, RESEARCH.md §2b):
  * R-2026-11-07-MAGICSF (potential 3): +14.2%/yr vs SPY +7.6% 2000-24,
    factor alpha t 2.8, but -57% worst drop and a lost 2017-24 window.
  * L-2026-11-07-SAFEHAVEN (potential 4): yen + franc (FXY/FXF) only while
    the S&P 500 is below its 10-month SMA — pays in equity crashes with no
    equity beta, flat (cash) most of the time.
  * Theme 13 (L-2026-11-08-QVTREND, FAIL): trend-GATING the value book cut
    the drop (-57% -> -33%) but killed the alpha (t 2.8 -> 0.8), because value
    earns its premium in the rebounds right after a crash, while the trend
    filter is still out. "Do not trend-gate value; size it instead, or pair it
    with a crisis sleeve held alongside."

RATIONALE (written before any run): keep the value book fully invested
through every crash so it captures the rebound premium, and let the trend
signal switch on an ADDITIONAL hedge instead of switching the book off. In
equity bear markets carry trades unwind and the funding currencies (JPY,
CHF) rally against the dollar (Ranaldo-Soderlind 2010), so the sleeve should
pay during the value book's drawdowns (2008: FXY +~20%) and cost little the
rest of the time, when it is not held. The sleeve is an overlay financed at
the T-bill rate (the harness charges T-bills on gross exposure above 1),
which is economically a long JPY/CHF vs USD forward position.

RULE (fixed before any run):
  * Core, always on: R-2026-11-07-MAGICSF's book unchanged — at each month
    end, best 30 of the point-in-time S&P 500 ex Financial Services/Utilities
    by EBIT/EV rank + point-in-time ROIC rank (ART row public <= day), equal
    weight 100% (imported from its script, so the core is identical).
  * Sleeve: at each month end, if SPY's close is below the average of its last
    10 month-end closes, add FXY 25% + FXF 25% (50% overlay) for the next
    month; otherwise no sleeve. FXY lists 2007-02, FXF 2006-06: before both
    have a price the sleeve is skipped.
  * Variants (robustness gate): overlay 25% and 75%; 8- and 12-month SMA.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault (lab original: the vault
    applies), strict bar + FF5+Mom alpha gate.
  * Family GREENBLATT (a variation of the same core): its lifetime count is
    10 (MAGICSF 5 + QVTREND 5) -> trials passed 15; the harness takes the
    larger of this and the family's recorded count.
DATA: FXY/FXF are ETFs, which Sharadar keeps in its `funds` table, not the
`stocks` (SEP) table that evaluate(source="sharadar") reads — a plain run
would see no prices for them (checked: stocks?ticker=FXY returns 0 rows;
funds returns 2006/2007-> history). FETCH below routes only those two tickers
to `funds`; everything else is unchanged (the 1-argument form is the Yahoo
fetch tbill() uses). Side effect: today's cache file for stocks/FXY|FXF holds
the funds rows — correct prices, just under the stocks key.
KNOWN COST REALISM GAP: the overlay is financed at the T-bill rate; a Schwab
margin loan costs more (~+2-5%/yr on the 50% for the ~20% of months held,
i.e. ~0.2-0.5%/yr) — red team should haircut by that.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("magic", Path(__file__).with_name("R-2026-11-07-MAGICSF.py"))
magic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(magic)

ID = "L-2026-11-09-QVBOOK"
HAVENS = ("FXY", "FXF")


def FETCH(*a):
    """Polymorphic fetch for evaluate(): 1 arg = Yahoo symbol (tbill),
    2 args = Sharadar (table, params) with FXY/FXF routed to `funds`."""
    if len(a) == 1:
        return rb._fetch(a[0])
    table, params = a
    if table == "stocks" and params.get("ticker") in HAVENS:
        table = "funds"
    return rb._sh_fetch(table, params)


def make(overlay=0.50, sma_months=10):
    base = magic.make()                               # the MAGICSF core, its own state
    st = {"ends": [], "on": False}

    def weights(i, dates, px):
        if i == 0:
            st.update(ends=[], on=False)              # fresh state for every simulation
        w = dict(base(i, dates, px) or {})            # core is always called -> state stays current
        if i + 1 >= len(dates) or dates[i + 1][:7] != dates[i][:7]:
            st["ends"].append(i)
            spy = px.get("SPY")
            closes = [spy[j] for j in st["ends"][-sma_months:] if spy is not None and spy[j]]
            st["on"] = (spy is not None and bool(spy[i]) and len(closes) == sma_months
                        and spy[i] < sum(closes) / sma_months)
        if st["on"] and all(h in px and px[h][i] for h in HAVENS):
            for h in HAVENS:
                w[h] = w.get(h, 0.0) + overlay / len(HAVENS)
        return w
    return weights


weights = make()
VARIANTS = {"overlay25": make(0.25), "overlay75": make(0.75),
            "sma8": make(sma_months=8), "sma12": make(sma_months=12)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(ID, weights, magic.TICKERS + list(HAVENS), "SPY", start="2000-01-01",
                      asset_class="stocks", source="sharadar", family="GREENBLATT", trials=15,
                      variants=VARIANTS, fetch=FETCH,
                      notes="Lab original: MAGICSF book always 100% + FXY/FXF 25%/25% overlay while SPY < "
                            "10-month SMA (theme 13: hedge alongside, never gate value); Sharadar "
                            "survivorship-free (FXY/FXF from the funds table); family GREENBLATT")
    print(json.dumps({k: out[k] for k in out if k not in ("equity",)}, indent=1)[:6000])
