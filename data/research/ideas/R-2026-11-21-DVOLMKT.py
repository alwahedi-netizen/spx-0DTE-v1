"""R-2026-11-21-DVOLMKT — REPLICATION (no evaluate() call, 0 tests) of Wang &
Yan, "Downside risk and the performance of volatility-managed portfolios",
Journal of Banking & Finance 131 (2021) 106198, for the MARKET factor on the
source's own data and period. It gates I-2026-11-21-BTCDVMP (league rule 1).

Source: https://doi.org/10.1016/j.jbankfin.2021.106198 (author copy
https://www.lehigh.edu/~xuy219/research/Downside.pdf). Data: Kenneth French
library (the source's own: "Data on MKT, SMB, HML ... are from Kenneth
French's website"), monthly and daily Mkt-RF, 1926-07 -> 2018-12.
Source construction (Eq. 1-5, footnote 7): sigma_Total,t = sqrt(sum of
squared daily returns in month t); sigma_Down,t = sqrt(sum of squared
NEGATIVE daily returns in month t) — if fewer than 3 negative days, use the
negative days of months t and t-1; managed f_sigma,t = c / sigma_{t-1} * f_t,
c chosen so f_sigma and f have the same full-sample volatility (alphas'
t-stats and Sharpe are invariant to c). Spanning regression f_sigma = a + b f
with White (1980) standard errors, alpha annualised in %.
Source headline (Table 1, MKT, 1926-08 -> 2018-12):
  total-vol managed  alpha 3.34%/yr (t 3.39);
  downside-vol managed alpha 4.83%/yr (t 4.10);
  Table 3: downside on total, alpha 1.53%/yr (t 2.53).
REPLICATED (pre-registered, "sign and rough size", KNOWLEDGE theme 33) iff
ALL of: (a) downside alpha > 0 with t >= 2; (b) downside alpha within +-50%
of 4.83 (2.42 .. 7.25 %/yr); (c) downside alpha > total alpha.
Also printed (information only, never a gate): the same regressions on
1990-01 -> 2018-12 and on the post-publication-sample stretch 2019-01 ->
2024-10 (stops before the research vault, 2024-11).
DATA TIMING: the weight for month t uses daily returns of month t-1 only
(and t-2 for the <3-negative-days rule); c uses the full sample (the
source's convention; it only rescales).
"""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "R-2026-11-21-DVOLMKT"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
URL_M = BASE + "F-F_Research_Data_Factors_CSV.zip"
URL_D = BASE + "F-F_Research_Data_Factors_daily_CSV.zip"
SRC = {"total_alpha": 3.34, "total_t": 3.39, "down_alpha": 4.83, "down_t": 4.10,
       "down_on_total_alpha": 1.53, "down_on_total_t": 2.53}
_D = {}


def _rows(text, ndig):
    """(key, Mkt-RF decimal) rows whose first cell has `ndig` digits."""
    out = []
    for line in text.splitlines():
        c = [x.strip() for x in line.split(",")]
        if len(c) >= 2 and c[0].isdigit() and len(c[0]) == ndig:
            try:
                out.append((c[0], float(c[1]) / 100))
            except ValueError:
                pass
    return out


def data():
    if not _D:
        m = _rows(rb._ff_fetch(URL_M), 6)              # yyyymm (annual rows are 4 digits)
        seen, monthly = set(), []
        for k, v in m:                                  # keep the first (monthly) section only
            if k in seen:
                break
            seen.add(k)
            monthly.append((k, v))
        daily = {}
        for k, v in _rows(rb._ff_fetch(URL_D), 8):
            daily.setdefault(k[:6], []).append(v)
        _D["m"], _D["d"] = monthly, daily
    return _D["m"], _D["d"]


def sigmas(daily, months):
    """{yyyymm: (sigma_total, sigma_down)} per the source's Eq. 2-3."""
    out, prev = {}, None
    for ym in months:
        x = daily.get(ym)
        if not x:
            prev = None
            continue
        tot = math.sqrt(sum(v * v for v in x))
        neg = [v for v in x if v < 0]
        if len(neg) < 3 and prev is not None:
            neg = neg + [v for v in daily[prev] if v < 0]
        down = math.sqrt(sum(v * v for v in neg)) if neg else None
        out[ym] = (tot, down)
        prev = ym
    return out


def _sd(x):
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def ols_white(y, x):
    """y = a + b x; returns (a, b, t_a, t_b) with White (HC0) errors."""
    n = len(y)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((u - mx) * (w - my) for u, w in zip(x, y)) / sxx
    a = my - b * mx
    e = [w - a - b * u for u, w in zip(x, y)]
    s0, s1, s2 = float(n), sum(x), sum(v * v for v in x)
    det = s0 * s2 - s1 * s1
    inv = [[s2 / det, -s1 / det], [-s1 / det, s0 / det]]
    m00 = sum(r * r for r in e)
    m01 = sum(r * r * u for r, u in zip(e, x))
    m11 = sum(r * r * u * u for r, u in zip(e, x))
    meat = [[m00, m01], [m01, m11]]
    tmp = [[sum(inv[i][k] * meat[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    cov = [[sum(tmp[i][k] * inv[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    return a, b, a / math.sqrt(cov[0][0]), b / math.sqrt(cov[1][1])


def run(first="192608", last="201812"):
    monthly, daily = data()
    months = [k for k, _ in monthly]
    sig = sigmas(daily, months)
    f, gt, gd = [], [], []
    for k in range(1, len(monthly)):
        ym, prev = monthly[k][0], monthly[k - 1][0]
        if not (first <= ym <= last) or prev not in sig or sig[prev][1] is None:
            continue
        ft = monthly[k][1]
        f.append(ft)
        gt.append(ft / sig[prev][0])
        gd.append(ft / sig[prev][1])
    ct, cd = _sd(f) / _sd(gt), _sd(f) / _sd(gd)
    tot = [ct * v for v in gt]
    down = [cd * v for v in gd]
    at, _, tat, _ = ols_white(tot, f)
    ad, _, tad, _ = ols_white(down, f)
    adt, _, tadt, _ = ols_white(down, tot)
    sr = lambda x: round(sum(x) / len(x) / _sd(x) * math.sqrt(12), 3)
    return {"months": len(f), "period": [first, last],
            "total_alpha": round(at * 1200, 2), "total_t": round(tat, 2),
            "down_alpha": round(ad * 1200, 2), "down_t": round(tad, 2),
            "down_on_total_alpha": round(adt * 1200, 2), "down_on_total_t": round(tadt, 2),
            "sharpe_original": sr(f), "sharpe_total": sr(tot), "sharpe_down": sr(down)}


def replicated(r=None):
    r = r or run()
    a = r["down_alpha"] > 0 and r["down_t"] >= 2.0
    b = 0.5 * SRC["down_alpha"] <= r["down_alpha"] <= 1.5 * SRC["down_alpha"]
    c = r["down_alpha"] > r["total_alpha"]
    return {"a_down_alpha_pos_t2": a, "b_size_within_50pct": b, "c_down_beats_total": c,
            "replicated": a and b and c}


if __name__ == "__main__":
    main = run()
    print(json.dumps({"idea": IDEA, "tests": 0, "source": SRC, "source_period": main,
                      "replication": replicated(main),
                      "info_1990_2018": run("199001", "201812"),
                      "info_2019_2024_10": run("201901", "202410")}, indent=1))
