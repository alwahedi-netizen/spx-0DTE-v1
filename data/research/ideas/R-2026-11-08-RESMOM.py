"""R-2026-11-08-RESMOM — residual momentum on the point-in-time S&P 500
(survivorship-free).

Promoted from the queue row I-2026-11-07-RESMOM (scored 61 on 2026-11-07).
Varies G-MOM / R-2026-11-07-XSMOMSF: XSMOMSF (total-return 12-1 momentum)
beat SPY on honest data but had NO factor alpha (momentum loading 0.41,
alpha t -1.1) and fell 58%. Residual momentum ranks on the part of each
stock's return that the Fama-French factors do NOT explain, which the source
reports roughly doubles the risk-adjusted return and removes the crash
exposure that total momentum gets from its time-varying factor bets.
Source: Blitz, Huij & Martens (2011) "Residual momentum", J. Empirical
Finance 18(3) 506-521
(https://econpapers.repec.org/RePEc:eee:empfin:v:18:y:2011:i:3:p:506-521).

RATIONALE (fixed before any run): investors under-react to firm-specific
news; total-return momentum mixes that firm-specific drift with factor
exposure (e.g. after a value rally the winners are value stocks), and the
factor part is what crashes when factor leadership turns. Ranking on
standardized FF3 residuals isolates the firm-specific under-reaction.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on each month's last close
    (rb.sp500_members), Sharadar survivorship-free prices.
  * Monthly stock returns from month-end closes. Let month t-1 be the month
    that just ended. Regress each stock's excess returns over the 36 months
    t-37..t-2 on monthly Fama-French 3 factors (Mkt-RF, SMB, HML compounded
    from Ken French daily data via rb.ff_factors). Month t-1 is not used at
    all, so the French data's publication lag never matters.
  * Residual momentum = sum of residuals over t-12..t-2 (11 months) divided
    by their standard deviation over the same months (BHM's definition).
  * A stock needs all 37 month-end closes of the window; else it is skipped.
  * Warm-up (before the first scoreable month end, ~2000): hold SPY.
  * Hold the top decile equal-weight to the next month end (weights drift).
  * Variants (robustness gate): top 5%, top 20%, regression window 24 and
    48 months.
  * Benchmark SPY, 5bp/side, 1997-01 (SPY warm-up) -> vault, strict bar +
    FF5+Mom alpha.
  * family "XSMOM" (a momentum variant: shares G-MOM/XSMOMSF's lifetime
    count, 5 before this run) -> trials = 5 + 1 + 4 = 10.
"""
import bisect
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-08-RESMOM"
BENCH = "SPY"
_U = {"rows": None, "mem": {}, "ff": None, "ffd": None}


def hist():
    if _U["rows"] is None:
        _U["rows"] = rb.sp500_history(first_year=1996)
    return _U["rows"]


def members(day):
    if day not in _U["mem"]:
        _U["mem"][day] = rb.sp500_members(day, hist())
    return _U["mem"][day]


def ff():
    if _U["ff"] is None:
        _U["ff"] = rb.ff_factors()
        _U["ffd"] = sorted(_U["ff"])
    return _U["ff"], _U["ffd"]


def ff_month(d0, d1):
    """Compounded (Mkt-RF, SMB, HML, RF) over French days in (d0, d1]."""
    f, fd = ff()
    a, b = bisect.bisect_right(fd, d0), bisect.bisect_right(fd, d1)
    out = [1.0, 1.0, 1.0, 1.0]
    n = 0
    for d in fd[a:b]:
        row = f[d]
        if not all(k in row for k in ("Mkt-RF", "SMB", "HML")):
            continue
        for j, k in enumerate(("Mkt-RF", "SMB", "HML", "RF")):
            out[j] *= 1 + row.get(k, 0.0)
        n += 1
    return [x - 1 for x in out] if n else None


def _inv(m):
    n = len(m)
    return [rb._solve(m, [1.0 if r == c else 0.0 for r in range(n)]) for c in range(n)]


def make(top=0.10, win=36):
    st = {}

    def weights(i, dates, px):
        if i == 0:                                    # fresh state for every simulation
            st.clear()
            st["me"], st["fac"] = [], []
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if st["me"]:
                st["fac"].append(ff_month(dates[st["me"][-1]], dates[i]))
            else:
                st["fac"].append(None)
            st["me"].append(i)
            J = len(st["me"]) - 1                    # index of month t-1 (just ended)
            if J >= win + 2:
                # months used: J-win .. J-1  (= t-37..t-2 for win 36)
                months = list(range(J - win, J))
                F = [st["fac"][j] for j in months]
                if all(F):
                    X = [[1.0, f[0], f[1], f[2]] for f in F]
                    xtx = [[sum(X[r][a] * X[r][b] for r in range(win)) for b in range(4)]
                           for a in range(4)]
                    try:
                        inv = _inv(xtx)
                    except ValueError:
                        inv = None
                    if inv:
                        scores = []
                        for t in members(dates[i]):
                            s = px.get(t)
                            if s is None:
                                continue
                            idx = [st["me"][j] for j in range(J - win - 1, J)]
                            p = [s[k] for k in idx]
                            if any(v is None or v <= 0 for v in p):
                                continue
                            y = [p[m + 1] / p[m] - 1 - F[m][3] for m in range(win)]
                            xty = [sum(X[r][a] * y[r] for r in range(win)) for a in range(4)]
                            beta = [sum(inv[a][b] * xty[b] for b in range(4)) for a in range(4)]
                            res = [y[r] - sum(beta[a] * X[r][a] for a in range(4))
                                   for r in range(win)]
                            form = res[-11:]           # t-12 .. t-2
                            mu = sum(form) / 11
                            sd = (sum((e - mu) ** 2 for e in form) / 10) ** 0.5
                            if sd > 0:
                                scores.append((sum(form) / sd, t))
                        if len(scores) >= 50:
                            scores.sort(reverse=True)
                            n = max(1, int(len(scores) * top))
                            # data hygiene (fixed after a crash, before any result existed):
                            # only stocks with a price on the rebalance day can be bought
                            pick = [t for _, t in scores[:n] if px[t][i] and px[t][i] > 0]
                            n = len(pick) or 1
                            st["w"] = {t: 1.0 / n for t in pick}
                            st["base"] = {t: px[t][i] for t in pick}
                            st["last"] = dict(st["base"])
                            return dict(st["w"])
        if "w" not in st:
            return {BENCH: 1.0}                        # warm-up = benchmark
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t]
        tot = sum(v.values())
        return {t: x / tot for t, x in v.items()} if tot > 0 else {}

    return weights


weights = make()
VARIANTS = {"top5%": make(top=0.05), "top20%": make(top=0.20),
            "win24": make(win=24), "win48": make(win=48)}


if __name__ == "__main__":
    import json
    tickers = sorted({r["ticker"] for r in hist() if r["date"][:10] >= "1996-01-01"}
                     | members("1997-01-02"))
    out = rb.evaluate(ID, weights, tickers, BENCH, start="1997-01-01",
                      asset_class="stocks", source="sharadar", family="XSMOM", trials=10,
                      variants=VARIANTS,
                      notes=("Residual momentum (Blitz-Huij-Martens): FF3 residuals over 36 months "
                             "t-37..t-2, score = sum/sd of residuals t-12..t-2, top decile of the "
                             "point-in-time S&P 500, monthly, equal weight; Sharadar survivorship-free; "
                             "family XSMOM; promoted from I-2026-11-07-RESMOM"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
