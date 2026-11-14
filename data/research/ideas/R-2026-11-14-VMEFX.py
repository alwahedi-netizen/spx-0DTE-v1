"""R-2026-11-14-VMEFX — REPLICATION: currency value + momentum 50/50 (Asness,
Moskowitz & Pedersen 2013) on carry-inclusive returns, checked month by month
against the SOURCE'S OWN published, updated factor series (AQR "Value and
Momentum Everywhere: Factors, Monthly", columns VALLS_VME_FX / MOMLS_VME_FX).

This is the careful retest of R-2026-11-09-VALMOMFX (and of its value leg
R-2026-11-07-FXVALUE) that KNOWLEDGE theme 28 asks for: after harness fix 2
(Yahoo `=X` relabelled to true closes; short proceeds earn T-bills) FXVALUE
moved 28% -> 71% and VALMOMFX 17% -> 51%. Two things were still wrong with
those runs and are fixed here, nothing else:
  1. Returns: AMP use currency FORWARD excess returns (spot move + interest
     differential). Spot pairs earn no foreign interest, so the old runs
     missed every leg's carry. Here each currency is a synthetic deposit
     index TR_<ccy> = USD price of the currency x compounded OECD 3-month
     interbank rate of that country (FRED IR3TIB01xxM156N). Holding w of it
     in research_bt earns w x (spot + r_ccy - r_US) on top of T-bills, which
     is exactly the forward excess return; a short pays r_ccy and its
     proceeds earn T-bills (fix 2).
  2. Momentum is ranked on those excess returns (AMP), not on spot.
Value stays NOMINAL (no CPI): FRED's OECD CPI for Japan ends 2021-06, so the
true PPP adjustment cannot be built point-in-time for the whole window; this
is the one known difference from the source and is stated up front.

SOURCE: Asness, Moskowitz & Pedersen, Journal of Finance 68(3) 2013,
https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf (paper
period 1979-2011: FX VAL+MOM 50/50 Sharpe 0.69 in AQR's current file).
Published UPDATED series (same definitions, rebuilt monthly by AQR):
https://www.aqr.com/Insights/Datasets/Value-and-Momentum-Everywhere-Factors-Monthly
(file: https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Value-and-Momentum-Everywhere-Factors-Monthly.xlsx).
In that file, over OUR overlap 2009-06 .. 2024-10 (185 months): FX VAL Sharpe
-0.10, FX MOM -0.08, 50/50 -0.17 (corr VAL/MOM -0.51). The source's paper
period cannot be replicated (Yahoo `=X` start 2003-12, value needs 5.5 years),
so the replication target is the source's own series on the overlap.

HYPOTHESIS (written before any run): with carry-inclusive returns our G10
construction reproduces the source's published FX value+momentum series on
2009-06 .. 2024-10 — i.e. the harness and the `=X` data are now right for FX
long/short designs — AND, if it does, the 50/50 premium is ~zero in this
window in the source's own data, so the fx-value family is closed rather
than mined with more variants.

PASS CRITERION (pre-registered, two separate questions):
  A. REPLICATION (the question this script exists for): over the months
     2009-06 .. 2024-10 in which the book holds positions, the monthly excess
     return of our 50/50 book correlates >= 0.50 with AQR's 0.5*VAL + 0.5*MOM
     FX series, AND our annualised Sharpe of those monthly excess returns is
     within +/- 0.30 of AQR's over the same months. Both -> "replicated";
     else "harness/data suspect" (log it and test no fx-value variant).
  B. STRATEGY: the research_bt verdict vs T-bills (§4 + world-class gates).
     Pre-stated expectation: FAIL (the source's own Sharpe is negative here;
     t >= 3 over ~15 years needs Sharpe ~0.76).
DATA-TIMING: signals read only month-end bar i (the last trading day of the
month). Spot `=X` values are true closes after fix 2 (each value relabelled
to the previous bar's date). Value = ln(mean USD price over bars dated 5.5 to
4.5 years before bar i / USD price at bar i). Momentum = ln of TR at the
month-end one month back over TR 12 month-ends back (skip the latest month),
minus the same for TR_USD. The carry accrual on bar k-1 -> k uses the OECD
monthly rate for the calendar month BEFORE bar k's month (a past value; it
stands in for the forward points known at the trade, and is never a signal
input). Weights decided at close i earn close i -> close i+1.
RULE (fixed before any run; AMP rank weights as in FXVALUE):
  * Universe: EUR GBP AUD NZD JPY CHF CAD SEK NOK + USD (score 0).
  * Each leg: rank weights incl. USD, sum|w| = 1, USD weight dropped; held one
    month. Book = 0.5 value + 0.5 momentum, only when both legs exist (else
    T-bills). Value 5y centre, momentum 12-1.
  * Variants (as VALMOMFX): V4, V6 (value centre years), M9, M15 (momentum).
Benchmark T-bills; asset_class "fx" (2bp); start 2003-12-01; positions from
~2009-06. FAMILY "fx-value" (FXVALUE, VALTREND, VALMOMFX: 30 trials in the
results files) -> this run 35. Never vault.
DATA: Yahoo `=X` (via research_bt), FRED fredgraph.csv (10 OECD 3m rates),
AQR xlsx — all cached in data/research/cache/ (git-ignored). The diagnostics
re-simulate the SAME book on the SAME data only to build its monthly series
for the correlation; they print no performance of any other rule.
"""
import bisect
import json
import math
import re
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-14-VMEFX"
START = "2003-12-01"
OVERLAP = ("2009-06", "2024-10")
# currency: (Yahoo pair, sign: +1 if quoted USD per unit of ccy), FRED code, day count
CCY = {"EUR": ("EURUSD=X", 1, "EZ", 360), "GBP": ("GBPUSD=X", 1, "GB", 365),
       "AUD": ("AUDUSD=X", 1, "AU", 365), "NZD": ("NZDUSD=X", 1, "NZ", 365),
       "JPY": ("USDJPY=X", -1, "JP", 360), "CHF": ("USDCHF=X", -1, "CH", 360),
       "CAD": ("USDCAD=X", -1, "CA", 365), "SEK": ("USDSEK=X", -1, "SE", 360),
       "NOK": ("USDNOK=X", -1, "NO", 360)}
