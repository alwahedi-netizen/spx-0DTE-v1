"""R-2026-11-11-DOLCARRY — dollar carry: long the G10 basket vs USD when the
average foreign short rate is above the US rate, long USD when it is below
(Lustig, Roussanov & Verdelhan). Promotes ledger row I-2026-11-07-DOLCARRY
(replace that row); also carries the queued I-2026-11-08-HEDGECARRY in its
only harness-correct form (variant HUSD, see below).

SOURCE: Lustig, Roussanov & Verdelhan, "Countercyclical Currency Risk Premia",
Journal of Financial Economics 111(3) 2014, 527-553 (NBER w16427,
https://www.nber.org/papers/w16427): "the average forward discount" (AFD) of a
basket of developed currencies vs USD predicts the basket's excess return;
the dollar carry trade goes long all foreign currencies when AFD > 0 and
short them when AFD < 0. Developed-country version Sharpe ~0.5 (1983-2010),
near-zero correlation with HML-carry.
HEDGECARRY source: Castro, Hamill, Harber, Harvey & Van Hemert, "Hedging
currency risk" JPM 2025 (via https://quantpedia.com/the-best-strategies-for-fx-hedging/):
hedge a foreign currency only when its rate is below the home rate.

RATIONALE (written before any run): when US rates are low relative to the
world the US is typically in a downturn and the dollar carries a
counter-cyclical risk premium: foreign currencies are expected to earn more
than the rate gap. Holding the high-rate side of the dollar also earns the
rate gap itself (futures roll). The signal is slow (monthly, rate levels), so
costs are negligible.

RULE (fixed before any run):
  * Rates: FRED / OECD 3-month interbank IR3TIB01xxM156N, monthly, for
    AU CA CH EZ GB JP NO NZ SE and US.
  * At each month-end close of month m use the value for month m-2
    (publication lag: on 2026-11-10 the latest AU value was 2026-08; a
    missing value -> latest earlier month, up to 6 back).
  * AFD = equal-weight mean of available foreign rates - US rate.
  * AFD > +band -> UDN 100% (long the DXY basket vs USD, futures-backed);
    AFD < -band -> UUP 100% (long USD vs the DXY basket); else T-bills.
    Base band = 0. The chosen ETF must have a price that day, else T-bills.
  * Variants (4):
      DXYW  - AFD weighted by DXY weights (EZ .576 JP .136 GB .119 CA .091
              SE .042 CH .036, renormalised over available) - the basket the
              instruments actually hold.
      HUSD  - HEDGECARRY at basket level: UUP 100% when the DXY-weighted
              AFD < 0, else T-bills (the hedge overlay's return measured
              standalone, as L-2026-11-09-HEDGEUUP did for the trend hedge;
              per-slice hedges need short legs the harness cannot fund).
      BAND50 - band 0.50 (cash when |AFD| <= 0.50).
      LAG3  - rates from month m-3.
Benchmark: T-bills (bench None). asset_class="fx" (2bp). Start 2007-03-01
(UUP lists 2007-03-01, UDN 2007-02-20).
DATA TIMING: rates are monthly averages read with a 2-month lag (no
look-ahead, slightly stale); UUP/UDN are US closes and the decision is made
at the month-end close and earns from the next bar - no Yahoo `=X` series
is used, so the start-of-day `=X` dating issue (KNOWLEDGE themes 17/21) does
not arise. OECD interbank rates are not revised in practice (market rates).
INSTRUMENTS: UUP / UDN hold USD-index futures with T-bill collateral, so
their total return = T-bill + spot dollar move + the US-minus-basket rate gap
- fee (0.75-0.78%): a funded long, harness-correct (no short legs).
MISMATCH on the record: the signal averages 9 currencies; the instruments
hold the 6-currency DXY basket (58% EUR) - DXYW aligns them. 2007-24 holds
few regime switches (US above the average ~2007-08 and ~2017-24; below
2009-16), so the test leans on a handful of long stretches.
FAMILY "fx-dollar-carry" (new) -> trials 5.
DATA SOURCES: Yahoo (UUP, UDN) + FRED fredgraph.csv (10 series), fetched at
run time and cached in data/research/cache/fred_<id>.json (git-ignored).
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYMS = ["UUP", "UDN"]
FOREIGN = ["AU", "CA", "CH", "EZ", "GB", "JP", "NO", "NZ", "SE"]
DXYW = {"EZ": 0.576, "JP": 0.136, "GB": 0.119, "CA": 0.091, "SE": 0.042, "CH": 0.036}
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def fred(sid):
    """FRED series as {date: float}, cached per day. FRED tarpits unknown
    User-Agents: use the default Python-urllib agent, then curl's."""
    f = rb.CACHE / f"fred_{sid}.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == today:
            return j["v"]
    rows, err = None, None
    for hdr in ({}, {"User-Agent": "curl/8.5.0"}):
        try:
            req = urllib.request.Request(FRED + sid, headers=hdr)
            rows = urllib.request.urlopen(req, timeout=30).read().decode().strip().splitlines()[1:]
            break
        except Exception as e:          # noqa: BLE001 - retry with the other agent
            err = e
    if rows is None:
        raise err
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": today, "v": v}))
    return v


def load_rates():
    """{country: {'YYYY-MM': rate}} for the 9 foreign countries + US."""
    return {c: {d[:7]: x for d, x in fred(f"IR3TIB01{c}M156N").items()} for c in FOREIGN + ["US"]}


def _month_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _rate(series, ym):
    for k in range(7):
        v = series.get(_month_back(ym, k))
        if v is not None:
            return v
    return None


def afd(rates, ym, weighted):
    us = _rate(rates["US"], ym)
    if us is None:
        return None
    if weighted:
        got = {c: _rate(rates[c], ym) for c in DXYW}
        got = {c: r for c, r in got.items() if r is not None}
        tw = sum(DXYW[c] for c in got)
        return sum(DXYW[c] * r for c, r in got.items()) / tw - us if tw else None
    got = [r for r in (_rate(rates[c], ym) for c in FOREIGN) if r is not None]
    return sum(got) / len(got) - us if got else None


def make(band=0.0, lag=2, weighted=False, short_leg=True, rates=None):
    rates = rates if rates is not None else load_rates()
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                              # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        a = afd(rates, _month_back(dates[i][:7], lag), weighted)
        pick = None
        if a is not None and a > band and short_leg:
            pick = "UDN"
        elif a is not None and a < -band:
            pick = "UUP"
        st["w"] = {pick: 1.0} if pick and px[pick][i] else {}
        return st["w"]
    return weights


if __name__ == "__main__":
    R = load_rates()
    r = rb.evaluate("R-2026-11-11-DOLCARRY", make(rates=R), SYMS, None, start="2007-03-01",
                    asset_class="fx", trials=5, family="fx-dollar-carry",
                    variants={"DXYW": make(weighted=True, rates=R),
                              "HUSD": make(weighted=True, short_leg=False, rates=R),
                              "BAND50": make(band=0.50, rates=R),
                              "LAG3": make(lag=3, rates=R)},
                    notes="Lustig-Roussanov-Verdelhan dollar carry: month-end, AFD = mean OECD 3m rate "
                          "(9 G10, month m-2) - US; AFD>0 -> UDN, AFD<0 -> UUP; bench T-bills. "
                          "Variant HUSD = HEDGECARRY basket form (UUP or cash)")
    print(json.dumps(r, indent=1))
