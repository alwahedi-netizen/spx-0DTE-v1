"""R-2026-11-09-CMDVALUE — commodity value (5-year spot reversal), long-only ETF form.
PROMOTES ledger row I-2026-11-08-CMDVALUE (same mechanism; update that row's
id/phase, do not add a second row).

Source: Asness, Moskowitz & Pedersen, "Value and Momentum Everywhere", Journal of
Finance 68(3), 2013 (https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf):
commodity value = log of the average spot price 4.5-5.5 years ago divided by
today's spot price; long the cheapest third, short the dearest; value is
negatively correlated with momentum across every asset class. Long-run support:
the 1877-2017 commodity value/momentum/basis long-short premia of 0.9-1.1%/month
summarised by CXO (https://www.cxoadvisory.com/commodity-futures/commodity-futures-strategies-over-the-very-long-run).

Rationale: commodity supply responds to price with a multi-year lag (mines,
acreage, rigs): five years of falling prices starve investment and set up the
next shortage; five years of rising prices bring new supply. Ranking on the
5-year spot change buys the starved markets.

WHY NOW TESTABLE (yesterday's row said "data-thin"): the SIGNAL is a price
LEVEL comparison (today vs ~5 years ago), so Yahoo front-month futures serve as
the spot proxy from 2000 — roll gaps do not matter for a level ratio (they do
for returns, which is why returns come only from the ETFs). The fronts are
loaded on their own calendar and read only on dates <= today (they never enter
the simulated universe, so they cannot distort the ETF calendar).

RULE (fixed before any run; the AMP definition, ledger row's ETF form):
  universe (ETF traded <- front used for the signal):
    GLD<-GC=F  SLV<-SI=F  PPLT<-PL=F  PALL<-PA=F  CPER<-HG=F  USO<-CL=F
    UNG<-NG=F  CORN<-ZC=F  SOYB<-ZS=F  WEAT<-ZW=F  CANE<-SB=F
  at each month-end close i (date D):
    for each name whose ETF has a close at i:
      now  = last front close dated <= D
      past = mean of front closes dated in [D - 5.5y, D - 4.5y] (>= 150 closes)
      value = ln(past / now)
    if >= 6 names have a value: hold the 3 highest-value (cheapest) ETFs,
    1/3 each, next month; else T-bills
Benchmark: buy & hold DBC. Costs 5bp. Start 2006-02-01 (DBC lists 2006-02);
the >= 6-name condition is met from ~2010 (PPLT/PALL 2010-01, CORN 2010-06), so
positions run ~2010 -> vault; 2008 is NOT in the traded sample (caveat), the
2014-16 commodity crash and 2020-22 are.
Known weaknesses stated before the run: long-only drops the short (dear) leg;
11 names make ranks noisy; NG=F's front level is seasonal (winter vs summer
contract) — the 1-year average in `past` damps it but `now` is one day.
Variants: window centred at 4 years (3.5-4.5y) and 6 years (5.5-6.5y); hold the
top 2 / top 4. trials = 5 (new family "cmd-value").
"""
import bisect
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

PAIRS = {"GLD": "GC=F", "SLV": "SI=F", "PPLT": "PL=F", "PALL": "PA=F", "CPER": "HG=F",
         "USO": "CL=F", "UNG": "NG=F", "CORN": "ZC=F", "SOYB": "ZS=F", "WEAT": "ZW=F",
         "CANE": "SB=F"}
UNIV = list(PAIRS)
MIN_NAMES = 6
SIDE = {}          # front -> (sorted dates, closes); filled once, on first use


def _load():
    if not SIDE:
        fronts = sorted(set(PAIRS.values()))
        d, p = rb.prices(fronts, "1999-01-01")
        for f in fronts:
            pts = [(x, v) for x, v in zip(d, p[f]) if v]
            SIDE[f] = ([x for x, _ in pts], [v for _, v in pts])
    return SIDE


def _shift(d, years):
    y, m, dd = (int(x) for x in d.split("-"))
    return (date(y, m, dd) - timedelta(days=round(365.25 * years))).isoformat()


def _value(front, today, centre):
    ds, vs = _load()[front]
    k = bisect.bisect_right(ds, today)            # closes dated <= today only
    if k == 0:
        return None
    now = vs[k - 1]
    lo, hi = _shift(today, centre + 0.5), _shift(today, centre - 0.5)
    a, b = bisect.bisect_left(ds, lo), bisect.bisect_right(ds, hi)
    if b - a < 150 or now <= 0:
        return None
    past = sum(vs[a:b]) / (b - a)
    return math.log(past / now) if past > 0 else None


def make(centre=5.0, top=3):
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        val = {}
        for etf in UNIV:
            if not px[etf][i]:
                continue
            v = _value(PAIRS[etf], dates[i], centre)
            if v is not None:
                val[etf] = v
        if len(val) < MIN_NAMES:
            st["w"] = {}
        else:
            pick = sorted(val, key=lambda s: (-val[s], s))[:top]
            st["w"] = {s: 1.0 / top for s in pick}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"c4y": make(4.0, 3), "c6y": make(6.0, 3), "top2": make(5.0, 2), "top4": make(5.0, 4)}
    res = rb.evaluate("R-2026-11-09-CMDVALUE", weights, UNIV, "DBC", start="2006-02-01",
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="cmd-value", variants=variants,
                      notes="month-end: value = ln(mean front close 4.5-5.5y ago / front close today) "
                            "(Yahoo fronts, signal only); hold the 3 cheapest of 11 commodity ETFs 1/3 each "
                            "when >= 6 have a value, else T-bills; bench DBC; AMP 2013 long-only ETF form; "
                            "promotes I-2026-11-08-CMDVALUE; positions ~2010+ (no 2008)")
    print(json.dumps(res, indent=1))
