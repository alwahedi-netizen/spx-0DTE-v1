"""
perf_report.py — weekly performance report for the Paper Lab's systems
======================================================================
Owner request 2026-10-31: "scan my systems for performance, weekly update".
Reads only the journals the hub snapshots into git (data/stocks/*.csv,
data/labs/*.csv) plus SPY from Yahoo as the yardstick, and prints a report:

    python3 perf_report.py            # plain-text summary
    python3 perf_report.py --html F   # also write the email body to F
    python3 perf_report.py --json F   # machine-readable numbers

Covered: Stocks & ETFs, Crypto, Commodities, FX, Allocations. NOT options
(another instance owns them) and not Project Shine (its journal is not in git).
Read-only: it never writes a journal, never trades.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LABS = BASE / "data" / "labs"
STOCKS = BASE / "data" / "stocks"

LAB_META = {   # prefix -> (title, start $ per lane, lane labels)
    "alloclab": ("Allocations", 10_000.0, {
        "HFEA": "Hedgefundie 55/45", "VMSPX15": "Vol-managed S&P 1.5×",
        "RP2X": "Risk parity 2×", "SPY": "SPY (yardstick)"}),
    "cryptolab": ("Crypto", 10_000.0, {
        "H5": "5★ sell after 5 days", "H10": "5★ sell after 10 days", "TR30": "TR30 breakout"}),
    "cmdlab": ("Commodities", 10_000.0, {
        "H21": "5★ sell after 21 days", "H63": "5★ sell after 63 days", "TR30": "TR30 breakout"}),
    "fxlab": ("FX", 10_000.0, {
        "CARRY": "Carry", "CARRY-V": "Carry + trend veto", "TSMOM": "Trend (12-1)", "TR30": "TR30 breakout"}),
}
FLAG_WEEK_LOSS = -0.05       # a lane down more than 5% on the week
FLAG_DRAWDOWN = -0.15        # a lane more than 15% below its peak
STALE_DAYS = 4               # last mark older than this (calendar days) -> stale
STOCK_PAPER_LANES = ("ICHI", "ST", "KDJA")   # stocks_config.yaml stage: paper (observation)


def _rows(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _d(s):
    return date.fromisoformat(s[:10])


def lane_series(prefix):
    """{lane: [(date, nav), ...]} from <prefix>_nav.csv."""
    out = defaultdict(list)
    for r in _rows(LABS / f"{prefix}_nav.csv"):
        try:
            out[r["lane"]].append((_d(r["day"]), float(r["nav"])))
        except (KeyError, ValueError):
            continue
    for k in out:
        out[k].sort()
    return dict(out)


def stats(series, start_nav, asof, week_start):
    """Now, week change, since start, max drawdown for one NAV series."""
    if not series:
        return None
    now_d, now = series[-1]
    before = [v for d, v in series if d <= week_start]
    wk_base = before[-1] if before else start_nav
    peak, dd = start_nav, 0.0
    for _, v in series:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    return {"now": round(now, 2), "asof": now_d.isoformat(),
            "week": round(now - wk_base, 2), "week_pct": round(now / wk_base - 1, 4) if wk_base else 0,
            "total": round(now - start_nav, 2), "total_pct": round(now / start_nav - 1, 4),
            "max_dd": round(dd, 4), "from_peak": round(now / peak - 1, 4),
            "first": series[0][0].isoformat(), "stale": (asof - now_d).days > STALE_DAYS}


def lab_trades(prefix, week_start):
    """Closed trades (all time / this week) from <prefix>_trades.csv."""
    closed, week = [], []
    for r in _rows(LABS / f"{prefix}_trades.csv"):
        if not r.get("exit_day") or r.get("pnl") in (None, ""):
            continue
        t = {"lane": r["lane"], "sym": r["sym"], "pnl": float(r["pnl"]),
             "pct": float(r["pnl_pct"] or 0), "exit": r["exit_day"][:10]}
        closed.append(t)
        if _d(t["exit"]) > week_start:
            week.append(t)
    return closed, week


def open_positions(prefix):
    rows = _rows(LABS / f"{prefix}_pos.csv")
    if prefix == "fxlab":
        rows += [dict(r, lane="TR30", sym=r.get("ccy")) for r in _rows(LABS / "fxlab_trpos.csv")]
    out = defaultdict(list)
    for r in rows:
        try:
            if float(r.get("qty") or r.get("notional") or 0) == 0:
                continue
        except ValueError:
            continue
        out[r["lane"]].append(r.get("sym") or r.get("ccy"))
    return dict(out)


def stocks_section(asof, week_start):
    eod = [r for r in _rows(STOCKS / "eod.csv") if r.get("equity_est")]
    if not eod:
        return None
    ser = [(_d(r["date"]), float(r["equity_est"])) for r in eod]
    book = stats(ser, 100_000.0, asof, week_start)
    by = defaultdict(lambda: {"realized": 0.0, "week_realized": 0.0, "closed": 0, "wins": 0,
                              "week_closed": 0, "open": [], "unrealized": 0.0})
    for lane in STOCK_PAPER_LANES:      # list every paper lane, traded or not
        by[lane]
    for p in _rows(STOCKS / "positions.csv"):
        s = by[p["strategy"]]
        pnl = p.get("pnl_actual") or p.get("pnl_theo")
        if p.get("exit_ts") and pnl:
            v = float(pnl)
            s["realized"] += v
            s["closed"] += 1
            s["wins"] += v > 0
            if _d(p["exit_ts"]) > week_start:
                s["week_realized"] += v
                s["week_closed"] += 1
        elif not p.get("exit_ts"):
            s["open"].append(p["symbol"])
    marks = _rows(STOCKS / "marks.csv")
    last = max((m["date"] for m in marks), default=None)
    for m in marks:
        if m["date"] == last and m["strategy"] in by:
            try:
                by[m["strategy"]]["unrealized"] += float(m["unrealized"])
            except ValueError:
                pass
    lanes = {k: {**v, "realized": round(v["realized"], 2), "week_realized": round(v["week_realized"], 2),
                 "unrealized": round(v["unrealized"], 2),
                 "total": round(v["realized"] + v["unrealized"], 2)} for k, v in sorted(by.items())}
    return {"book": book, "lanes": lanes, "start": 100_000.0}


def spy_returns(first_day, week_start, asof, fetch=None):
    """SPY total return over the week and since `first_day` (Yahoo adjusted)."""
    try:
        if fetch is None:
            sys.path.insert(0, str(BASE))
            import research_bt
            fetch = research_bt._fetch
        px = fetch("SPY")
        days = sorted(d for d in px if d <= asof.isoformat())
        at = lambda d0: px[max([d for d in days if d <= d0] or [days[0]])]
        end = px[days[-1]]
        return {"week": round(end / at(week_start.isoformat()) - 1, 4),
                "since": {d: round(end / at(d) - 1, 4) for d in first_day}}
    except Exception as e:
        return {"error": str(e)[:120]}


def build(asof=None, fetch=None):
    days = []
    for p in LAB_META:
        for s in lane_series(p).values():
            days += [d for d, _ in s]
    for r in _rows(STOCKS / "eod.csv"):
        days.append(_d(r["date"]))
    asof = asof or (max(days) if days else date.today())
    week_start = asof - timedelta(days=7)
    rep = {"asof": asof.isoformat(), "week_start": week_start.isoformat(), "labs": {}, "flags": []}
    firsts = set()
    st = stocks_section(asof, week_start)
    if st:
        rep["stocks"] = st
        firsts.add(st["book"]["first"])
    for prefix, (title, start, labels) in LAB_META.items():
        ser = lane_series(prefix)
        if not ser:
            continue
        closed, week = lab_trades(prefix, week_start) if prefix in ("cryptolab", "cmdlab") else ([], [])
        pos = open_positions(prefix)
        lanes = {}
        for lane in list(labels) + [l for l in ser if l not in labels]:
            if lane not in ser:
                continue
            s = stats(ser[lane], start, asof, week_start)
            s["label"] = labels.get(lane, lane)
            s["open"] = pos.get(lane, [])
            s["closed_all"] = sum(1 for t in closed if t["lane"] == lane)
            s["closed_week"] = [t for t in week if t["lane"] == lane]
            lanes[lane] = s
            firsts.add(s["first"])
            name = f"{title} · {s['label']}"
            if s["week_pct"] <= FLAG_WEEK_LOSS:
                rep["flags"].append(f"{name}: down {s['week_pct']:.1%} this week")
            if s["from_peak"] <= FLAG_DRAWDOWN:
                rep["flags"].append(f"{name}: {s['from_peak']:.1%} below its peak")
            if s["stale"]:
                rep["flags"].append(f"{name}: no mark since {s['asof']} — is the lab running?")
        rep["labs"][prefix] = {"title": title, "lanes": lanes}
    rates = _rows(LABS / "fxlab_rates.csv")
    if rates and "fxlab" in rep["labs"]:
        seed = {"USD": 4.0, "EUR": 2.15, "JPY": 1.0, "GBP": 3.75, "CHF": 0.25,
                "CAD": 2.5, "AUD": 3.6, "NZD": 3.0, "SEK": 2.0, "NOK": 4.0}
        if all(abs(float(r["rate"]) - seed.get(r["ccy"], -1)) < 1e-9 for r in rates):
            rep["flags"].append("FX: policy rates are still the unverified seed values — the carry lanes rank currencies by them")
    if st and st["book"]["from_peak"] <= FLAG_DRAWDOWN / 3:
        rep["flags"].append(f"Stocks book: {st['book']['from_peak']:.1%} below its peak")
    rep["spy"] = spy_returns(sorted(firsts), week_start, asof, fetch)
    return rep


# ── rendering ────────────────────────────────────────────────────────────────

def _money(v):
    return f"{'+' if v >= 0 else '−'}${abs(v):,.0f}"


def _pct(v):
    return f"{'+' if v >= 0 else '−'}{abs(v) * 100:.1f}%"


def _col(v):
    return "#1a7f4b" if v > 0 else "#b3372f" if v < 0 else "#6b7280"


def text(rep):
    out = [f"Paper Lab performance — week to {rep['asof']}"]
    spy = rep.get("spy", {})
    if "week" in spy:
        out.append(f"SPY this week {_pct(spy['week'])}")
    if rep.get("stocks"):
        b = rep["stocks"]["book"]
        out.append(f"\nStocks & ETFs book ${b['now']:,.0f}: week {_money(b['week'])}, since start {_money(b['total'])}")
        for k, v in rep["stocks"]["lanes"].items():
            out.append(f"  {k:6s} total {_money(v['total'])} (realized {_money(v['realized'])}, open {_money(v['unrealized'])}) "
                       f"· {v['closed']} closed, {v['week_closed']} this week · open: {', '.join(v['open']) or '—'}")
    for lab in rep["labs"].values():
        out.append(f"\n{lab['title']}")
        for k, s in lab["lanes"].items():
            out.append(f"  {s['label']:24s} ${s['now']:>9,.0f}  week {_pct(s['week_pct']):>7s}  since {s['first']} {_pct(s['total_pct']):>7s}"
                       f"  max DD {_pct(s['max_dd'])}  open: {', '.join(s['open']) or '—'}")
    out.append("\nFlags: " + ("; ".join(rep["flags"]) if rep["flags"] else "none"))
    return "\n".join(out)


def html(rep, intro=""):
    spy = rep.get("spy", {})
    th = 'style="text-align:left;padding:5px 8px;background:#f6f4ef;font-size:12px"'
    td = 'style="padding:5px 8px;border-bottom:1px solid #eee;font-size:13px"'
    tdr = 'style="padding:5px 8px;border-bottom:1px solid #eee;font-size:13px;text-align:right;white-space:nowrap"'
    h = ['<div style="font-family:Segoe UI,Arial,sans-serif;color:#1e232b;max-width:780px">',
         "<p>Tariq,</p>", intro and f"<p>{intro}</p>",
         f"<p>Week to <b>{rep['asof']}</b> (since {rep['week_start']}). "
         + (f"SPY this week: <b style='color:{_col(spy['week'])}'>{_pct(spy['week'])}</b>." if "week" in spy else "")
         + "</p>"]
    h.append("<h3 style='margin:16px 0 6px'>Needs attention</h3>")
    h.append("<ul>" + "".join(f"<li>{f}</li>" for f in rep["flags"]) + "</ul>" if rep["flags"]
             else "<p>Nothing — no lane is down more than 5% on the week or 15% from its peak, and every lab marked on schedule.</p>")
    if rep.get("stocks"):
        st = rep["stocks"]
        b = st["book"]
        h.append(f"<h3 style='margin:16px 0 6px'>Stocks &amp; ETFs — ${b['now']:,.0f} "
                 f"(<span style='color:{_col(b['week'])}'>{_money(b['week'])}</span> this week, "
                 f"<span style='color:{_col(b['total'])}'>{_money(b['total'])}</span> since {b['first']})</h3>")
        h.append(f"<table style='border-collapse:collapse'><tr><th {th}>Lane</th><th {th}>Total P&amp;L</th>"
                 f"<th {th}>Closed trades</th><th {th}>This week</th><th {th}>Open now</th></tr>")
        for k, v in st["lanes"].items():
            h.append(f"<tr><td {td}><b>{k}</b></td><td {tdr} style='color:{_col(v['total'])}'>{_money(v['total'])}</td>"
                     f"<td {tdr}>{v['closed']} ({v['wins']} won)</td>"
                     f"<td {tdr}>{v['week_closed']} closed, {_money(v['week_realized'])}</td>"
                     f"<td {td}>{', '.join(v['open']) or '—'}</td></tr>")
        h.append("</table><p style='font-size:12px;color:#6b7280'>ICHI, ST and KDJA run as observation lanes; "
                 "their gate needs 50+ trades before a verdict.</p>")
    for prefix, lab in rep["labs"].items():
        h.append(f"<h3 style='margin:16px 0 6px'>{lab['title']}</h3>")
        h.append(f"<table style='border-collapse:collapse'><tr><th {th}>Lane</th><th {th}>Value</th><th {th}>This week</th>"
                 f"<th {th}>Since start</th><th {th}>Worst drop</th><th {th}>Holding</th></tr>")
        for k, s in lab["lanes"].items():
            since = spy.get("since", {}).get(s["first"])
            spy_note = f"<br><span style='font-size:11px;color:#6b7280'>SPY {_pct(since)}</span>" if since is not None else ""
            wk = "; ".join(f"{t['sym']} {_money(t['pnl'])}" for t in s["closed_week"])
            h.append(f"<tr><td {td}><b>{s['label']}</b><br><span style='font-size:11px;color:#6b7280'>since {s['first']}</span></td>"
                     f"<td {tdr}>${s['now']:,.0f}</td>"
                     f"<td {tdr} style='color:{_col(s['week_pct'])}'>{_pct(s['week_pct'])}</td>"
                     f"<td {tdr}><span style='color:{_col(s['total_pct'])}'>{_pct(s['total_pct'])}</span>{spy_note}</td>"
                     f"<td {tdr}>{_pct(s['max_dd'])}</td>"
                     f"<td {td}>{', '.join(s['open']) or 'cash'}{('<br><span style=font-size:11px>closed: ' + wk + '</span>') if wk else ''}</td></tr>")
        h.append("</table>")
    h.append("<p style='font-size:12px;color:#6b7280'>Each lane started with $10,000 (Stocks book: $100,000). Options and Project Shine "
             "are not in this report. Live pages: <a href='https://paper.sahmi.ae/'>paper.sahmi.ae</a>.</p></div>")
    return "\n".join(x for x in h if x)


if __name__ == "__main__":
    rep = build()
    print(text(rep))
    args = sys.argv[1:]
    if "--html" in args:
        Path(args[args.index("--html") + 1]).write_text(html(rep), encoding="utf-8")
    if "--json" in args:
        Path(args[args.index("--json") + 1]).write_text(json.dumps(rep, indent=1), encoding="utf-8")
