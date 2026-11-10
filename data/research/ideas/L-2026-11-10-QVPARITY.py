"""L-2026-11-10-QVPARITY — lab original: risk parity with the quality-value
book as its equity leg. Equal risk in MAGICSF's book and long Treasuries,
levered to 1.5x gross (KNOWLEDGE.md themes 2, 3, 15, 18, 19).

INGREDIENTS (shortlist first, RESEARCH.md §2b):
  * R-2026-11-07-MAGICSF (potential 3): +14.2%/yr vs SPY +7.6% 2000-24, the
    only honest-data stock book with factor alpha (t 2.8), but -57% worst
    drop and a lost 2017-24 window.
  * R-2026-10-28-RPARL (potential 4): risk parity stocks/bonds/gold at 2x —
    +14.3%/yr vs +9.4%, Sharpe 0.78 vs 0.47 over 20-year windows; breaks when
    stocks and bonds fall together (2022).
  * Theme 13: never trend-GATE value (the gate killed the alpha); "size it
    instead, or pair it with a crisis sleeve held alongside".
  * Theme 19 (QVBOOK, FAIL): the yen/franc sleeve was too SMALL to offset an
    equity crash — "size or a different hedge is the open question".
  * Themes 15/18: the book is saturated; the next gain is sizing/leverage.

RATIONALE (written before any run): the value book's alpha is real but it
comes wrapped in full equity beta and a -57% drawdown. Risk parity answers
theme 19's open question with a hedge that is BIG and ALWAYS ON: long
Treasuries rallied in 2000-02 and 2008 (the value book's worst stretches)
and carry a term premium the rest of the time, so an equal-risk mix keeps
the book's alpha in every rebound (no gate, theme 13) while cutting the
crash. Leverage (1.5x) restores the return that de-risking gives up
(Asness-Frazzini-Pedersen 2012 "Leverage aversion and risk parity", FAJ:
levered low-risk mixes beat unlevered equity-heavy ones per unit of risk).
Expected failure regime, stated before the run: 2022 (stocks and bonds fell
together — RPARL's and HFEA's known break), and 2017-24 (MAGICSF's lag).

RULE (fixed before any run):
  * Equity leg: R-2026-11-07-MAGICSF's book unchanged (imported, own state):
    best 30 of the point-in-time S&P 500 ex Financial Services/Utilities by
    EBIT/EV rank + point-in-time ROIC rank, monthly, equal weight.
  * Bond leg: TLT (20+ year Treasuries).
  * At each month end: sigma_E = stdev of the equity leg's own daily returns
    over the last 63 trading days (computed from the book's past holdings and
    past prices only), sigma_B = stdev of TLT's last 63 daily returns;
    w_E = L * (1/sigma_E) / (1/sigma_E + 1/sigma_B), w_B = L - w_E, L = 1.5;
    held as targets until the next month end (the book's names share w_E in
    the book's own proportions).
  * Before TLT has 63 daily returns (TLT lists 2002-07-30): the book alone at
    100% (equals MAGICSF over 2000-02).
  * Variants (robustness gate): L = 1.25 and 1.75; vol look-back 42 and 126
    days.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault (lab original: the vault
    applies), strict bar + FF5+Mom alpha gate.
  * Family GREENBLATT (same core): lifetime 15 (MAGICSF 5 + QVTREND 5 +
    QVBOOK 5) -> trials 20 if this runs first; the harness takes the larger
    of this and the family's recorded count.
DATA: TLT is an ETF, which Sharadar keeps in its `funds` table, not the
`stocks` (SEP) table that evaluate(source="sharadar") reads (checked
2026-11-10: funds?ticker=TLT has 6,110 rows from 2002-07-30). FETCH routes
only TLT to `funds`, exactly as QVBOOK routes FXY/FXF; side effect: today's
cache file for stocks/TLT holds the funds rows.
COST REALISM: the harness finances gross above 1 at the T-bill rate. Held as
TLT on Schwab margin it would cost more (~+3%/yr on the 0.5 borrowed ->
~1.5%/yr haircut). The realistic implementation holds the Treasury leg as
10-year/bond futures (ZN/ZB, Schwab-tradeable), whose financing IS ~T-bill:
then the harness figure is the right one, minus roll costs. Red team: check
both.
"""
import importlib.util
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("magic", Path(__file__).with_name("R-2026-11-07-MAGICSF.py"))
magic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(magic)

ID = "L-2026-11-10-QVPARITY"
BOND = "TLT"


def FETCH(*a):
    """Polymorphic fetch for evaluate(): 1 arg = Yahoo symbol (tbill),
    2 args = Sharadar (table, params) with TLT routed to `funds`."""
    if len(a) == 1:
        return rb._fetch(a[0])
    table, params = a
    if table == "stocks" and params.get("ticker") == BOND:
        table = "funds"
    return rb._sh_fetch(table, params)


def _sd(x):
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def make(lev=1.5, lb=63):
    base = magic.make()                               # the MAGICSF core, its own state
    st = {}

    def weights(i, dates, px):
        if i == 0:                                    # fresh state for every simulation
            st.update(prev={}, cr=[], br=[], legs=None)
        w = dict(base(i, dates, px) or {})            # core always called -> its state stays current
        if i > 0:
            if st["prev"]:                            # the book's realised return i-1 -> i
                r = 0.0
                for t, x in st["prev"].items():
                    a, b = px[t][i - 1], px[t][i]
                    if a and b:
                        r += x * (b / a - 1)
                st["cr"].append(r)
            bnd = px.get(BOND)
            if bnd is not None and bnd[i] and bnd[i - 1]:
                st["br"].append(bnd[i] / bnd[i - 1] - 1)
        st["prev"] = w
        if i + 1 >= len(dates) or dates[i + 1][:7] != dates[i][:7]:     # month end
            st["legs"] = None
            if len(st["cr"]) >= lb and len(st["br"]) >= lb:
                se, sb = _sd(st["cr"][-lb:]), _sd(st["br"][-lb:])
                if se > 0 and sb > 0:
                    we = lev * (1 / se) / (1 / se + 1 / sb)
                    st["legs"] = (we, lev - we)
        if not w:
            return {}
        bnd = px.get(BOND)
        if st["legs"] is None or bnd is None or not bnd[i]:
            return w                                  # book alone (warm-up)
        we, wb = st["legs"]
        out = {t: x * we for t, x in w.items()}
        out[BOND] = wb
        return out
    return weights


weights = make()
VARIANTS = {"lev125": make(lev=1.25), "lev175": make(lev=1.75),
            "lb42": make(lb=42), "lb126": make(lb=126)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(ID, weights, magic.TICKERS + [BOND], "SPY", start="2000-01-01",
                      asset_class="stocks", source="sharadar", family="GREENBLATT", trials=20,
                      variants=VARIANTS, fetch=FETCH,
                      notes="Lab original: equal-risk MAGICSF book + TLT (63-day inverse vol, monthly), "
                            "1.5x gross financed at T-bills (futures-equivalent); book alone until TLT has "
                            "63 returns; Sharadar survivorship-free (TLT from the funds table); family GREENBLATT")
    print(json.dumps({k: out[k] for k in out if k not in ("equity",)}, indent=1)[:6000])