SPOT = [v[0] for v in CCY.values()]
TR = {c: f"TR_{c}" for c in CCY}
TR_USD = "TR_USD"
SYMS = SPOT + list(TR.values()) + [TR_USD]
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
AQR_VME = ("https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/"
           "Value-and-Momentum-Everywhere-Factors-Monthly.xlsx")


# ── data helpers (FRED as in L-2026-11-10-OECDCARRY) ─────────────────────────
def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fred(sid):
    f = rb.CACHE / f"fred_{sid}.json"
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == _today():
            return j["v"]
    rows, err = None, None
    for hdr in ({}, {"User-Agent": "curl/8.5.0"}):
        try:
            req = urllib.request.Request(FRED + sid, headers=hdr)
            rows = urllib.request.urlopen(req, timeout=30).read().decode().strip().splitlines()[1:]
            break
        except Exception as e:          # noqa: BLE001 — retry with the other agent
            err = e
    if rows is None:
        raise err
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d[:7]] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": _today(), "v": v}))
    return v


def month_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def rate_for(series, ym):
    """value for month ym, else the latest earlier month (up to 6 back)."""
    for k in range(7):
        v = series.get(month_back(ym, k))
        if v is not None:
            return v
    return None


def _days(d0, d1):
    return (date.fromisoformat(d1) - date.fromisoformat(d0)).days


def deposit_index(dates, usd_px, rates, basis):
    """USD value of 1 unit of currency held on deposit: USD price x
    compounded deposit rate. Accrual on bar k-1 -> k uses the rate of the
    month before bar k's month. usd_px None -> None (no index that day)."""
    out, acc, prev = {}, 1.0, None
    for d, p in zip(dates, usd_px):
        if prev is not None:
            r = rate_for(rates, month_back(d[:7], 1))
            if r is not None:
                acc *= 1 + r / 100 * _days(prev, d) / basis
        prev = d
        if p:
            out[d] = p * acc
    return out


def build_synthetic():
    """{symbol: {date: value}} for TR_<ccy> and TR_USD on the spot calendar."""
    dates, px = rb.prices(SPOT, "1990-01-01")
    out = {}
    for c, (sym, sg, code, basis) in CCY.items():
        usd = [(v if sg > 0 else 1.0 / v) if v else None for v in px[sym]]
        out[TR[c]] = deposit_index(dates, usd, fred(f"IR3TIB01{code}M156N"), basis)
    first = min(min(v) for v in out.values() if v)
    out[TR_USD] = deposit_index([d for d in dates if d >= first],
                                [1.0] * sum(1 for d in dates if d >= first),
                                fred("IR3TIB01USM156N"), 360)
    return out


