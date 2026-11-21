"""R-2026-11-21-REBALFR — front-running institutional 60/40 rebalancing:
stocks vs 10-year Treasuries (Harvey, Mazzoleni & Melone, "The Unintended
Consequences of Rebalancing", NBER WP 33554, 2025; Fisher College WP
2025-03-001, version 2026-01-14). New idea (bonds desk, league round 2).

SOURCE: https://www.nber.org/papers/w33554 ; full text (2026-01-14 version)
https://www.edhec.edu/sites/default/files/2026-03/Scientific%20paper.%20ssrn-5122748.pdf
Published headline (1997-09-10 .. 2023-03-17, daily, S&P 500 and 10-year
Treasury note FUTURES): when a simulated 60/40 fund drifts overweight
equities, rebalancers sell stocks and buy bonds; S&P-minus-10y returns
are predictably lower next day. Table 1 col (1): Threshold signal -0.414
(se 0.115); Calendar x week4 -0.303 (se 0.081), i.e. calendar predictability
sits in the last 5 business days of the month. Table 6: a front-running
strategy (long S&P / short 10y or the reverse, weight = average of the two
modified signals) earns 10.20%/yr excess at 9.17% vol, Sharpe 1.11, alpha
t > 4 against CAPM/C4/FF5/HXZ; Sharpe 0.90 without 2008-09 and 2020-03;
"close to 1" net of Harvey et al. (2018) costs.

RULE (the paper's Section 4 / Appendix B, fixed before any run):
  * Daily returns R_sp, R_10 (harness: SPY and IEF adjusted closes).
  * Threshold portfolios: for each delta in 0.0%, 0.1%, ... 2.5% (26), a
    60/40 portfolio drifts with the day's returns; Threshold_delta(t) =
    drifted equity weight - 60%; if |deviation| >= delta it rebalances to
    60% at close t. Threshold(t) = average over the 26 deltas (eq. 2).
  * Calendar portfolio: drifts, Calendar(t) = drifted weight - 60%,
    rebalanced to 60% at the close of the last business day of the month.
  * Modified Calendar m(t) = sign(-Calendar(t)) if t is one of the last 5
    business days of its month (week4); on the first business day of a
    month m(t) = +sign(Calendar at the first day of the previous month's
    week4 window, i.e. day -4 counting the last day as 0) — the paper's
    "sign(Calendar Signal_-4)" reversal; else 0. ASSUMPTION (the text is
    terse): "-4" is read as that day; logged for the red team.
  * Weight w(t) = 0.5 * ( -Threshold(t)/1.5% + m(t) ).  Positions at close
    t: SPY +w, IEF -w (dollar-neutral; net weight 0, so the harness credits
    T-bills on the capital, matching the futures' excess-return design).

STEP 1 — REPLICATION (no evaluate call; printed, gates step 2). Source's
own period 1997-09-10..2023-03-17 (signals warm up from 1997-01-02).
IEF only exists from 2002-07, so the 10-year leg is FRED DGS10 turned into
a daily 10-year par-bond total return (carry y/252 - D*dy + 0.5*C*dy^2,
D/C of a semiannual 10y par bond at the prior yield); equity = SPY
adjusted close (total return). Futures excess-return difference ~= SPY
minus bond total return (the T-bill rate cancels). Pre-registered gate
(theme 33: sign and rough size at the source's own significance):
  (a) strategy annualised mean >= 5.1% (half of 10.2%) AND Sharpe >= 0.55
      (half of 1.11), gross of costs like Table 6 Panel A, AND
  (b) Calendar x week4 coefficient < 0 with White t <= -2.0 in the
      Table 1 col (1) regression (Ret_t+1 on Threshold, Calendar, week4,
      Calendar x week4, Momentum, Ret_t; Momentum = mean sign of trailing
      S&P-minus-10y returns over 11..20, 21, 42, 63, 126, 252 days).
Otherwise "harness/data suspect" and step 2 does not run (no trial spent).

STEP 2 — ETF TEST (one evaluate call). HYPOTHESIS: the rebalancing price
pressure the paper measures in futures is also earned on SPY/IEF, net of
3bp per unit of turnover, over 2002-08 .. vault (2024-10).
Benchmark: T-bills (dollar-neutral, market-neutral design). Costs 3bp
(bonds class; SPY/IEF spreads are ~1bp). Variants (4, the paper's own
robustness neighbours, App. D.6 / Fig. 3): delta grid 0-2.0%; delta grid
0.1-2.5% (no daily rebalancer); week4 = last 4 days; Threshold scaled by
2.0% instead of 1.5%. trials = 5 (new family R-2026-11-21-REBALFR; no
ledger row trades rebalancing flows — checked ideas.csv 2026-11-21).
Known caveats before the run: (1) the harness pays T-bills on short-sale
proceeds (a Schwab margin account earns less; futures would not); (2)
gross exposure reaches ~2-3x on big signals (futures-style; no financing
charge because net weight is 0); (3) the paper's edge concentrates in
2008-09 and 2020-03 (positive skew 5.2) — both inside our window.
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs T-bills, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating T-bills). The printed
leg decomposition (Threshold-only / Calendar-only) and the month-end IEF
split are learning read-outs, not tests, and do not change the verdict.
DATA TIMING: the weight decided at close i reads only SPY/IEF closes with
index <= i (returns of day i and earlier) and the exchange calendar
(whether bar i is among the last 5 / first trading days of its month —
holidays are scheduled in advance); it earns close i -> close i+1. In the
replication, DGS10 for date t is the H.15 close-of-day yield of day t,
used only for that day's realised bond return (never for the signal of an
earlier day). FRED fredgraph.csv, default Python user-agent, cached per
day in data/research/cache/fred_<id>.json (git-ignored).
"""
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-21-REBALFR"
EQ, BD = "SPY", "IEF"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
DELTAS = [k / 1000 for k in range(0, 26)]          # 0.0% .. 2.5% step 0.1%
REP_FROM, REP_TO = "1997-09-10", "2023-03-17"


