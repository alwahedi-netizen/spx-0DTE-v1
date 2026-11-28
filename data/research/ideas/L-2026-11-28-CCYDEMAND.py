"""L-2026-11-28-CCYDEMAND — is the commodity-currency signal a DEMAND signal or
just the dollar? CCYCMD's signal traded as long DBC / short GLD (and the
reverse), dollar-neutral. League round 3 (2026-11-28), commodities desk.
Lab original (RESEARCH.md §2b). New ledger row; varies R-2026-11-09-CCYCMD
(potential 4; one of CMDBOOK's three surviving sleeves).

WHY THIS TEST (written before any run): Chen, Rogoff & Rossi, "Can Exchange
Rates Forecast Commodity Prices?", QJE 125(3) 2010
(https://econpapers.repec.org/RePEc:oup:qjecon:v:125:y:2010:i:3:p:1145-1194)
argue that commodity-exporter currencies are forward-looking prices of future
export earnings, so they move before commodity prices. Our long/flat form
(R-2026-11-09-CCYCMD: DBC while the AUD/CAD/CLP/NZD/ZAR basket rose vs USD over
3 months) earned +5.4%/yr vs DBC +0.6% (conf 94%, potential 4). But "commodity
currencies up vs USD" is also "the dollar down", and a weak dollar lifts every
USD-priced commodity mechanically. If CCYCMD is only a dollar/beta timer, it is
a weaker block than the book assumes. Gold is the cleanest control: it is
priced in USD (it shares the dollar effect) but is a monetary/haven asset, not
a cyclical input whose demand the exporters' earnings discount. Spreading DBC
against GLD cancels most of the common dollar move and leaves the cyclical-
demand component — the part of the paper's story that should carry an edge.
One change only versus CCYCMD (the gold leg); signal, basket and 3-month
horizon are imported unchanged, plus a pre-registered bad-print guard
(theme 37).
NOT A REPLICATION: the paper is a quarterly forecasting regression, not a
trading rule; the replication-equivalent is CCYCMD itself (round 2026-11-09).
Known caveat stated before the run: Australia and South Africa are large gold
exporters, so AUD and ZAR also respond to gold; the "exgold" variant (CAD,
CLP, NZD: oil, copper, dairy/ag) is the cleaner demand basket and is run as a
counted variant, not as the rule.

HYPOTHESIS (written before any run): after the commodity-currency basket has
risen over 3 months, cyclical commodities (DBC) outperform gold over the next
month; after it has fallen, gold outperforms DBC. Long DBC / short GLD in the
first state and long GLD / short DBC in the second earns a positive excess
return over T-bills.

PASS CRITERION (pre-registered): research_bt verdict PASS vs T-bills (bench
None: dollar-neutral book), all §0 gates with the family's lifetime trials
(16 + 1 + 5 = 22), >= 70% of the 5 neighbours above T-bills (4 of 5).
DEMAND READ-OUT (pre-registered, printed separately; rb.simulate on the same
calendar, no result file, no trial):
  DEMAND SIGNAL     spread book Sharpe > 0, harness confidence >= 0.90 and the
                    held-out (last 30%) Sharpe > 0;
  PARTIAL           spread book Sharpe > 0, otherwise short of DEMAND SIGNAL;
  DOLLAR/BETA ONLY  spread book Sharpe <= 0 while the guarded long/flat CCYCMD
                    (DBC or T-bills, same signal) beats buy-and-hold DBC on
                    Sharpe — i.e. CCYCMD works only through the common move;
  NO SIGNAL         anything else.
  Also printed (diagnostic, after the fact): mean next-month DBC-minus-GLD
  return in up-signal vs down-signal months, and the static long DBC / short
  GLD book (what the spread earns with no signal).

RULE (fixed before any run):
  at each month-end close i (date D; next bar falls in a new month):
    for each of AUDUSD, NZDUSD (as quoted) and USDCAD, USDCLP, USDZAR
    (inverted): x = log change of the currency's USD value between the FX
    level "strictly before D" and the FX level "strictly before the month-end
    date 3 months earlier" (CCYCMD's dates, unchanged);
      FX level strictly before d = the last Yahoo bar dated < d; GUARD
      (theme 37, pre-registered): if that bar differs from the median of the
      last 5 bars dated < d by more than 3%, the median is used instead
      (single-bar spike-and-revert prints, e.g. USDCLP 2014-04-09 and
      2016-12-21 at -99%; uses only bars dated before d);
      |x| > 25% is still dropped as a bad tick (CCYCMD's own filter);
    s = mean of the available x; need >= 3 currencies AND DBC and GLD priced
    at i, else T-bills;
    s > 0: DBC +1.0, GLD -1.0          (demand rising: long cyclicals vs gold)
    s <= 0: DBC -1.0, GLD +1.0         (demand falling: long gold vs cyclicals)
  SIZING (assert in code, printed as an audit): 100% long / 100% short, gross
  2.0, net 0.0 on every live month; T-bills on capital and short proceeds
  (harness fix 2; a retail account would not earn T-bills on short proceeds).
  Held to the next month-end.
Benchmark: T-bills (bench None). Costs 5bp (DBC and GLD are liquid). No borrow
fee modelled (both borrow cheaply). Start 2006-03-01 (as CCYCMD; DBC lists
2006-02, GLD 2004-11; first signal ~2006-06). Ends at the vault (2024-10-31).
Includes 2008, 2011-15 (gold bust), 2020, 2022.
DATA-TIMING: price signals none (the book reads DBC/GLD closes at i only to
confirm they are priced); the FX side data are bars dated STRICTLY BEFORE the
decision date D (Yahoo `=X` "close" is ~19:00 ET, after the US close — theme
30 — so a bar dated D is never read) and strictly before the month-end date 3
months earlier; FX is loaded on its own calendar and never enters the
simulated universe (theme 12/17); the month-end test peeks only at
dates[i+1]'s MONTH; weights decided at close i earn close i -> close i+1.
Variants (CCYCMD's own neighbours, not re-chosen): horizon 1, 2, 4, 6 months;
plus the ex-gold-exporter basket (CAD, CLP, NZD) at 3 months.
FAMILY "ccy-predicts-cmd" (same hypothesis: commodity currencies forecast
commodities) -> lifetime trials 16 + 1 + 5 = 22.
Data checked 2026-11-28 (prices only): AUDUSD from 2006-05-16 on Yahoo (so the
basket has 4 currencies until 2006-08, >= 3 needed); spike scan of the five
pairs found AUD only real 2008-10/11 crisis moves, USDCLP noisy 2004-07 and two
-99% prints (2014-04-09, 2016-12-21), USDZAR bad prints only inside the vault
(2024-11-14, 2025-01-14..16); no gaps > 6 days.
"""
import bisect
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

