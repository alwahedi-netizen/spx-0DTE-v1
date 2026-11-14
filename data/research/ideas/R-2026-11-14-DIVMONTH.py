"""R-2026-11-14-DIVMONTH — the dividend-month premium (Hartzmark-Solomon):
long the S&P 500 stocks expected to go ex-dividend this month, short the
other recent payers, dollar-neutral, on point-in-time Sharadar data.

Promoted from the queue row I-2026-11-08-DIVMONTH (scored 60, blocked by
the 5-script cap and "needs the Sharadar actions table" — checked
2026-11-14: rb.sharadar("actions", ticker=...) returns dividend ex-dates).
Same mechanism, first test; this script uses the paper's own hedged
construction, the queue row's long-only form is I-2026-11-14-DIVMONTHLO.
Source: Hartzmark & Solomon (2013) "The Dividend Month Premium", J.
Financial Economics 109(3) 640-660
(https://econpapers.repec.org/RePEc:eee:jfinec:v:109:y:2013:i:3:p:640-660);
draft summary with the exact definitions: CXO Advisory 2011-10-13
(https://www.cxoadvisory.com/?p=16926). CRSP 1927-2009. A firm is EXPECTED
to pay in month m if it paid 3, 6, 9 or 12 months earlier (83-88% hit
rate). HEADLINE: long expected payers / short recent payers NOT expected
this month earns 0.37%/month equal-weighted (0.29% value-weighted) factor-
adjusted; long expected / short all others 0.53% EW (0.32% VW); premium
persists across subperiods, larger in high-yield and less-liquid stocks.

RATIONALE (fixed before any run): dividend-seeking investors (retail,
income funds) buy ahead of the ex-date and sell after it, creating
predictable price pressure in the month a dividend is expected. The
"other payers" short leg is the paper's cleanest control: same type of
firm (payers), different month — so the spread is the calendar pressure,
not a payer/value tilt. Expected failure regime: large liquid names absorb
the pressure (our universe is all large caps — expect a smaller spread
than the CRSP EW figure), and turnover (~3 units a month) eats a thin
edge (theme 5).

REPLICATION FIRST (RESEARCH.md § LEAGUE rule 1): this run IS the paper's
hedged construction on our universe, so one run reproduces and tests. The
script also prints the replication check on the overlap with the source's
sample (from rb.simulate on the same rule; no extra trial):
  REPLICATION PASS iff the mean monthly spread (net of the 5bp costs,
  over T-bills) over 1998-01..2009-12 is >= +0.10%/month (sign right and
  about a third of the paper's VW 0.29% — large caps only, net of costs).
  If it fails: "harness/data suspect" and I-2026-11-14-DIVMONTHLO refuses.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the signal day dates[i-1]
    (ASSETGROW's members()), priced on it.
  * Dividends: Sharadar ACTIONS rows with action "dividend" (date = the
    ex-date), only those dated <= dates[i-1].
  * At the last close of each month (trade day dates[i]; the coming month
    m = the month of dates[i+1]): EXPECTED = members with an ex-date in
    calendar month m-3, m-6, m-9 or m-12; OTHERS = members with an ex-date
    in m-12..m-1 (and <= dates[i-1]) that are not EXPECTED.
  * Weights: +1/nE on each EXPECTED, -1/nO on each OTHER (dollar-neutral;
    short proceeds earn T-bills — theme 28); hold the month, drift with
    prices. Needs >= 10 names in each leg, else cash for the month.
  * Variants (robustness gate): expected-by lags {12} only, {3} only,
    {3, 12}; and short leg = ALL other members (the paper's 0.53% form).
  * Benchmark T-bills (bench=None), 5bp/side, 1998-01 -> vault, strict
    bar + FF5+Mom alpha gate. Family "dividend-month" (new): trials 5.
  * Borrow fees on the short leg not charged (S&P 500 general collateral,
    ~0.25-0.5%/yr — haircut the result).
PASS CRITERION (written before any run): harness verdict PASS with every
world-class gate on 1998-01 -> 2024-10, AND the replication check passes.

DATA-TIMING: signal day dates[i-1]: ex-dates <= dates[i-1] (the lags only
look at months m-3 ... m-12, all fully in the past), membership and price
on dates[i-1]. px[.][i] only drifts the held book. Weights decided at close
i earn close i -> close i+1; the book is formed at the last close of month
m-1 and earns month m.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("assetgrow", _here.with_name("R-2026-11-08-ASSETGROW.py"))
ag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ag)                    # members(), all_tickers()

ID = "R-2026-11-14-DIVMONTH"
START = "1998-01-01"
FAMILY = "dividend-month"
_DIV = {}


def _mi(ym):
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def ex_months(t):
    """{month index: earliest dividend ex-date in that month} for ticker t
    (Sharadar ACTIONS)."""
    if t not in _DIV:
        try:
            rows = rb.sharadar("actions", None, ticker=t)
        except Exception:  # noqa: BLE001 — no actions = no dividends known
            rows = []
        out = {}
        for r in rows:
            d = (r.get("date") or "")[:10]
            if r.get("action") == "dividend" and d:
                k = _mi(d[:7])
                out[k] = min(out.get(k, d), d)
        _DIV[t] = out
    return _DIV[t]


_CL = {}


def classify(sd, m, lags=(3, 6, 9, 12)):
    """(expected, other recent payers) among members on signal day sd for
    coming month m ('YYYY-MM'); only ex-dates <= sd count."""
    key = (sd, m, tuple(lags))
    if key in _CL:
        return _CL[key]
    mm = _mi(m)
    want = {mm - k for k in lags}
    exp, oth = [], []
    for t in ag.members(sd):
        em = ex_months(t)
        months = {k for k in range(mm - 12, mm) if k in em and em[k] <= sd}
        if months & want:
            exp.append(t)
        elif months:
            oth.append(t)
    _CL[key] = (sorted(exp), sorted(oth))
    return _CL[key]


def make_monthly(select, warmup=None):
    """Re-form at each month's last close via select(dates, i, px) -> weights
    or None (then hold cash / warmup); drift in between (signed NAV drift)."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if i > 0 and i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            w = select(dates, i, px) or {}
            w = {t: x for t, x in w.items() if px[t][i] is not None}
            st["w"], st["base"] = w, {t: px[t][i] for t in w}
            st["last"] = dict(st["base"])
            return dict(w)
        if "w" not in st:
            return dict(warmup) if warmup else {}
        val = {}
        for t, w0 in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            val[t] = w0 * st["last"][t] / st["base"][t]
        nav = 1.0 + sum(val[t] - st["w"][t] for t in val)
        return {t: v / nav for t, v in val.items()} if nav > 0 else {}
    return weights


