"""
paper_report.py — stats for the paper-mode signal logger
========================================================
`python3 paper_engine.py report --weeks N` lands here. Runs on the CSVs in
data/paper/ alone — no API calls — so it works anywhere the journal is
checked out. Theo metrics judge the rules; actual metrics (human-filled
paperMoney columns) judge execution; slippage is the gap between them.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta

import paper_store as st


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _pnl_stats(pnls):
    """(n, win_rate, avg_win, avg_loss, expectancy) over closed P/Ls."""
    pnls = [p for p in pnls if p is not None]
    if not pnls:
        return 0, None, None, None, None
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return (len(pnls), len(wins) / len(pnls), _mean(wins), _mean(losses),
            _mean(pnls))


def _vix_bucket(v):
    if v is None:
        return "n/a"
    if v < 15:
        return "<15"
    if v <= 20:
        return "15-20"
    return ">20"


def pnl_summary(today: str = None, week_start: str = None) -> dict:
    """Daily/weekly P&L per strategy from positions.csv (closed rows only,
    pnl_actual when present, else pnl_theo). Pure CSV, no API. Used by the
    dashboard's P&L card and the CLI report."""
    closed = [p for p in st.read("positions") if (p.get("exit_ts") or "").strip()]
    by_day = {}
    for p in closed:
        d = (p.get("signal_ts") or "")[:10]
        v = _f(p.get("pnl_actual"))
        if v is None:
            v = _f(p.get("pnl_theo"))
        if not d or v is None:
            continue
        strat = p.get("strategy") or "?"
        rec = by_day.setdefault(d, {})
        rec[strat] = rec.get(strat, 0.0) + v

    def bucket(pred):
        out = {}
        for d, rec in by_day.items():
            if pred(d):
                for k, v in rec.items():
                    out[k] = round(out.get(k, 0.0) + v, 2)
        out["TOTAL"] = round(sum(v for k, v in out.items() if k != "TOTAL"), 2)
        return out

    days = [dict(date=d, TOTAL=round(sum(rec.values()), 2),
                 **{k: round(v, 2) for k, v in rec.items()})
            for d, rec in sorted(by_day.items(), reverse=True)]
    res = {"days": days[:10], "all": bucket(lambda d: True)}
    if today:
        res["today"] = bucket(lambda d: d == today)
    if week_start:
        res["week"] = bucket(lambda d: d >= week_start)
    return res


