"""I-2026-11-21-BTCDVMP — sourced-idea VARIANT: downside-volatility-managed
Bitcoin (Wang & Yan, JBF 2021, applied to BTC). Scripts the queued ledger row
I-2026-11-11-BTCDVMP (new id per the league naming rule).

Sources: Wang & Yan, "Downside risk and the performance of volatility-managed
portfolios", JBF 131 (2021) https://doi.org/10.1016/j.jbankfin.2021.106198 —
replicated first on the source's own data in R-2026-11-21-DVOLMKT (this
script REFUSES to run its test unless that replication held). Baur & Dimpfl,
Economics Letters 173 (2018) https://ideas.repec.org/a/eee/ecolet/v173y2018icp148-151.html
(crypto volatility rises MORE after positive shocks — the inverse of equities).
Varies I-2026-11-10-BTCVMP (total-variance scaling, FAIL: Sharpe 0.99 vs
1.04, confidence 34%).

Hypothesis (written before any run): BTCVMP failed because total volatility
in BTC spikes in RALLIES (Baur-Dimpfl), so scaling by it cut the best months.
Downside volatility (negative days only) is high in crashes and capitulations
(2018, Mar 2020, 2022) but not in up-legs; Wang-Yan find it also predicts
LOWER future returns (return timing, not just vol timing). So scaling BTC by
inverse downside vol should cut crash months without cutting rallies and beat
BTC buy-and-hold on Sharpe. Counter-hypothesis: BTC's downside-vol spikes come
at the bottoms (Mar 2020, Jun/Nov 2022) and are followed by the sharpest
rebounds, so the rule de-risks just before recoveries (theme 13's failure
mode) and, like BTCVMP, lands below buy-and-hold.

RULE (fixed before any run; the source's construction, long-only):
  * At the close of each month-end BTC bar (last calendar day; Yahoo 00:00 UTC
    bar): sigma_Down,m = sqrt(sum of squared NEGATIVE daily BTC simple returns
    inside month m); if month m has fewer than 3 negative days, the negative
    days of months m and m-1 are used (source rule).
  * w = min(1, median(last 36 sigma_Down readings incl. this one) /
    sigma_Down,m); the rest in T-bills. Volatility, not variance, scaling
    (source footnote 7). Fewer than 36 readings: w = 1 (warm-up = bench).
    The median reference replaces the source's full-sample constant c (not
    known in real time); the cap at 1 = no leverage on BTC.
  * BTC quantity fixed between decisions; a missing month-end bar -> decide
    on the next month's first bar (catch-up), as in BTCVMP.
DATA TIMING: the decision on bar i reads only BTC bars <= i (the month just
closed); weights decided at bar i's close earn bar i -> i+1 (harness).
Benchmark BTC-USD buy & hold (RESEARCH.md §4; for a standalone BTC rule the
static allocation IS buy & hold — theme 22). 25bp per unit of turnover.
Window 2014-09-17 -> vault (sealed from 2024-11-01).
Variants: 24- and 60-month median; variance scaling (the ledger row's
original rule); weekly (every Sunday: last 30 bars, median of last 156
weekly readings); Wang-Yan fixed-weight combination (50% managed + 50%
unmanaged: w = 0.5 + 0.5 w_dvmp).
PASS CRITERION (pre-registered): the harness verdict vs BTC-USD (99%
confidence + held-out win + DSR >= 0.95 + t >= 3 + 2x costs + >= 70% of the
5 variants beat BTC). Learning read-out (pre-registered, not a PASS):
"downside beats total on BTC" iff this rule's Sharpe > the identical
construction scaled by TOTAL vol (printed, rb.simulate on the same window —
a diagnostic, not a separate test). If it PASSES, the next test is the BTC10
sleeve with this rule in its 10% slot vs the static BTC10 (theme 22).
trials: 17 = btc-vol-managed's 5 (BTCVMP) + 6 here + btc-trend-vol's 6
(BTCTRENDVOL, the vol x trend parent), as BTCVMP counted; family
btc-vol-managed. No factor gate.
"""
import importlib.util
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

IDEA = "I-2026-11-21-BTCDVMP"
REPL = "R-2026-11-21-DVOLMKT"
BTC = "BTC-USD"
START = "2014-09-17"
COST = 25.0


def _last_day(d):
    x = date.fromisoformat(d)
    return (x + timedelta(days=1)).month != x.month


def _median(x):
    s = sorted(x)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def _sigma(rets, prev, mode):
    """Source Eq. 2-3: sqrt of summed squares; downside uses negative days,
    adding the previous block's negative days when fewer than 3."""
    if mode == "total":
        return math.sqrt(sum(r * r for r in rets)) if rets else None
    neg = [r for r in rets if r < 0]
    if len(neg) < 3:
        neg = neg + [r for r in prev if r < 0]
    return math.sqrt(sum(r * r for r in neg)) if neg else None