def make_weights(lags=(3, 6, 9, 12), short_all=False, min_leg=10):
    def select(dates, i, px):
        sd, m = dates[i - 1], dates[i + 1][:7]
        exp, oth = classify(sd, m, lags)
        exp = [t for t in exp if t in px and px[t][i - 1] is not None]
        if short_all:
            es = set(exp)
            oth = [t for t in ag.members(sd) if t not in es]
        oth = [t for t in oth if t in px and px[t][i - 1] is not None]
        if len(exp) < min_leg or len(oth) < min_leg:
            return None
        w = {t: 1.0 / len(exp) for t in exp}
        w.update({t: -1.0 / len(oth) for t in oth})
        return w
    return make_monthly(select)


weights = make_weights()
VARIANTS = {"lag12": make_weights((12,)), "lag3": make_weights((3,)),
            "lag3_12": make_weights((3, 12)), "short_all": make_weights(short_all=True)}


def replication_check(weights_fn=None, threshold=0.0010):
    weights_fn = weights_fn or make_weights()
    dates, px = rb.sharadar_prices(ag.all_tickers(START), START)
    keep = sum(1 for d in dates if d < "2010-01-01")
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(weights_fn, dates, px, rf, rb.COST_BPS["stocks"])
    mx = {}
    for k, r in enumerate(rets):
        mx[dates[k + 1][:7]] = mx.get(dates[k + 1][:7], 0.0) + r - rf[k + 1]
    xs = list(mx.values())[1:]                       # drop the partial first month
    mu = sum(xs) / len(xs)
    sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
    ok = mu >= threshold
    return {"source_headline": "CRSP 1927-2009: expected payers minus other payers +0.37%/month EW, +0.29% VW",
            "ours_1998_2009": {"months": len(xs), "mean_monthly_net": round(mu, 5),
                               "t": round(mu / sd * len(xs) ** 0.5, 2) if sd else None},
            "threshold": threshold, "replicated": ok,
            "verdict": "REPLICATED" if ok else "harness/data suspect"}


if __name__ == "__main__":
    rep = replication_check()
    print("REPLICATION", json.dumps(rep))
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), None, start=START, asset_class="stocks", trials=5,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Hartzmark-Solomon dividend month premium: long point-in-time S&P 500 members with a "
               "Sharadar ex-dividend date 3/6/9/12 months before the coming month, short the other "
               "payers of the last 12 months, equal weight, dollar-neutral, monthly, bench T-bills; "
               "variants lag12/lag3/lag3_12/short-all; borrow fees not charged; promoted from "
               "I-2026-11-08-DIVMONTH; replication " + rep["verdict"] + " (1998-2009 mean "
               + str(rep["ours_1998_2009"]["mean_monthly_net"]) + "/month vs paper +0.29..0.37%)"))
    out["replication"] = rep
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