_SYN = {}


def fetch(sym):
    if sym in TR.values() or sym == TR_USD:
        if not _SYN:
            _SYN.update(build_synthetic())
        return _SYN[sym]
    return rb._fetch(sym)


# ── the rule ─────────────────────────────────────────────────────────────────
def rank_weights(scores):
    """AMP rank weights: {ccy: s} incl. USD -> {ccy: w}, sum|w| = 1."""
    names = sorted(scores, key=lambda c: scores[c])
    n = len(names)
    mean = (n + 1) / 2
    raw = {c: (r + 1) - mean for r, c in enumerate(names)}
    tot = sum(abs(v) for v in raw.values())
    return {c: v / tot for c, v in raw.items()} if tot else {}


def _shift(d, years):
    return (date.fromisoformat(d) - timedelta(days=int(round(years * 365.25)))).isoformat()


def usd_price(px, c, k):
    sym, sg = CCY[c][0], CCY[c][1]
    v = px[sym][k]
    return None if not v else (v if sg > 0 else 1.0 / v)


def value_scores(i, dates, px, st, center_years):
    lo_y, hi_y = center_years + 0.5, center_years - 0.5
    a = bisect.bisect_left(dates, _shift(dates[i], lo_y), 0, i + 1)
    b = bisect.bisect_right(dates, _shift(dates[i], hi_y), 0, i + 1)
    scores = {"USD": 0.0}
    for c in CCY:
        sym = CCY[c][0]
        now = usd_price(px, c, i)
        if sym not in st["first"] and now:
            st["first"][sym] = next(k for k in range(0, i + 1) if px[sym][k])
        first = st["first"].get(sym)
        if not now or first is None or first > a:
            continue
        past = [p for p in (usd_price(px, c, k) for k in range(a, b)) if p]
        if len(past) > 100:
            scores[c] = math.log((sum(past) / len(past)) / now)
    return scores


def make(value_years=5.0, mom_months=12, legs=("value", "momentum")):
    """legs: which legs the book holds (the diagnostics build one-leg books
    ONLY to correlate them with AQR's matching column; never evaluated)."""
    st = {"w": {}, "me": [], "first": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"], st["first"] = {}, [], {}   # evaluate() re-simulates
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        st["me"].append({s: px[s][i] for s in list(TR.values()) + [TR_USD]})
        books = {}
        if "value" in legs:
            sc = value_scores(i, dates, px, st, value_years)
            if len(sc) >= 4:
                books["value"] = rank_weights(sc)
        if "momentum" in legs:
            me = st["me"]
            if len(me) >= mom_months + 1:
                a, b = me[-2], me[-1 - mom_months]
                if a[TR_USD] and b[TR_USD]:
                    usd = math.log(a[TR_USD] / b[TR_USD])
                    sc = {"USD": 0.0}
                    for c in CCY:
                        x, y = a[TR[c]], b[TR[c]]
                        if x and y:
                            sc[c] = math.log(x / y) - usd
                    if len(sc) >= 4:
                        books["momentum"] = rank_weights(sc)
        if len(books) < len(legs):
            st["w"] = {}
            return st["w"]
        out = {}
        for bk in books.values():
            for c, w in bk.items():
                if c != "USD" and w:
                    out[TR[c]] = out.get(TR[c], 0.0) + w / len(legs)
        st["w"] = {s: w for s, w in out.items() if w}
        return st["w"]
    return weights


weights = make(5.0, 12)
VARIANTS = {"V4": make(4.0, 12), "V6": make(6.0, 12), "M9": make(5.0, 9), "M15": make(5.0, 15)}


# ── replication diagnostics ──────────────────────────────────────────────────
def _xlsx_rows(path, sheet=1):
    z = zipfile.ZipFile(path)
    ss = re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)
    ss = ["".join(re.findall(r"<t[^>]*>(.*?)</t>", s, re.S)) for s in ss]
    x = z.read(f"xl/worksheets/sheet{sheet}.xml").decode()
    rows = []
    for r in re.findall(r"<row [^>]*>(.*?)</row>", x, re.S):
        row = {}
        for ref, attrs, body in re.findall(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', r, re.S):
            v = re.search(r"<v>(.*?)</v>", body or "")
            if v:
                row[ref] = ss[int(v.group(1))] if 't="s"' in attrs else v.group(1)
        rows.append(row)
    return rows


def aqr_columns(url, fname, wanted):
    """{column title: {'YYYY-MM': monthly return}} from an AQR data xlsx."""
    f = rb.CACHE / fname
    if not f.exists() or datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d") != _today():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rb.CACHE.mkdir(parents=True, exist_ok=True)
        f.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    rows = _xlsx_rows(f)
    hdr = next(r for r in rows if any(v in wanted for v in r.values()))
    cols = {v: k for k, v in hdr.items() if v in wanted}
    out = {w: {} for w in wanted}
    for r in rows:
        a = r.get("A", "")
        if a.count("/") == 2:
            m, _, y = a.split("/")
            ym = f"{y}-{int(m):02d}"
        elif re.fullmatch(r"\d{5}(\.0+)?", a):             # Excel serial date
            ym = (date(1899, 12, 30) + timedelta(days=int(float(a)))).isoformat()[:7]
        else:
            continue
        for w, col in cols.items():
            if r.get(col) not in (None, ""):
                out[w][ym] = float(r[col])
    return out


def monthly_excess(wfn):
    """Monthly excess returns of a book on exactly evaluate()'s data."""
    dates, px = rb.prices(sorted(SYMS), START, fetch)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates, fetch)
    rets, _ = rb.simulate(wfn, dates, px, rf, rb.COST_BPS["fx"])
    g, gf = {}, {}
    for k, r in enumerate(rets):
        ym = dates[k + 1][:7]
        g[ym] = g.get(ym, 1.0) * (1 + r)
        gf[ym] = gf.get(ym, 1.0) * (1 + rf[k + 1])
    return {ym: g[ym] - gf[ym] for ym in g}


