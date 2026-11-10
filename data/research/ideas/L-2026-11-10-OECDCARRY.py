"""L-2026-11-10-OECDCARRY — G10 carry ranked on true 3-month interbank rates
(FRED / OECD), held in deposit-backed CurrencyShares trusts (lab original,
RESEARCH.md §2b: a variation of a ledger row that failed for a stated, fixable
reason).

VARIES: L-2026-11-08-ETFCARRY (FAIL: 0.7%/yr vs 1.4%, held-out Sharpe 0.24).
Its stated weakness (L-2026-11-08-HEDGECARRYPX proxy check, 2026-11-09): the
rates it backed out of the ETF drift lag policy by 100-250bp and sit below
T-bills for most currencies in 2009-16, so its ranking and its "beats T-bills"
test were both measured with error. FIX: rank on the OECD 3-month interbank
rate itself (FRED IR3TIB01xxM156N, monthly), which the 2026-11-10 desk found
reachable from the research environment (fredgraph.csv, HTTP 200) — the data
gap KNOWLEDGE.md theme 12 lists as "no FRED rates".

INGREDIENTS: Lustig, Roussanov & Verdelhan, "Common risk factors in currency
markets", RFS 2011 (https://www.nber.org/papers/w14082) and Koijen, Moskowitz,
Pedersen & Vrugt, "Carry", JFE 2018: high-rate currencies earn a premium over
low-rate ones; the long leg alone (vs USD) is the part a long-only,
deposit-backed holder can earn.

RATIONALE (written before any run): the carry premium is paid for holding
high-rate currencies through global risk-off episodes. A US holder captures it
long-only by holding the highest-rate currencies' deposits when they out-yield
US bills by more than the trusts' 0.40% fee. ETFCARRY tested this with a noisy
rate; this tests the same holding rule with the rate the literature uses.

RULE (fixed before any run):
  * Universe: FXE (EUR, FRED EZ), FXY (JPY, JP), FXF (CHF, CH), FXA (AUD, AU),
    FXB (GBP, GB), FXC (CAD, CA); US rate = IR3TIB01USM156N. Only trusts with
    a price that day.
  * At each month-end close of month m: rate_k = the OECD monthly value for
    month m-2 (publication lag: on 2026-11-10 the latest AU value was 2026-08,
    so m-2 is what a real-time reader has; a missing value -> the latest
    earlier month).
  * Candidates: rate_k > US rate (same month m-2) + 0.40 (the trust fee).
    Hold the top N = 2 candidates by rate_k at 1/N each next month; unfilled
    slots stay in T-bills (no rescaling).
  * Variants: N = 1, N = 3, hurdle 0.00, hurdle 0.80.
Benchmark: T-bills. asset_class="fx" (2bp). Start 2006-06-01 (FXA/FXB/FXC/FXF
list 2006-06; FXY 2007-02; FXE 2005-12). JP series starts 2002-04, CH 1999-07.
Instrument choice: the trusts hold deposits, so the harness return is the
currency's true total return minus 0.40% (spot pairs would earn no interest).
FAMILY "L-fx-etfcarry" (ETFCARRY 5 + CARRYTREND-guard family separate) -> 10
already -> trials 15.
DATA SOURCES: Yahoo (trusts) + FRED fredgraph.csv (7 OECD series), fetched by
this script and cached in data/research/cache/fred_<id>.json (git-ignored).
EXPECTED WEAKNESS: 2008 (AUD -35% in months), 2013-15 commodity bust; the
CurrencyShares deposit rate is below interbank (bank spread), so the trusts
under-earn the ranking signal by a varying spread.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

TRUSTS = {"FXE": "EZ", "FXY": "JP", "FXF": "CH", "FXA": "AU", "FXB": "GB", "FXC": "CA"}
SYMS = list(TRUSTS)
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
LAG = 2   # months


def fred(sid):
    """FRED series as {date: float}, cached per day (FRED tarpits unknown
    User-Agents; the default Python-urllib agent and curl's are served)."""
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
        except Exception as e:          # noqa: BLE001 — retry with the other agent
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
    """{country: {'YYYY-MM': rate}}"""
    out = {}
    for c in list(TRUSTS.values()) + ["US"]:
        s = fred(f"IR3TIB01{c}M156N")
        out[c] = {d[:7]: x for d, x in s.items()}
    return out


def _month_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:7])
    m -= k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _rate(series, ym):
    """value for month ym, else the latest earlier month (up to 6 back)."""
    for k in range(7):
        v = series.get(_month_back(ym, k))
        if v is not None:
            return v
    return None


def make(top_n=2, hurdle=0.40, rates=None):
    rates = rates if rates is not None else load_rates()
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                              # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        ym = _month_back(dates[i][:7], LAG)
        us = _rate(rates["US"], ym)
        cands = []
        for etf, c in TRUSTS.items():
            r = _rate(rates[c], ym)
            if px[etf][i] and r is not None and us is not None and r > us + hurdle:
                cands.append((r, etf))
        cands.sort(reverse=True)
        st["w"] = {etf: 1.0 / top_n for _, etf in cands[:top_n]}
        return st["w"]
    return weights


if __name__ == "__main__":
    R = load_rates()
    r = rb.evaluate("L-2026-11-10-OECDCARRY", make(2, 0.40, R), SYMS, None, start="2006-06-01",
                    asset_class="fx", trials=15, family="L-fx-etfcarry",
                    variants={"N1": make(1, 0.40, R), "N3": make(3, 0.40, R),
                              "H0": make(2, 0.0, R), "H80": make(2, 0.80, R)},
                    notes="month-end: hold the top-2 CurrencyShares trusts by OECD 3m interbank rate "
                          "(FRED IR3TIB01, month m-2) among those beating the US rate + 0.40%; 1/2 each, "
                          "else T-bills; ETFCARRY with true rates")
    print(json.dumps(r, indent=1))
