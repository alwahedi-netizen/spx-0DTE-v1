"""L-2026-11-11-RATEMOM — policy-cycle momentum: long the currencies whose
short rates have risen most over the last 6 months (relative to the DXY
basket), funded in the DXY basket via UUP (lab original, RESEARCH.md §2b).

VARIES: I-2026-11-07-FOXY (Simplify FOXY's G10 bucket: 3v3 on momentum of
short-dated forward-implied yields - untestable for lack of forwards) and
L-2026-11-10-OECDCARRY / R-2026-11-11-GOODCARRY (carry LEVELS). This trades
the CHANGE in rates, using the same FRED/OECD series, on the same
harness-correct funded construction as the fx-carry-dxy core.

INGREDIENTS: Simplify FOXY methodology (https://simplify.us/sites/default/files/fund-insights/2025-02/Simplify-FI-FOXY-Harvesting-Foreign-Exchange-Risk-Premia.pdf,
G10 implied-yield momentum); MUFG FX Quant 22 Oct 2026 (carry family
signals include "changes in those [2Y] differentials",
https://www.mufgresearch.com/fx/fx-quant-what-fx-signals-are-winning-22-october-2026/);
Molodtsova & Papell, JIE 2009 (Taylor-rule fundamentals - expected policy
tightening - forecast exchange rates out of sample).

RATIONALE (written before any run): central-bank cycles are persistent: a
bank that has been hiking keeps hiking, so its currency's carry is rising
and markets under-price the path (spot adjusts with a lag, as in the
"delayed overshooting" literature). Rate CHANGES are less crowded than rate
levels and are not the AUD-long / JPY-short carry book.

RULE (fixed before any run):
  * Rates: FRED / OECD 3-month interbank IR3TIB01xxM156N; at the month-end
    close of month m use month m-2 (publication lag; missing -> latest
    earlier) and month m-2-L (L = 6).
  * d_k = rate_k(m-2) - rate_k(m-2-L) for FXE EZ, FXY JP, FXF CH, FXA AU,
    FXB GB, FXC CA; d_B = the same change for the DXY-weighted basket (EZ .576
    JP .136 GB .119 CA .091 SE .042 CH .036).
  * Candidates: trusts with a price and d_k > d_B (tightening faster than
    the funding basket). Hold the top N = 2 by d_k at 0.25 each + UUP at the
    same total weight (long currency k vs the DXY basket); rest T-bills.
  * Variants (4): L3, L12 (lookback months); N1, N3.
Benchmark: T-bills (bench None). asset_class="fx" (2bp). Start 2007-03-01.
DATA TIMING: OECD monthly averages read with a 2-month lag (no look-ahead);
trusts and UUP are US closes; no Yahoo `=X` series (themes 17/21 do not
arise).
EXPECTED WEAKNESS: 2008 (rates cut everywhere - ranking by who cut least);
2009-15 ZIRP (changes ~0, ranking is noise between tiny moves); the funding
basket is fixed (EUR 58%), so a fast-hiking ECB makes FXE a candidate that
is partly hedged by its own basket leg.
FAMILY "L-fx-ratemom" (new) -> trials 5.
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
DXYW = {"EZ": 0.576, "JP": 0.136, "GB": 0.119, "CA": 0.091, "SE": 0.042, "CH": 0.036}
SYMS = list(TRUSTS) + ["UUP"]
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


def _change(series, ym, look):
    a, b = _rate(series, ym), _rate(series, _month_back(ym, look))
    return None if a is None or b is None else a - b


def basket_change(rates, ym, look):
    got = {c: _change(rates[c], ym, look) for c in DXYW}
    got = {c: d for c, d in got.items() if d is not None}
    tw = sum(DXYW[c] for c in got)
    return sum(DXYW[c] * d for c, d in got.items()) / tw if tw else None


def make(look=6, top_n=2, rates=None):
    rates = rates if rates is not None else load_rates()
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                              # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        ym = _month_back(dates[i][:7], LAG)
        db = basket_change(rates, ym, look)
        w = {}
        if db is not None and px["UUP"][i]:
            cands = []
            for etf, c in TRUSTS.items():
                d = _change(rates[c], ym, look)
                if px[etf][i] and d is not None and d > db:
                    cands.append((d, etf))
            cands.sort(reverse=True)
            w = {etf: 0.5 / top_n for _, etf in cands[:top_n]}
            if w:
                w["UUP"] = sum(w.values())
        st["w"] = w
        return st["w"]
    return weights


if __name__ == "__main__":
    R = load_rates()
    r = rb.evaluate("L-2026-11-11-RATEMOM", make(rates=R), SYMS, None, start="2007-03-01",
                    asset_class="fx", trials=5, family="L-fx-ratemom",
                    variants={"L3": make(look=3, rates=R), "L12": make(look=12, rates=R),
                              "N1": make(top_n=1, rates=R), "N3": make(top_n=3, rates=R)},
                    notes="policy-cycle momentum: month-end, top-2 trusts by 6-month change in OECD 3m "
                          "rate (m-2) above the DXY-basket change, 0.25 each + UUP 0.5; bench T-bills")
    print(json.dumps(r, indent=1))