FX = {"AUDUSD=X": +1, "NZDUSD=X": +1, "USDCAD=X": -1, "USDCLP=X": -1, "USDZAR=X": -1}
EXGOLD = ("NZDUSD=X", "USDCAD=X", "USDCLP=X")
BAD = 0.25
GUARD_N, GUARD_TOL = 5, 0.03
SYMS = ["DBC", "GLD"]
START = "2006-03-01"
SIDE = {}
AUDIT = {"months_live": 0, "max_long": 0.0, "max_short": 0.0, "max_abs_net": 0.0, "guard_used": 0}


def _load():
    if not SIDE:
        d, p = rb.prices(list(FX), "2003-01-01")
        for s in FX:
            pts = [(x, v) for x, v in zip(d, p[s]) if v]
            SIDE[s] = ([x for x, _ in pts], [v for _, v in pts])
    return SIDE


def _before(s, d, audit=False):
    """FX level from bars dated strictly before d, with the spike guard."""
    ds, vs = _load()[s]
    k = bisect.bisect_left(ds, d)
    if k <= 0:
        return None
    last = vs[k - 1]
    win = sorted(vs[max(0, k - GUARD_N):k])
    med = win[len(win) // 2]
    if med > 0 and abs(last / med - 1) > GUARD_TOL:
        if audit:
            AUDIT["guard_used"] += 1
        return med
    return last


def signal(me, months, pairs, audit=False):
    """Mean log change of the basket's USD value; None if < 3 currencies."""
    if len(me) <= months:
        return None
    now_d, then_d = me[-1], me[-1 - months]
    xs = []
    for s in pairs:
        a, b = _before(s, then_d, audit), _before(s, now_d, audit)
        if a and b and a > 0 and b > 0:
            x = FX[s] * math.log(b / a)
            if abs(x) <= BAD:
                xs.append(x)
    return sum(xs) / len(xs) if len(xs) >= 3 else None


def make(months=3, pairs=tuple(FX), mode="spread", audit=False):
    """mode 'spread' = the rule; 'longflat' = guarded CCYCMD (DBC or T-bills);
    'static' = always long DBC / short GLD (control)."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["me"] = []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        st["me"].append(dates[i])
        w = {}
        if px["DBC"][i] and px["GLD"][i]:
            if mode == "static":
                w = {"DBC": 1.0, "GLD": -1.0}
            else:
                s = signal(st["me"], months, pairs, audit)
                if s is not None:
                    if mode == "longflat":
                        w = {"DBC": 1.0} if s > 0 else {}
                    else:
                        w = {"DBC": 1.0, "GLD": -1.0} if s > 0 else {"DBC": -1.0, "GLD": 1.0}
        if mode != "longflat":
            long_ = sum(x for x in w.values() if x > 0)
            short = -sum(x for x in w.values() if x < 0)
            assert long_ <= 1.0 + 1e-9 and short <= 1.0 + 1e-9 and abs(long_ - short) < 1e-9, w
            if audit and w:
                AUDIT["months_live"] += 1
                AUDIT["max_long"] = max(AUDIT["max_long"], long_)
                AUDIT["max_short"] = max(AUDIT["max_short"], short)
                AUDIT["max_abs_net"] = max(AUDIT["max_abs_net"], abs(long_ - short))
        st["w"] = w
        return w
    return weights


weights = make()


def split_diag(dates, px):
    """Diagnostic: next-month DBC-minus-GLD return by signal state (outcome read after the fact)."""
    ends = [i for i in range(len(dates) - 1) if dates[i + 1][:7] != dates[i][:7]]
    me, up, dn = [], [], []
    for a, b in zip(ends, ends[1:]):
        me.append(dates[a])
        s = signal(me, 3, tuple(FX))
        if s is None or not (px["DBC"][a] and px["GLD"][a] and px["DBC"][b] and px["GLD"][b]):
            continue
        sp = (px["DBC"][b] / px["DBC"][a]) - (px["GLD"][b] / px["GLD"][a])
        (up if s > 0 else dn).append(sp)
    m = lambda x: round(sum(x) / len(x), 5) if x else None
    return {"up_months": len(up), "up_mean_dbc_minus_gld": m(up),
            "down_months": len(dn), "down_mean_dbc_minus_gld": m(dn)}


if __name__ == "__main__":
    variants = {"m1": make(1), "m2": make(2), "m4": make(4), "m6": make(6), "exgold": make(3, EXGOLD)}
    res = rb.evaluate("L-2026-11-28-CCYDEMAND", weights, SYMS, None, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=22,
                      family="ccy-predicts-cmd", variants=variants,
                      notes="month-end: if the mean 3-month log change vs USD of AUD/CAD/CLP/NZD/ZAR (Yahoo FX "
                            "bars strictly before the decision date, 5-bar median spike guard) > 0: DBC +1.0 / "
                            "GLD -1.0, else DBC -1.0 / GLD +1.0; net 0, T-bills on capital and short proceeds; "
                            "bench T-bills; 5bp; dollar-neutral test of R-2026-11-09-CCYCMD (lab)")
    print(json.dumps(res, indent=1))

    dates, px = rb.prices(SYMS, START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    rf1 = rf[1:]
    out = {}
    for name, fn in (("spread", make(audit=True)), ("longflat_guarded", make(mode="longflat")),
                     ("static_long_dbc_short_gld", make(mode="static"))):
        r, _ = rb.simulate(fn, dates, px, rf, 5.0)
        out[name] = {"sharpe": round(rb.sharpe(r, rf1), 3), "cagr": round(rb.cagr(r), 4),
                     "maxdd": round(rb.max_dd(r), 4)}
    dbc = rb.bench_returns("DBC", dates, px, rf)
    out["dbc_buy_hold"] = {"sharpe": round(rb.sharpe(dbc, rf1), 3), "cagr": round(rb.cagr(dbc), 4)}
    s_sp = out["spread"]["sharpe"]
    conf = res.get("confidence", 0)
    oos = res.get("oos_idea_sharpe", -9)
    if s_sp > 0 and conf >= 0.90 and oos > 0:
        read = "DEMAND SIGNAL"
    elif s_sp > 0:
        read = "PARTIAL"
    elif out["longflat_guarded"]["sharpe"] > out["dbc_buy_hold"]["sharpe"]:
        read = "DOLLAR/BETA ONLY"
    else:
        read = "NO SIGNAL"
    print(json.dumps({"demand_readout": read, "confidence": conf, "controls": out,
                      "split_diagnostic": split_diag(dates, px),
                      "sizing_audit (header: long 1.0, short 1.0, net 0 every live month)": AUDIT,
                      "ccycmd_reference": {"cagr": 0.0535, "sharpe": 0.372, "confidence": 0.9428}}, indent=1))