def make(n_ref=36, power=1.0, weekly=False, win=30, mode="down", mix=0.0):
    """mix = share held unmanaged (Wang-Yan fixed-weight combination)."""
    st = {}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(w={BTC: 1.0}, sig=[], cur=[], prev=[], hist=[], m=None)
            return dict(st["w"])
        st["w"] = drift(st["w"], i, px)
        a, b = px[BTC][i - 1], px[BTC][i]
        r = (b / a - 1) if (a and b) else None
        d = dates[i]
        decide = False
        if weekly:
            if r is not None:
                st["hist"].append(r)
            if date.fromisoformat(d).weekday() == 6 and len(st["hist"]) >= 2 * win:
                s = _sigma(st["hist"][-win:], st["hist"][-2 * win:-win], mode)
                if s:
                    st["sig"].append(s)
                    decide = True
        else:
            if d[:7] != dates[i - 1][:7] and st["m"] != dates[i - 1][:7] and st["cur"]:
                # catch-up: last month had no month-end bar; close it now
                s = _sigma(st["cur"], st["prev"], mode)
                st["m"], st["prev"], st["cur"] = dates[i - 1][:7], st["cur"], []
                if s:
                    st["sig"].append(s)
                    decide = True
            if d[:7] != dates[i - 1][:7] and st["cur"]:
                st["prev"], st["cur"] = st["cur"], []   # a new month's returns start here
            if r is not None:
                st["cur"].append(r)
            if _last_day(d):
                s = _sigma(st["cur"], st["prev"], mode)
                st["m"], st["prev"], st["cur"] = d[:7], st["cur"], []
                if s:
                    st["sig"].append(s)
                    decide = True
        if decide:
            ref = st["sig"][-n_ref:]
            if len(ref) == n_ref and ref[-1] > 0:
                w = min(1.0, (_median(ref) / ref[-1]) ** power)
            else:
                w = 1.0                   # warm-up = the benchmark
            st["w"] = {BTC: mix + (1 - mix) * w}
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "ref24": make(n_ref=24),
    "ref60": make(n_ref=60),
    "variance_scaling": make(power=2.0),
    "weekly": make(n_ref=156, weekly=True),
    "fixed_weight_50": make(mix=0.5),
}


def replication_ok():
    p = Path(__file__).resolve().parent / f"{REPL}.py"
    spec = importlib.util.spec_from_file_location("dvolmkt", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    r = mod.run()
    rep = mod.replicated(r)
    return rep["replicated"], {"replication": rep, "numbers": r}


def diagnostic():
    """Down vs total vol (identical construction) and buy & hold, same window."""
    d, p = rb.prices([BTC], START)
    keep = sum(1 for x in d if x < rb.VAULT_FROM)
    d, p = d[:keep], {s: v[:keep] for s, v in p.items()}
    rb.PPY = rb.periods_per_year(d)
    rf = rb.tbill(d)
    out = {}
    for name, fn in [("down_vol", make()), ("total_vol", make(mode="total")),
                     ("buy_hold", lambda i, dd, px: {BTC: 1.0})]:
        r, to = rb.simulate(fn, d, p, rf, COST)
        out[name] = {"cagr": round(rb.cagr(r), 4), "sharpe": round(rb.sharpe(r, rf[1:]), 3),
                     "maxdd": round(rb.max_dd(r), 4),
                     "turnover_per_yr": round(to / (len(r) / rb.PPY), 2)}
    out["downside_beats_total_on_btc"] = out["down_vol"]["sharpe"] > out["total_vol"]["sharpe"]
    return out


if __name__ == "__main__":
    ok, why = replication_ok()
    if not ok:
        print(json.dumps({"idea": IDEA, "skipped": True,
                          "reason": "replication of the source failed (league rule 1)", "detail": why},
                         indent=1))
        sys.exit(0)
    res = rb.evaluate(
        IDEA, weights, [BTC], bench=BTC, start=START,
        asset_class="crypto", cost_bps=COST, trials=17, family="btc-vol-managed",
        variants=VARIANTS,
        notes="Wang-Yan downside-vol management on BTC (replicated on French MKT 1926-2018 in "
              "R-2026-11-21-DVOLMKT): month-end w = min(1, median of last 36 monthly downside vols / this "
              "month's), downside vol = sqrt(sum of squared negative daily returns; <3 negative days -> add "
              "last month's), rest T-bills, quantity fixed between; bench BTC-USD; 25bp; variants 24/60-month "
              "median, variance scaling, weekly, 50% fixed-weight mix; trials 17 family btc-vol-managed; "
              "vault sealed from 2024-11")
    print(json.dumps({"evaluate": res, "diagnostic": diagnostic(), "replication": why}, indent=1))