def fred(sid):
    """FRED series as {date: float}, cached per day (default urllib agent)."""
    f = rb.CACHE / f"fred_{sid}.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == today:
            return j["v"]
    rows = urllib.request.urlopen(FRED + sid, timeout=60).read().decode().strip().splitlines()[1:]
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": today, "v": v}))
    return v


def sign(x):
    return (x > 0) - (x < 0)


class Engine:
    """Threshold and Calendar rebalancing signals, stepped one day at a time."""

    def __init__(self, deltas=DELTAS, week_n=5, scale=0.015):
        self.deltas, self.week_n, self.scale = deltas, week_n, scale
        self.wt = [0.6] * len(deltas)
        self.wc = 0.6
        self.cal_ref = None          # Calendar at the first day of this month's window
        self.cal_ref_prev = None     # ... of the previous month (used on day 1)

    @staticmethod
    def drift(w, rs, rb_):
        a, b = w * (1 + rs), (1 - w) * (1 + rb_)
        return a / (a + b) if a + b > 0 else w

    def step(self, rs, rb_, last_day, days_left, first_day):
        """rs/rb_: today's equity/bond returns; days_left counts today (1 = last day)."""
        sigs = []
        for k, d in enumerate(self.deltas):
            wd = self.drift(self.wt[k], rs, rb_)
            s = wd - 0.6
            sigs.append(s)
            self.wt[k] = 0.6 if abs(s) >= d else wd
        thr = sum(sigs) / len(sigs)
        wd = self.drift(self.wc, rs, rb_)
        cal = wd - 0.6
        self.wc = 0.6 if last_day else wd
        week4 = days_left <= self.week_n
        if first_day:
            self.cal_ref_prev, self.cal_ref = self.cal_ref, None
        if days_left == self.week_n:
            self.cal_ref = cal
        if week4:
            m = -sign(cal)
        elif first_day and self.cal_ref_prev is not None:
            m = sign(self.cal_ref_prev)
        else:
            m = 0
        w = 0.5 * (-thr / self.scale + m)
        return {"w": w, "thr": thr, "cal": cal, "week4": week4, "m": m}


def month_info(dates, i):
    """(is last trading day of its month, trading days left incl. i, is first day)."""
    ym = dates[i][:7]
    j = i
    while j + 1 < len(dates) and dates[j + 1][:7] == ym:
        j += 1
    last = j == i and i + 1 < len(dates)
    first = i == 0 or dates[i - 1][:7] != ym
    return last, j - i + 1, first