def _stats(xs):
    n = len(xs)
    mu = sum(xs) / n
    sd = (sum((x - mu) ** 2 for x in xs) / (n - 1)) ** 0.5
    return mu / sd * 12 ** 0.5 if sd else 0.0


def _corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def replication():
    aqr = aqr_columns(AQR_VME, "aqr_vme_factors.xlsx", ["VALLS_VME_FX", "MOMLS_VME_FX"])
    combo = {m: 0.5 * aqr["VALLS_VME_FX"][m] + 0.5 * aqr["MOMLS_VME_FX"][m]
             for m in aqr["VALLS_VME_FX"] if m in aqr["MOMLS_VME_FX"]}
    ours = monthly_excess(make(5.0, 12))
    months = [m for m in sorted(ours) if OVERLAP[0] <= m <= OVERLAP[1] and m in combo
              and abs(ours[m]) > 1e-9]
    a, b = [ours[m] for m in months], [combo[m] for m in months]
    out = {"months": len(months), "from": months[0] if months else None,
           "to": months[-1] if months else None,
           "corr_5050": round(_corr(a, b), 3) if months else None,
           "sharpe_ours": round(_stats(a), 3) if months else None,
           "sharpe_aqr": round(_stats(b), 3) if months else None}
    # leg correlations only (no leg performance is reported)
    for leg, col in (("value", "VALLS_VME_FX"), ("momentum", "MOMLS_VME_FX")):
        o = monthly_excess(make(5.0, 12, legs=(leg,)))
        mm = [m for m in months if m in o and m in aqr[col]]
        out[f"corr_{leg}"] = round(_corr([o[m] for m in mm], [aqr[col][m] for m in mm]), 3) if mm else None
    ok = (out["corr_5050"] is not None and out["corr_5050"] >= 0.50
          and abs(out["sharpe_ours"] - out["sharpe_aqr"]) <= 0.30)
    out["replicated"] = bool(ok)
    out["verdict_replication"] = "REPLICATED" if ok else "HARNESS/DATA SUSPECT"
    return out


if __name__ == "__main__":
    r = rb.evaluate(ID, weights, SYMS, None, start=START, asset_class="fx",
                    trials=35, family="fx-value", variants=VARIANTS, fetch=fetch,
                    notes="REPLICATION of AMP 2013 FX value+momentum 50/50 vs AQR's published VME FX "
                          "series (2009-06..2024-10); carry-inclusive synthetic deposit indices "
                          "(spot x OECD 3m rate, FRED), nominal value (no CPI), 12-1 momentum on "
                          "excess returns; rank weights incl. USD; month-end; T-bills bench; "
                          "careful retest of VALMOMFX/FXVALUE after harness fix 2")
    try:
        r["replication"] = replication()
    except Exception as e:                 # noqa: BLE001 — report, never hide
        r["replication"] = {"verdict_replication": "NOT COMPUTED", "error": repr(e)}
    print(json.dumps(r, indent=1))
