"""
stocks_report.py — scorecard for the Stocks & ETF sandbox (journal only)
========================================================================
Runs on data/stocks/*.csv alone — no API — so analysis works anywhere the
journal snapshot is checked out. Per strategy: closed campaigns, win rate,
expectancy ± SE, t-stat, the playbook's "confidence the edge is real"
(Student-t CDF), profit factor, max drawdown, average hold, unrealized
P&L on open campaigns, the pre-registered gate progress, and P&L split by
every regime tag at entry (the §6a idea well).
"""

import math
from datetime import date

import stocks_engine as se
import stocks_store as st


# ── Student-t CDF (regularized incomplete beta, Numerical Recipes) ──────────

def _betacf(a, b, x):
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                   -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + aa / c
            c = c if abs(c) > tiny else tiny
            de = d * c
            h *= de
        if abs(de - 1) < 3e-12:
            break
    return h


def _betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_cdf(t: float, df: int) -> float:
    if df <= 0:
        return None
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2, 0.5, x)
    return 1 - tail if t > 0 else tail


def stats(pnls: list) -> dict:
    pnls = [p for p in pnls if p is not None]
    n = len(pnls)
    out = {"n": n, "total": round(sum(pnls), 2)}
    if not n:
        return out
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    mean = sum(pnls) / n
    out.update(win_rate=round(len(wins) / n, 3), expectancy=round(mean, 2),
               avg_win=round(sum(wins) / len(wins), 2) if wins else None,
               avg_loss=round(sum(losses) / len(losses), 2) if losses else None,
               pf=(round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0
                   else None))
    if n >= 2:
        sd = math.sqrt(sum((p - mean) ** 2 for p in pnls) / (n - 1))
        se_ = sd / math.sqrt(n)
        out["se"] = round(se_, 2)
        if se_ > 0:
            t = mean / se_
            out["t"] = round(t, 2)
            out["confidence"] = round(t_cdf(t, n - 1), 3)
    eq = peak = dd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    out["max_dd"] = round(dd, 2)
    return out


def _vix_bucket(v):
    v = se.fnum(v)
    if v is None:
        return "n/a"
    return "<15" if v < 15 else ("15-20" if v <= 20 else ">20")


def _breadth_bucket(v):
    v = se.fnum(v)
    if v is None:
        return "n/a"
    return "<40%" if v < 40 else ("40-60%" if v <= 60 else ">60%")


def summary(cfg=None) -> dict:
    """Everything the dashboard's scorecard needs, as JSON."""
    cfg = cfg or se.load_config()
    positions = st.read("positions")
    days = {r["date"]: r for r in st.read("day")}
    marks = se.last_marks()
    first_day = min((p.get("entry_ts") or "")[:10] for p in positions) if positions else None
    weeks = max(0.0, (date.today() - date.fromisoformat(first_day)).days / 7) if first_day else 0
    out = {"strategies": {}, "weeks_running": round(weeks, 1), "first_day": first_day}
    for strat in se.STRATEGIES:
        rows = [p for p in positions if p.get("strategy") == strat]
        closed = [p for p in rows if not st.is_open(p)]
        closed.sort(key=lambda p: p.get("exit_ts") or "")
        opens = [p for p in rows if st.is_open(p)]
        s = stats([se.realized(p) for p in closed])
        unreal = sum(se.fnum((marks.get(p["position_id"]) or {}).get("unrealized")) or 0
                     for p in opens)
        holds = [se.sessions_between((p.get("entry_ts") or "")[:10], (p.get("exit_ts") or "")[:10])
                 for p in closed if p.get("entry_ts") and p.get("exit_ts")]
        g = cfg["gates"].get(strat, {})
        s_first = min(((p.get("entry_ts") or "")[:10] for p in rows), default=None)
        s_weeks = max(0.0, (date.today() - date.fromisoformat(s_first)).days / 7) if s_first else 0
        splits = {}
        for tag, fn in (("spy_regime", lambda d: d.get("spy_regime") or "n/a"),
                        ("vix", lambda d: _vix_bucket(d.get("vix"))),
                        ("breadth50", lambda d: _breadth_bucket(d.get("breadth50")))):
            buckets = {}
            for p in closed:
                d = days.get((p.get("entry_ts") or "")[:10]) or {}
                buckets.setdefault(fn(d), []).append(se.realized(p))
            splits[tag] = {k: {"n": len(v), "total": round(sum(x or 0 for x in v), 2)}
                           for k, v in sorted(buckets.items())}
        reasons = {}
        for p in closed:
            reasons[p.get("exit_reason") or "?"] = reasons.get(p.get("exit_reason") or "?", 0) + 1
        tot = s.get("total", 0)
        out["strategies"][strat] = {
            **s, "open": len(opens), "unrealized": round(unreal, 2),
            "avg_hold_sessions": round(sum(holds) / len(holds), 1) if holds else None,
            "exit_reasons": reasons, "splits": splits,
            "gate": {"trades": g.get("trades"), "weeks": g.get("weeks"),
                     "tripwire": g.get("tripwire"), "weeks_running": round(s_weeks, 1),
                     "progress": round(max(len(closed) / g["trades"] if g.get("trades") else 0,
                                           s_weeks / g["weeks"] if g.get("weeks") else 0), 3),
                     "tripped": (tot + unreal) <= (g.get("tripwire") or -1e18),
                     "admissible": len(closed) >= 20},
        }
    eod = st.read("eod")
    out["equity_curve"] = [{"date": r["date"], "equity": se.fnum(r.get("equity_est")),
                            "realized_cum": se.fnum(r.get("realized_cum")),
                            "unrealized": se.fnum(r.get("unrealized"))} for r in eod]
    return out


def _m(x, nd=0):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def _usd(x):
    if x is None:
        return "n/a"
    return ("−" if round(x) < 0 else "") + f"${abs(x):,.0f}"


def text_report(cfg=None) -> str:
    s = summary(cfg)
    L = [f"── stocks sandbox report ({date.today().isoformat()}) — journal only ──"]
    for strat, r in s["strategies"].items():
        g = r["gate"]
        L.append(f"{strat:<5} closed {r['n']:>3} | open {r['open']:>2} | realized "
                 f"{_usd(r.get('total'))} | unrealized {_usd(r.get('unrealized'))}")
        if r["n"]:
            conf = r.get("confidence")
            L.append(f"      win {_m((r.get('win_rate') or 0) * 100)}% | expectancy "
                     f"{_usd(r.get('expectancy'))} ± {_m(r.get('se'))} | t {r.get('t', 'n/a')} | "
                     f"conf {'n/a' if conf is None else f'{conf * 100:.0f}%'} | PF "
                     f"{r.get('pf') or 'n/a'} | maxDD {_usd(r.get('max_dd'))} | hold "
                     f"{r.get('avg_hold_sessions') or 'n/a'} sessions")
            L.append(f"      exits {r['exit_reasons']}")
            for tag, b in r["splits"].items():
                L.append(f"      by {tag}: " + ", ".join(
                    f"{k} n={v['n']} {_usd(v['total'])}" for k, v in b.items()))
        adm = "" if g["admissible"] else "  [<20 closed: statistically inadmissible]"
        trip = "  ** TRIPWIRE HIT — review **" if g["tripped"] else ""
        L.append(f"      gate {g['trades']} trades or {g['weeks']}w "
                 f"(tripwire {_usd(g['tripwire'])}): {g['progress'] * 100:.0f}%{adm}{trip}")
    return "\n".join(L)
