"""R-2026-11-11-GOODCARRY — "good carry": G10 carry that leaves out the
typical carry currencies (AUD, JPY, NOK), built harness-correct as long
deposit-backed CurrencyShares trusts funded in the DXY basket via UUP.
Promotes ledger row I-2026-11-08-GOODCARRY (replace that row).

SOURCE: Bekaert & Panayotov, "Good Carry, Bad Carry", Journal of Financial
and Quantitative Analysis 55(4) 2020, 1063-1094 (CEPR DP13463,
https://repec.cepr.org/repec/cpr/ceprdp/DP13463.pdf): equal-weighted carry on
subsets of G10 that exclude the typical carry currencies has a higher Sharpe
and less negative skew than all-G10 carry; summaries name AUD, JPY and NOK as
the excluded "bad" currencies (https://alphaarchitect.com/2015/05/currency-investing-good-carry-bad-carry/ ;
benchmark carry Sharpe 0.32, best subset 0.61 - in-sample selection).
Follow-up: Iwanaga & Sakemoto (SSRN 5465034, via quantseeker weekly recap
314): good carry Sharpe 0.76 gross / 0.54 net vs 0.64 / 0.28 standard,
G10 1980-2024.

RATIONALE (written before any run): carry's crash risk is concentrated in a
few currencies whose positions are crowded (AUD long / JPY short); the same
rate premium earned in less crowded currencies keeps most of the return with
less unwind risk.

CORE CONSTRUCTION (lab; shared with R-2026-11-11-VIXCARRY, family
fx-carry-dxy):
  * Rates: FRED / OECD 3-month interbank IR3TIB01xxM156N, month m-2 at the
    month-end close of month m (publication lag; missing -> latest earlier).
  * Funding basket rate B = DXY-weighted mean of EZ .576 JP .136 GB .119
    CA .091 SE .042 CH .036 (renormalised over available).
  * Candidates: trusts in the universe with a price and rate_k > B + hurdle
    (base 0.40 = the trusts' fee). Hold the top N by rate_k at 0.5/N each,
    plus UUP at the same total weight (UUP = long USD vs the DXY basket,
    so trust + UUP = long currency k vs the basket, USD netted out). Rest
    in T-bills. No UUP price -> all T-bills.
  * Economic check: 0.5 x trust (r_k + spot_k - fee) + 0.5 x UUP (r_US +
    spot_USD + r_US - r_B - fee) - 1 x r_US = 0.5 (r_k - r_B + spot_k vs
    basket) - fees: the carry-trade excess return, every leg a funded long.
GOODCARRY RULE: universe FXE, FXF, FXB, FXC (FXA and FXY excluded; NOK has
no trust). N = 2, hurdle 0.40.
  * Variants (4): N1, N3, H0 (hurdle 0.00), H80 (hurdle 0.80).
Benchmark: T-bills (bench None). asset_class="fx" (2bp). Start 2007-03-01.
DATA TIMING: OECD monthly rates read with a 2-month lag; trusts and UUP are
US closes, decision at the month-end close earns from the next bar; no
Yahoo `=X` series is used (KNOWLEDGE themes 17/21 do not arise).
MISMATCH on the record: the funding leg is the fixed DXY basket (incl. JPY
13.6%, EUR 57.6%), not the lowest-rate currencies; with AUD gone the long
universe is EUR/CHF/GBP/CAD, and EUR is also 58% of the funding basket, so
FXE is rarely a candidate. The good/bad classification in the source is an
in-sample choice.
FAMILY "fx-carry-dxy" (new). RUN ORDER: run this BEFORE VIXCARRY -> trials 5
(VIXCARRY then 11).
DATA SOURCES: Yahoo (trusts, UUP) + FRED fredgraph.csv (7 series), cached in
data/research/cache/fred_<id>.json (git-ignored).
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

TRUSTS = {"FXE": "EZ", "FXY": "JP", "FXF": "CH", "FXA": "AU", "FXB": "GB", "FXC": "CA"}
GOOD = ["FXE", "FXF", "FXB", "FXC"]
DXYW = {"EZ": 0.576, "JP": 0.136, "GB": 0.119, "CA": 0.091, "SE": 0.042, "CH": 0.036}
SYMS = GOOD + ["UUP"]
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
LAG = 2


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
    cs = sorted(set(TRUSTS.values()) | set(DXYW))
    return {c: {d[:7]: x for d, x in fred(f"IR3TIB01{c}M156N").items()} for c in cs}


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


def basket_rate(rates, ym):
    got = {c: _rate(rates[c], ym) for c in DXYW}
    got = {c: r for c, r in got.items() if r is not None}
    tw = sum(DXYW[c] for c in got)
    return sum(DXYW[c] * r for c, r in got.items()) / tw if tw else None


def carry_book(i, px, rates, ym, universe, top_n, hurdle):
    """Target weights of the DXY-funded carry book (shared core)."""
    b = basket_rate(rates, ym)
    if b is None or not px["UUP"][i]:
        return {}
    cands = []
    for etf in universe:
        r = _rate(rates[TRUSTS[etf]], ym)
        if px[etf][i] and r is not None and r > b + hurdle:
            cands.append((r, etf))
    cands.sort(reverse=True)
    w = {etf: 0.5 / top_n for _, etf in cands[:top_n]}
    if w:
        w["UUP"] = sum(w.values())
    return w


def make(universe=GOOD, top_n=2, hurdle=0.40, rates=None):
    rates = rates if rates is not None else load_rates()
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                              # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        st["w"] = carry_book(i, px, rates, _month_back(dates[i][:7], LAG), universe, top_n, hurdle)
        return st["w"]
    return weights


if __name__ == "__main__":
    R = load_rates()
    r = rb.evaluate("R-2026-11-11-GOODCARRY", make(rates=R), SYMS, None, start="2007-03-01",
                    asset_class="fx", trials=20, family="L-fx-etfcarry",
                    variants={"N1": make(top_n=1, rates=R), "N3": make(top_n=3, rates=R),
                              "H0": make(hurdle=0.0, rates=R), "H80": make(hurdle=0.80, rates=R)},
                    notes="Bekaert-Panayotov good carry: month-end, top-2 of FXE/FXF/FXB/FXC by OECD 3m "
                          "rate (m-2) above the DXY-basket rate + 0.40, 0.25 each, funded with UUP 0.5 "
                          "(short the DXY basket); AUD/JPY excluded; bench T-bills")
    print(json.dumps(r, indent=1))
