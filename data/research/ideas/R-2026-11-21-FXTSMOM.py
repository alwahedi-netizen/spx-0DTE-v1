"""R-2026-11-21-FXTSMOM — REPLICATION: time-series momentum (trend) in the nine
G10 currencies vs the dollar (Moskowitz, Ooi & Pedersen 2013), checked month by
month against the SOURCE'S OWN published, updated factor series (AQR "Time
Series Momentum: Factors, Monthly", column TSMOM^FX). It is tested here as an FX
CRISIS SLEEVE that does not depend on any currency being a haven.

WHY THIS, WHY NOW (theme 31 + theme 29 + round 1): G10 FX style premia are
~zero over our window, so the FX budget goes to crisis sleeves and diversifiers.
The haven family (L-fx-safehaven: SAFEHAVEN, HAVENVOL, HAVENRATES, DOLHAVEN,
HAVENSPLIT, 50+ trials) bets on WHICH currency is the haven and fails when that
currency falls with stocks (yen in 2022, dollar in 2009 H1). Trend has no
fixed haven: it is short whatever has been falling (AUD/NZD in 2008, JPY/EUR in
2022). In the source's own series (AQR TSMOM^FX, 2005-01 .. 2024-10, 238
months; numbers read from AQR's file before any run of ours):
  * Sharpe 0.22 (t 0.98); 2005-14 0.37, 2015-24 0.09, 2017-24 -0.09;
  * correlation with SPY monthly -0.22;
  * in SPY's worst-decile months (mean SPY -8.0%) TSMOM^FX averaged +3.07%
    (vs +0.33% in all months) and was positive in 15 of 23; 2008-10 +19.8%,
    2020-03 +18.1%, 2022 +10.0% (the year the haven sleeves failed).
Paper period 1985-2009: Sharpe 0.78 (t 3.9) in the same file — cannot be
replicated here (Yahoo `=X` from 2003-12, OECD rates monthly).

SOURCE: Moskowitz, Ooi & Pedersen, "Time Series Momentum", Journal of
Financial Economics 104(2) 2012, 228-250,
https://doi.org/10.1016/j.jfineco.2011.11.003. Updated series:
https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly
(file: https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Time-Series-Momentum-Factors-Monthly.xlsx;
"a 12-month time series momentum strategy with a 1-month holding period").
VARIES: P-FX TSMOM paper lane (fx_lab.py, frozen: 12-1, 63-day inverse vol,
gross 2x, spot marks) — run here as variant PFX so the owner gets the lane's
historical record; R-2026-11-08-XTREND (same 12-month sign on dollar-free
CROSSES, FAIL Sharpe -0.38); L-2026-11-09-HEDGEUUP (12-month sign on the
dollar BASKET, long-only UUP, FAIL). This run keeps the dollar factor (the
source's construction) and adds what both earlier runs lacked: carry-inclusive
returns and per-currency vol scaling.

HYPOTHESIS (written before any run): (A) our construction on carry-inclusive
synthetic forwards reproduces AQR's TSMOM^FX on 2005-01 .. 2024-10; (B) it does
not clear the §4 bar alone (source Sharpe ~0.2 -> t ~1); (C) it IS a crisis
sleeve: it makes money in the months the S&P 500 falls hardest, with negative
correlation to stocks, at a positive full-period Sharpe.

PASS CRITERION (pre-registered, three separate questions):
  A. REPLICATION (decides whether anything else runs): over the overlap
     months 2005-01 .. 2024-10 in which our book holds positions, monthly
     excess returns correlate >= 0.50 with AQR TSMOM^FX AND our annualised
     Sharpe is within +/- 0.30 of AQR's over the same months. Both ->
     "REPLICATED"; else "HARNESS/DATA SUSPECT": the script prints that and
     STOPS WITHOUT calling evaluate (no trial is spent, no variant runs).
  B. STRATEGY: the research_bt verdict vs T-bills (§4 + world-class gates).
     Expected FAIL (t >= 3 needs Sharpe ~0.7 over 20 years).
  C. CRISIS SLEEVE (the building-block claim, judged on development data
     only, monthly, overlap months): corr(ours, SPY) <= 0; mean excess
     return in SPY's worst-decile months > 0 AND above our all-month mean;
     positive in >= 60% of those months; full-period Sharpe > 0 (from B).
     C holds -> candidate crisis sleeve for the book (the lead's
     portfolio.marginal decides fit); C fails -> FX trend is not the crisis
     sleeve and the family stops here.
DATA-TIMING: FX-only book — signal and trade are on the SAME `=X` bars (true
~19:00 ET closes after harness fix 2; no US-close asset is read, so theme 30's
cross-asset peek does not arise). At month-end bar i the signal reads USD
prices at bars i and the month-end L months earlier (spot part) plus the OECD
3-month rate gap for months m-2 .. m-L-1 (carry part; m = bar i's month; the
two-month lag clears OECD's ~1-month publication lag). Vol reads daily excess
returns up to bar i. Weights decided at close i earn close i -> close i+1 on
the synthetic forward TR_<ccy> (spot x compounded deposit rate, accrual on bar
k uses the rate of the month BEFORE bar k's month, as VMEFX/STYLE3FX, whose red
team found no look-ahead); held to the next month-end.
RULE (fixed before any run; MOP 2012 §2.4 / AQR TSMOM):
  * Universe: EUR GBP AUD NZD JPY CHF CAD SEK NOK vs USD (AQR's FX set).
  * At each month-end: s_c = sign(12-month excess return of currency c vs USD)
    = sign(ln spot_c(i)/spot_c(i-12 month-ends) + sum of (r_c - r_US)/1200
    over months m-2 .. m-13).
  * Ex-ante vol sigma_c: EWMA of squared daily excess log returns of TR_c vs
    TR_USD, centre of mass 60 days (delta = 60/61), annualised x261; needs
    >= 60 daily returns.
  * w_c = s_c x (0.10 / sigma_c) / N, N = currencies with a signal and a vol
    (>= 4, else T-bills). Gross capped at 1.0 (cash-account sizing: no
    leverage; AQR targets 40% per leg — scale only, the replication test
    uses correlation and Sharpe, both scale-free).
  * Variants: lookback 6, 9, 15, 18 months; PFX = the P-FX TSMOM lane's frozen
    rule (12-1 on daily spot bars i-21 vs i-273, weights ∝ sign / 63-day spot
    vol, gross = 2.0, held on TR_<ccy>).
Instruments: synthetic carry-inclusive forwards; tradeable at Schwab via CME
FX futures (6E 6J 6B 6S 6A 6C 6N; SEK/NOK futures are thin) or, for 6 of 9,
CurrencyShares (FXE FXY FXB FXF FXA FXC, shortable). Benchmark T-bills;
asset_class "fx" (2bp). Start 2003-12-01; positions from ~2005-01 (AUD joins
2006-05). FAMILY "fx-tsmom" (new name; same hypothesis as XTREND (5 trials in
trials.json, 11 by its own header incl. 6 DD-TREND FX runs) and HEDGEUUP (5)):
honest prior 16 -> trials 16 + 1 + 5 variants = 22. Never vault.
DATA: Yahoo `=X` (via research_bt), FRED fredgraph.csv (10 OECD 3m rates), AQR
xlsx — all cached in data/research/cache/ (git-ignored). Diagnostics
re-simulate the SAME book on the SAME development data only to build its
monthly series; they print no performance of any other rule.
"""
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