def make(deltas=DELTAS, week_n=5, scale=0.015, leg="both"):
    st = {"i": -1, "eng": None, "out": None}

    def weights(i, dates, px):
        if i <= st["i"] or st["eng"] is None:
            st.update(i=-1, eng=Engine(deltas, week_n, scale), out=None)
        for k in range(st["i"] + 1, i + 1):
            st["i"] = k
            if k == 0:
                continue
            a, b, c, d = px[EQ][k - 1], px[EQ][k], px[BD][k - 1], px[BD][k]
            if not (a and b and c and d):
                st["out"] = None
                continue
            last, left, first = month_info(dates, k)
            st["out"] = st["eng"].step(b / a - 1, d / c - 1, last, left, first)
        o = st["out"]
        if not o:
            return {}
        w = (0.5 * -o["thr"] / scale if leg == "thr" else
             0.5 * o["m"] if leg == "cal" else o["w"])
        return {EQ: w, BD: -w} if w else {}
    return weights


weights = make()


# ── step 1: replication on the source's period ───────────────────────────────
def par_dur_conv(y, n=20):
    """Modified duration and convexity of a 10-year semiannual par bond at annual yield y."""
    h = y / 2
    cfs = [(k, y / 2 + (1 if k == n else 0)) for k in range(1, n + 1)]
    pv = [cf / (1 + h) ** k for k, cf in cfs]
    price = sum(pv)
    dmod = sum((k / 2) * v for (k, _), v in zip(cfs, pv)) / price / (1 + h)
    conv = sum(cf * (k / 2) * ((k + 1) / 2) / (1 + h) ** (k + 2) for k, cf in cfs) / price
    return dmod, conv


