"""R-2026-11-11-LRCARRY — carry on LONG-RUN interest-rate differentials:
long the currencies whose Hamilton-filtered 10-year yield trend (vs the US)
is above the G10 median, funded in the DXY basket via UUP.

SOURCE: Kaebi & Martins, "Long-Run Interest Rate Differentials and the
Profitability of Currency Carry", Orebro University School of Business
Working Paper 2025:10 (26 Sep 2025),
https://www.oru.se/globalassets/oru-sv/institutioner/hh/workingpapers/workingpapers2025/wp-10-2025.pdf
(abstract https://swoba.hhs.se/oruesi/abs/oruesi2025_010.htm). Their rule
(Sections 2.2-2.3): for each G10 country fit i_t = d0 + sum_{j=1..12} d_j
i_{t-j} + v_t on 10-year yields over a rolling 24-month window, every month;
trend i*_t = fitted value; carry*_c = i*_c - i*_US; at each month-end go
long the currencies above the median carry*, short those below, equal
weights, monthly. 1992-2023, G10 vs USD: P2-P1 2.48%/yr, Sharpe 0.374
(t 2.03), turnover 5.4 vs 10.1 for traditional carry, net-of-cost Sharpe
0.251 vs 0.071 (15bp), skew -0.32 vs -0.71. Robust to window size and to
an expanding window (their footnote 1).

RATIONALE (written before any run): persistent (secular) rate differentials
- productivity and demographics - carry the currency risk premium; the
cyclical part is mostly monetary noise that raises turnover and crash risk.
A slow signal suits a monthly ETF rule.

LAB RULE (fixed before any run; harness-correct, every leg a funded long):
  * Yields: FRED / OECD IRLTLT01xxM156N (10-year, monthly) for AU CA CH EZ
    GB JP NO NZ SE and US. At the month-end close of month m use data
    through month m-1 (LAG 1: monthly averages of market yields, published
    within weeks; never revised).
  * Trend: the paper's AR(12) fitted value at the last month, OLS over the
    last W = 24 months (needs W + 12 months of history; a 1e-8 ridge on the
    slopes only keeps the 13-parameter fit solvable on flat Swiss/Japanese
    yields - it does not change a well-posed fit).
  * carry*_c = trend_c - trend_US; median over the 9 foreign countries.
  * Long leg: CurrencyShares trusts (FXE EZ, FXY JP, FXF CH, FXA AU, FXB GB,
    FXC CA) with a price whose carry* is ABOVE the median, equal weights
    summing to 0.5; short leg UUP 0.5 (long USD vs the DXY basket = short
    the basket). No trust above the median -> T-bills.
  * Variants (4): W36, W60 (window); EXP (expanding window); LAG2 (yields
    through month m-2).
Benchmark: T-bills (bench None). asset_class="fx" (2bp). Start 2007-03-01
(UUP).
DATA TIMING: monthly OECD 10-year yields read with a 1-month lag; trusts and
UUP are US closes; decision at the month-end close earns from the next bar.
No Yahoo `=X` series is used (themes 17/21 do not arise).
MISMATCH on the record: the short leg is the fixed DXY basket (58% EUR), not
the below-median currencies; NOK/SEK/NZD enter the median but cannot be
held (no US trust); the trusts earn deposit rates minus 0.40%, not forward
discounts. The paper's sample ends 2023 and covers our window, so this is a
re-implementation, not an out-of-sample test.
FAMILY "fx-lrcarry" (new) -> trials 5.
DATA SOURCES: Yahoo (trusts, UUP) + FRED fredgraph.csv (10 series), cached in
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
FOREIGN = ["AU", "CA", "CH", "EZ", "GB", "JP", "NO", "NZ", "SE"]
SYMS = list(TRUSTS) + ["UUP"]
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
P = 12          # AR lags (paper)


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


def load_yields():
    """{country: {'YYYY-MM': 10y yield}}"""
    return {c: {d[:7]: x for d, x in fred(f"IRLTLT01{c}M156N").items()} for c in FOREIGN + ["US"]}


def _month_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _solve(a, b):
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-14:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def trend(series, ym, window):
    """Paper's AR(12) fitted value at month ym, OLS on the last `window`
    months ending at ym (window None = expanding). None if history short or
    a month is missing."""
    hist = []
    k = 0
    while True:
        v = series.get(_month_back(ym, k))
        if v is None:
            break
        hist.append(v)
        k += 1
        if window is not None and k >= window + P:
            break
    hist.reverse()                                  # oldest -> newest, ends at ym
    n_obs = len(hist) - P
    if n_obs < (window if window is not None else 24):
        return None
    rows = [[1.0] + [hist[t - j] for j in range(1, P + 1)] for t in range(P, len(hist))]
    y = hist[P:]
    k = P + 1
    xtx = [[sum(r[a] * r[b] for r in rows) for b in range(k)] for a in range(k)]
    for a in range(1, k):
        xtx[a][a] += 1e-8                           # tiny ridge on slopes only
    xty = [sum(r[a] * yy for r, yy in zip(rows, y)) for a in range(k)]
    beta = _solve(xtx, xty)
    if beta is None:
        return None
    return sum(b * x for b, x in zip(beta, rows[-1]))


def make(window=24, lag=1, yields=None):
    ylds = yields if yields is not None else load_yields()
    st = {"w": {}}
    memo = {}                                       # pure function of (month) - safe across re-simulations

    def signal(ym):
        if ym not in memo:
            tus = trend(ylds["US"], ym, window)
            cs = {c: trend(ylds[c], ym, window) for c in FOREIGN}
            cs = {c: t - tus for c, t in cs.items() if t is not None} if tus is not None else {}
            memo[ym] = cs
        return memo[ym]

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                              # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        cs = signal(_month_back(dates[i][:7], lag))
        w = {}
        if len(cs) >= 5 and px["UUP"][i]:
            vals = sorted(cs.values())
            n = len(vals)
            med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
            longs = [etf for etf, c in TRUSTS.items() if c in cs and cs[c] > med and px[etf][i]]
            if longs:
                w = {etf: 0.5 / len(longs) for etf in longs}
                w["UUP"] = 0.5
        st["w"] = w
        return st["w"]
    return weights


if __name__ == "__main__":
    Y = load_yields()
    r = rb.evaluate("R-2026-11-11-LRCARRY", make(yields=Y), SYMS, None, start="2007-03-01",
                    asset_class="fx", trials=5, family="fx-lrcarry",
                    variants={"W36": make(window=36, yields=Y), "W60": make(window=60, yields=Y),
                              "EXP": make(window=None, yields=Y), "LAG2": make(lag=2, yields=Y)},
                    notes="Kaebi-Martins long-run carry: month-end, Hamilton/AR(12) 24m trend of OECD 10y "
                          "yields (m-1) minus US; long trusts above the 9-country median (0.5 total), "
                          "UUP 0.5; bench T-bills")
    print(json.dumps(r, indent=1))