ID = "R-2026-11-21-FXTSMOM"
FAMILY = "fx-tsmom"
TRIALS = 22
START = "2003-12-01"
OVERLAP = ("2005-01", "2024-10")
LEG_VOL = 0.10            # per-leg vol target before dividing by N
DELTA = 60.0 / 61.0       # EWMA centre of mass 60 days (MOP 2012)
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
AQR_TSMOM = ("https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/"
             "Time-Series-Momentum-Factors-Monthly.xlsx")


# ── data helpers (copied from R-2026-11-14-VMEFX, unchanged) ─────────────────
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


_RATES = {}


def rates():
    """{ccy or 'USD': {YYYY-MM: % p.a.}} — OECD 3m rates (signal carry part)."""
    if not _RATES:
        for c, v in CCY.items():
            _RATES[c] = fred(f"IR3TIB01{v[2]}M156N")
        _RATES["USD"] = fred("IR3TIB01USM156N")
    return _RATES


def usd_price(px, c, k):
    sym, sg = CCY[c][0], CCY[c][1]
    v = px[sym][k]
    return None if not v else (v if sg > 0 else 1.0 / v)


def carry_part(c, ym, months):
    """sum of (r_c - r_US)/1200 over months m-2 .. m-months-1 (lagged 2)."""
    rt, tot = rates(), 0.0
    for k in range(2, months + 2):
        a, b = rate_for(rt[c], month_back(ym, k)), rate_for(rt["USD"], month_back(ym, k))
        if a is None or b is None:
            return None
        tot += (a - b) / 1200.0
    return tot