def run_report(weeks: int = 1):
    since = (date.today() - timedelta(weeks=weeks)).isoformat()
    signals = [r for r in st.read("signals") if r.get("date", "") >= since]
    sig_by_ts = {r["ts"]: r for r in st.read("signals") if r.get("ts")}
    positions = [p for p in st.read("positions")
                 if (p.get("signal_ts") or "")[:10] >= since]
    closed = [p for p in positions if (p.get("exit_ts") or "").strip()]
    band_rows = st.read("band")

    print(f"── paper report: since {since} ({weeks}w) "
          f"────────────────────────────────")

    # ── trades / skips per strategy ──
    strategies = ("METF", "BAND", "MEIC", "ORB")
    for strat in strategies:
        srows = [r for r in signals if r.get("strategy") == strat]
        trades = [r for r in srows if r.get("action") != "SKIP"]
        skips = Counter(r.get("skip_reason") or "?" for r in srows
                        if r.get("action") == "SKIP")
        skip_s = ", ".join(f"{k}:{n}" for k, n in sorted(skips.items())) or "none"
        print(f"{strat:<5} signals: {len(trades)} trades, "
              f"{sum(skips.values())} skips ({skip_s})")

    # ── win rate / expectancy / premium capture, theo and actual ──
    for strat in strategies:
        rows = [p for p in closed if p.get("strategy") == strat]
        for label, pnl_col, credit_col in (("theo", "pnl_theo", "credit_theo"),
                                           ("actual", "pnl_actual", "credit_actual")):
            sub = [p for p in rows if _f(p.get(pnl_col)) is not None]
            n, wr, aw, al, exp = _pnl_stats([_f(p[pnl_col]) for p in sub])
            tot_pnl = sum(_f(p[pnl_col]) for p in sub) if sub else 0.0
            tot_credit = sum((_f(p.get(credit_col)) or 0) * 100 *
                             (_f(p.get("contracts")) or 1) for p in sub)
            cap = (tot_pnl / tot_credit) if tot_credit > 0 else None  # n/a for debit strategies
            if n == 0:
                what = "closed" if label == "theo" else "filled"
                hint = "" if label == "theo" else \
                    " (use `paper fill` to record paperMoney fills)"
                print(f"  {strat} {label}: no {what} rows yet{hint}")
                continue
            cap_s = "n/a" if cap is None else f"{cap * 100:.1f}%"
            print(f"  {strat} {label}: n={n} win {wr * 100:.0f}% | "
                  f"avg win {_fmt(aw, 0)} avg loss {_fmt(al, 0)} | "
                  f"expectancy {_fmt(exp, 0)} | premium capture {cap_s}")

    # ── double-stop rate (band: both sides stopped same day) ──
    band_by_day = defaultdict(list)
    for p in closed:
        if p.get("strategy") in ("BAND", "MEIC"):
            band_by_day[((p.get("signal_ts") or "")[:16])].append(p)
    condor_days = [d for d, ps in band_by_day.items() if len(ps) >= 2]
    dbl = [d for d in condor_days
           if sum(1 for p in band_by_day[d] if p.get("exit_reason") == "STOPPED") >= 2]
    if condor_days:
        print(f"  condor double-stop rate (BAND+MEIC): {len(dbl)}/{len(condor_days)} "
              f"condors ({100 * len(dbl) / len(condor_days):.0f}%)")
    else:
        print("  condor double-stop rate: no condors yet")

    # ── P/L breakdowns (theo, joined position -> signal) ──
    def breakdown(title, key_fn):
        agg = defaultdict(lambda: [0.0, 0])
        for p in closed:
            pnl = _f(p.get("pnl_theo"))
            if pnl is None:
                continue
            sig = sig_by_ts.get(p.get("signal_ts")) or {}
            k = key_fn(p, sig)
            agg[k][0] += pnl
            agg[k][1] += 1
        if not agg:
            return
        parts = ", ".join(f"{k}: {v[0]:+.0f} (n={v[1]})"
                          for k, v in sorted(agg.items(), key=lambda kv: str(kv[0])))
        print(f"  P/L by {title}: {parts}")

    breakdown("slot", lambda p, s: s.get("slot") or "?")
    breakdown("EMA state", lambda p, s: s.get("state") or "-")
    breakdown("GEX sign", lambda p, s: s.get("gex_sign") or "unknown")
    breakdown("VIX bucket", lambda p, s: _vix_bucket(_f(s.get("vix"))))

    # ── slippage (actual vs theo, filled rows only) ──
    slip_c = _mean([(_f(p.get("credit_actual")) or 0) - (_f(p.get("credit_theo")) or 0)
                    for p in closed if _f(p.get("credit_actual")) is not None])
    slip_e = _mean([(_f(p.get("exit_value_actual")) or 0) - (_f(p.get("exit_value_theo")) or 0)
                    for p in closed if _f(p.get("exit_value_actual")) is not None])
    print(f"  slippage: entry {_fmt(slip_c)} / exit {_fmt(slip_e)} "
          f"(mean actual - theo, per spread)")

    # ── daily P&L (closed trades; actual, theo fallback) ──
    ps = pnl_summary()
    if ps["days"]:
        rows = " | ".join(
            f"{d['date'][5:]}: M {d.get('METF', 0):+.0f} B {d.get('BAND', 0):+.0f} Σ {d['TOTAL']:+.0f}"
            for d in ps["days"][::-1])
        print(f"  P/L by day: {rows}")

    # ── band containment, rolling 20d ──
    contained = [int(r["contained"]) for r in band_rows
                 if (r.get("contained") or "").strip() in ("0", "1")]
    if contained:
        last20 = contained[-20:]
        print(f"  band containment: {sum(last20)}/{len(last20)} "
              f"({100 * sum(last20) / len(last20):.0f}%) rolling {len(last20)}d")
    else:
        print("  band containment: no settled band days yet")