def white_ols(y, xs):
    """OLS with heteroskedasticity-consistent (White HC0) t-stats."""
    n, k = len(y), len(xs) + 1
    X = [[1.0] + [x[i] for x in xs] for i in range(n)]
    xtx = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    beta = rb._solve(xtx, [sum(X[r][i] * y[r] for r in range(n)) for i in range(k)])
    e = [y[r] - sum(beta[j] * X[r][j] for j in range(k)) for r in range(n)]
    inv = [rb._solve(xtx, [1.0 if i == j else 0.0 for i in range(k)]) for j in range(k)]
    meat = [[sum(e[r] ** 2 * X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    cov = [[sum(inv[i][a] * meat[a][b] * inv[b][j] for a in range(k) for b in range(k))
            for j in range(k)] for i in range(k)]
    return beta, [beta[j] / math.sqrt(cov[j][j]) if cov[j][j] > 0 else 0.0 for j in range(k)]


def replication():
    dates, px = rb.prices([EQ], "1997-01-01")
    y10 = fred("DGS10")
    ys = sorted(y10)
    yv, last, p = {}, None, 0
    for d in dates:                       # last DGS10 print on or before d
        while p < len(ys) and ys[p] <= d:
            last = y10[ys[p]] / 100
            p += 1
        yv[d] = last
    eng = Engine()
    rows = []                             # (date, signals at t, diff return t)
    for i in range(1, len(dates)):
        if dates[i] > REP_TO or yv[dates[i - 1]] is None:
            continue
        y0, y1 = yv[dates[i - 1]], yv[dates[i]]
        dm, cv = par_dur_conv(y0)
        dy = y1 - y0
        r10 = y0 / 252 - dm * dy + 0.5 * cv * dy * dy
        rs = px[EQ][i] / px[EQ][i - 1] - 1
        last, left, first = month_info(dates, i)
        o = eng.step(rs, r10, last, left, first)
        rows.append((dates[i], o, rs - r10))
    strat, Y, THR, CAL, W4, CW4, MOM, RET = [], [], [], [], [], [], [], []
    wins = list(range(11, 21)) + [21, 42, 63, 126, 252]
    diffs = [r[2] for r in rows]
    for t in range(len(rows) - 1):
        d, o, ret = rows[t]
        if d < REP_FROM:
            continue
        nxt = rows[t + 1][2]
        strat.append(o["w"] * nxt)
        Y.append(nxt)
        THR.append(o["thr"])
        CAL.append(o["cal"])
        W4.append(1.0 if o["week4"] else 0.0)
        CW4.append(o["cal"] * (1.0 if o["week4"] else 0.0))
        MOM.append(sum(sign(sum(diffs[t - k + 1:t + 1])) for k in wins) / len(wins))
        RET.append(ret)
    mu = sum(strat) / len(strat)
    sd = math.sqrt(sum((x - mu) ** 2 for x in strat) / (len(strat) - 1))
    sk = sum((x - mu) ** 3 for x in strat) / len(strat) / sd ** 3
    beta, tv = white_ols(Y, [THR, CAL, W4, CW4, MOM, RET])
    ann, vol = 252 * mu, sd * math.sqrt(252)
    sh = ann / vol if vol else 0.0
    ok = ann >= 0.051 and sh >= 0.55 and beta[4] < 0 and tv[4] <= -2.0
    return {"period": f"{REP_FROM}..{REP_TO}", "days": len(strat),
            "bond_leg": "FRED DGS10 10y par-bond daily return", "equity_leg": "SPY adj close",
            "strategy_ann_mean_pct": round(100 * ann, 2), "strategy_vol_pct": round(100 * vol, 2),
            "strategy_sharpe": round(sh, 3), "strategy_skew": round(sk, 2),
            "coef_threshold": round(beta[1], 4), "t_threshold": round(tv[1], 2),
            "coef_calendar_x_week4": round(beta[4], 4), "t_calendar_x_week4": round(tv[4], 2),
            "paper": "Table 6: 10.20%/yr, vol 9.17%, Sharpe 1.11, skew 5.23; Table 1(1): "
                     "Threshold -0.414 (t -3.6), Calendar x week4 -0.303 (t -3.75)",
            "passes": bool(ok)}


# ── learning read-outs (not tests: no evaluate call, no trial) ───────────────
def readouts():
    dates, px = rb.prices([EQ, BD], "2002-08-01")
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    out = {}
    for leg in ("thr", "cal"):
        r, _ = rb.simulate(make(leg=leg), dates, px, rf, 3.0)
        out[f"{leg}_only_sharpe_vs_tbills"] = round(rb.sharpe(r, rf[1:]), 3)
        out[f"{leg}_only_cagr"] = round(rb.cagr(r), 4)
    # does the EOMTSY month-end Treasury gain depend on rebalancing direction?
    eng, pos, neg = Engine(), [], []
    for i in range(1, len(dates) - 1):
        a, b, c, d = px[EQ][i - 1], px[EQ][i], px[BD][i - 1], px[BD][i]
        if not (a and b and c and d):
            continue
        last, left, first = month_info(dates, i)
        o = eng.step(b / a - 1, d / c - 1, last, left, first)
        if o["week4"]:
            nxt = px[BD][i + 1] / px[BD][i] - 1 - rf[i + 1]
            (pos if o["cal"] > 0 else neg).append(nxt)
    out["ief_excess_bp_next_day_week4_cal_pos"] = round(1e4 * sum(pos) / max(len(pos), 1), 2)
    out["ief_excess_bp_next_day_week4_cal_neg"] = round(1e4 * sum(neg) / max(len(neg), 1), 2)
    out["n_pos_neg"] = [len(pos), len(neg)]
    return out


if __name__ == "__main__":
    rep = replication()
    print(json.dumps({"replication": rep}, indent=1))
    if not rep["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "harness/data suspect: the rebalancing front-running strategy did "
                                    "not replicate on SPY + FRED 10y 1997-2023 (pre-registered gate)"},
                         indent=1))
        sys.exit(0)
    r = rb.evaluate(ID, weights, [EQ, BD], None, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"DELTA_0_20": make(deltas=[k / 1000 for k in range(0, 21)]),
                              "DELTA_01_25": make(deltas=[k / 1000 for k in range(1, 26)]),
                              "WEEK_LAST4": make(week_n=4),
                              "THR_SCALE_2": make(scale=0.02)},
                    notes="SPY +w / IEF -w, w = 0.5*(-Threshold/1.5% + modified Calendar); "
                          "Harvey-Mazzoleni-Melone 2025 rebalancing front-run; bench T-bills; "
                          f"replication 1997-2023 Sharpe {rep['strategy_sharpe']} "
                          f"(paper 1.11), cal x week4 t {rep['t_calendar_x_week4']}")
    r["replication"] = rep
    r["readouts_not_tests"] = readouts()
    print(json.dumps(r, indent=1))