# ── the rule ─────────────────────────────────────────────────────────────────
def make(lookback=12):
    """MOP/AQR TSMOM: sign of the L-month excess return, EWMA-vol scaled."""
    st = {}

    def weights(i, dates, px):
        if i == 0:                                     # evaluate() re-simulates
            st.clear()
            st.update(w={}, me=[], prev={}, mu={}, var={}, n={})
        for c in CCY:                                  # daily vol update (bar i)
            x, u = px[TR[c]][i], px[TR_USD][i]
            if not (x and u):
                continue
            lv = math.log(x / u)
            if c in st["prev"]:
                r = lv - st["prev"][c]
                if c not in st["var"]:
                    st["mu"][c], st["var"][c], st["n"][c] = 0.0, r * r, 1
                else:
                    st["mu"][c] = DELTA * st["mu"][c] + (1 - DELTA) * r
                    st["var"][c] = DELTA * st["var"][c] + (1 - DELTA) * (r - st["mu"][c]) ** 2
                    st["n"][c] += 1
            st["prev"][c] = lv
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        st["me"].append({c: usd_price(px, c, i) for c in CCY})
        me, ym = st["me"], dates[i][:7]
        if len(me) < lookback + 1:
            st["w"] = {}
            return st["w"]
        raw = {}
        for c in CCY:
            a, b = me[-1][c], me[-1 - lookback][c]
            if not (a and b) or st["n"].get(c, 0) < 60:
                continue
            cp = carry_part(c, ym, lookback)
            if cp is None:
                continue
            sig = math.log(a / b) + cp
            vol = math.sqrt(st["var"][c] * 261)
            if sig == 0 or vol <= 0:
                continue
            raw[c] = (1.0 if sig > 0 else -1.0) * LEG_VOL / vol
        if len(raw) < 4:
            st["w"] = {}
            return st["w"]
        w = {c: v / len(raw) for c, v in raw.items()}
        g = sum(abs(v) for v in w.values())
        if g > 1.0:
            w = {c: v / g for c, v in w.items()}
        st["w"] = {TR[c]: v for c, v in w.items() if v}
        return st["w"]
    return weights


def make_pfx():
    """P-FX TSMOM lane (fx_lab.py, frozen): 12-1 spot return on daily bars
    (i-21 vs i-273), weights ∝ sign / 63-day spot vol, gross = 2.0."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["w"] = {}
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end or i < 273:
            return st["w"]
        ws = {}
        for c in CCY:
            a, b = usd_price(px, c, i - 21), usd_price(px, c, i - 273)
            s = [usd_price(px, c, k) for k in range(i - 63, i + 1)]
            s = [p for p in s if p]
            if not (a and b) or len(s) < 30:
                continue
            lr = [math.log(s[k] / s[k - 1]) for k in range(1, len(s))]
            m = sum(lr) / len(lr)
            v = math.sqrt(sum((x - m) ** 2 for x in lr) / len(lr)) * math.sqrt(252)
            if v <= 0 or a == b:
                continue
            ws[c] = (1.0 if a > b else -1.0) / v
        tot = sum(abs(x) for x in ws.values())
        st["w"] = {TR[c]: x / tot * 2.0 for c, x in ws.items()} if tot else {}
        return st["w"]
    return weights


weights = make(12)
VARIANTS = {"L6": make(6), "L9": make(9), "L15": make(15), "L18": make(18), "PFX": make_pfx()}


# ── replication + crisis diagnostics (same book, development data only) ──────
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


def aqr_column(url, fname, wanted):
    """{'YYYY-MM': monthly excess return} for one column of an AQR xlsx."""
    f = rb.CACHE / fname
    if not f.exists() or datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d") != _today():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rb.CACHE.mkdir(parents=True, exist_ok=True)
        f.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    rows = _xlsx_rows(f)
    hdr = next(r for r in rows if wanted in r.values())
    col = next(k for k, v in hdr.items() if v == wanted)
    out = {}
    for r in rows:
        a = r.get("A", "")
        if a.count("/") == 2:
            m, _, y = a.split("/")
            ym = f"{y}-{int(m):02d}"
        elif re.fullmatch(r"\d{5}(\.0+)?", a):             # Excel serial date
            ym = (date(1899, 12, 30) + timedelta(days=int(float(a)))).isoformat()[:7]
        else:
            continue
        if r.get(col) not in (None, ""):
            out[ym] = float(r[col])
    return out


def monthly_excess(wfn):
    """Monthly excess returns of a book on exactly evaluate()'s dev data."""
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


def us_monthly(sym):
    """Monthly total returns of a US-listed fund (Yahoo adjusted closes)."""
    d, p = rb.prices([sym], "2000-01-01")
    me = {}
    for k, x in enumerate(d):
        if p[sym][k] and x < rb.VAULT_FROM:
            me[x[:7]] = p[sym][k]
    ms = sorted(me)
    return {ms[k]: me[ms[k]] / me[ms[k - 1]] - 1 for k in range(1, len(ms))}


def _sharpe_m(xs):
    n = len(xs)
    mu = sum(xs) / n
    sd = (sum((x - mu) ** 2 for x in xs) / (n - 1)) ** 0.5
    return mu / sd * 12 ** 0.5 if sd else 0.0


def _corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def active_months(ours):
    return [m for m in sorted(ours) if OVERLAP[0] <= m <= OVERLAP[1] and abs(ours[m]) > 1e-9]


def replication(ours=None):
    aqr = aqr_column(AQR_TSMOM, "aqr_tsmom_factors.xlsx", "TSMOM^FX")
    ours = ours if ours is not None else monthly_excess(make(12))
    months = [m for m in active_months(ours) if m in aqr]
    if len(months) < 60:
        return {"months": len(months), "replicated": False,
                "verdict_replication": "HARNESS/DATA SUSPECT (too few overlap months)"}
    a, b = [ours[m] for m in months], [aqr[m] for m in months]
    out = {"months": len(months), "from": months[0], "to": months[-1],
           "corr": round(_corr(a, b), 3),
           "sharpe_ours": round(_sharpe_m(a), 3), "sharpe_aqr": round(_sharpe_m(b), 3)}
    ok = out["corr"] >= 0.50 and abs(out["sharpe_ours"] - out["sharpe_aqr"]) <= 0.30
    out["replicated"] = bool(ok)
    out["verdict_replication"] = "REPLICATED" if ok else "HARNESS/DATA SUSPECT"
    return out


def crisis_check(ours):
    """Criterion C on the overlap months (development data only)."""
    spy, uup = us_monthly("SPY"), us_monthly("UUP")
    months = [m for m in active_months(ours) if m in spy]
    a, s = [ours[m] for m in months], [spy[m] for m in months]
    worst = sorted(months, key=lambda m: spy[m])[:max(1, len(months) // 10)]
    wm = sum(ours[m] for m in worst) / len(worst)
    allm = sum(a) / len(a)
    hit = sum(1 for m in worst if ours[m] > 0) / len(worst)
    mu = [m for m in months if m in uup]
    out = {"months": len(months), "corr_spy": round(_corr(a, s), 3),
           "worst_decile_n": len(worst),
           "worst_decile_mean_pct": round(wm * 100, 3),
           "worst_decile_spy_mean_pct": round(sum(spy[m] for m in worst) / len(worst) * 100, 3),
           "all_month_mean_pct": round(allm * 100, 3),
           "worst_decile_hit": round(hit, 3),
           "corr_uup_info_only": round(_corr([ours[m] for m in mu], [uup[m] for m in mu]), 3) if len(mu) > 24 else None,
           "by_month_info_only": {m: round(ours[m] * 100, 2) for m in ("2008-09", "2008-10", "2008-11", "2011-08", "2020-03", "2022-06", "2022-09") if m in ours}}
    out["crisis_sleeve_C"] = bool(out["corr_spy"] <= 0 and wm > 0 and wm > allm and hit >= 0.60)
    return out


if __name__ == "__main__":
    ours = monthly_excess(make(12))
    rep = replication(ours)
    print(json.dumps({"id": ID, "replication": rep}, indent=1))
    if not rep.get("replicated"):
        print(json.dumps({"id": ID, "verdict": "NOT RUN",
                          "reason": "replication failed -> harness/data suspect; evaluate() not called, "
                                    "no trial spent, no variant (I-2026-11-21-FXTREND3 will not run)"}))
        sys.exit(0)
    r = rb.evaluate(ID, weights, SYMS, None, start=START, asset_class="fx",
                    trials=TRIALS, family=FAMILY, variants=VARIANTS, fetch=fetch,
                    notes="REPLICATION of MOP 2012 FX time-series momentum vs AQR TSMOM^FX "
                          "(2005-01..2024-10); 9 G10 vs USD; sign of 12-month excess return "
                          "(spot + OECD rate gap lagged 2 months); EWMA-60d vol scaling, 10%/leg/N, "
                          "gross <= 1; carry-inclusive synthetic forwards; month-end; T-bills bench; "
                          "tested as a crisis sleeve outside the haven family; variant PFX = P-FX "
                          "TSMOM paper lane rule")
    r["replication"] = rep
    try:
        r["crisis_sleeve"] = crisis_check(ours)
    except Exception as e:                 # noqa: BLE001 — report, never hide
        r["crisis_sleeve"] = {"error": repr(e)}
    print(json.dumps(r, indent=1))
