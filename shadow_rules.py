"""
shadow_rules.py — "what if we had applied them?" for three candidate rules.

Owner 2026-11-08: "I don't approve, however, you can run in parallel to see
if we applied them vs if we didn't." So NOTHING here changes how any
strategy trades. This is a read-only replay of the lab's own journals: for
each strategy it shows the P&L as actually traded next to the P&L had each
rule been in force. It is reported in the nightly digest.

PRE-REGISTERED 2026-11-08, before any result was computed (do not tune):

  Strategies: the lanes running today — MEIC, MNG, FLY, FLYR, MPM (premium
  sellers), ORB, OCB (breakout buyers) — from data/paper/positions.csv
  (pnl_actual = after simulated fills), plus MEIC's REAL-money trades from
  data/paper/live/live_trades.csv (pnl_live, already net of fees).
  A "session" is one trading date; rules act on whole sessions.

  1. FUSE (loss circuit breaker), every strategy.
     Halt a strategy's trading once its equity is $2,000 or more below its
     peak (checked at each session's close). While halted its trades still
     happen on paper (shadow). Re-arm for the next session once a session
     closes with shadow equity above the average of its last 10 session
     closes; the peak then resets to that equity.
     Sensitivity only (not the verdict): $1,500 and $3,000.

  2. GAP / RANGE gate, premium sellers only (MEIC, MNG, FLY, FLYR, MPM,
     MEIC real). ATR20 and prior_close come from day.csv (the lab's own
     morning values); SPX open/high/low from Yahoo ^GSPC daily bars.
     2a. skip the day if |open - prior_close| > 0.5 x ATR20   (big gap)
     2b. skip the day if prior day's (high - low) > 1.25 x ATR20 (wild day)
     Reported separately; never combined.

  3. VOLATILITY CHECK (VRP gate), premium sellers only.
     RV5 = annualised standard deviation of the last 5 daily SPX log returns
     up to the prior close, in VIX points (x100). Trade only when the
     morning VIX (day.csv) > RV5 — options priced richer than the realised
     moves (the published direction). Skip otherwise.
     Caveat recorded in advance: our own first 45 days pointed the other
     way, so the history below is partly in-sample; the FORWARD column
     (sessions from 2026-11-09) is the honest test.

    python3 shadow_rules.py              # text table
    python3 shadow_rules.py --json F     # numbers for the digest
"""

import csv
import json
import math
import sys
import urllib.request
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PAPER = BASE / "data" / "paper"
FORWARD_FROM = "2026-11-09"          # first session after pre-registration
FUSE_LIMIT = 2000.0
FUSE_SENS = (1500.0, 3000.0)
GAP_ATR, RANGE_ATR = 0.5, 1.25
SELLERS = ("MEIC", "MNG", "FLY", "FLYR", "MPM", "MEIC real")
BUYERS = ("ORB", "OCB")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def sessions():
    """{strategy: OrderedDict(date -> session P&L)} for paper lanes + live MEIC."""
    out = defaultdict(lambda: defaultdict(float))
    for r in csv.DictReader(open(PAPER / "positions.csv")):
        s, p = r["strategy"], _num(r["pnl_actual"])
        if s in SELLERS + BUYERS and p is not None:
            out[s][r["position_id"][:10]] += p
    live = PAPER / "live" / "live_trades.csv"
    if live.exists():
        for r in csv.DictReader(open(live)):
            p = _num(r.get("pnl_live"))
            if p is not None and "-MEIC-" in r["position_id"]:
                out["MEIC real"][r["position_id"][:10]] += p
    return {s: OrderedDict(sorted(d.items())) for s, d in out.items()}


def day_rows():
    return {r["date"]: r for r in csv.DictReader(open(PAPER / "day.csv"))}


def spx_bars(fetch=None):
    """{date: (open, high, low, close)} from Yahoo ^GSPC daily bars."""
    if fetch:
        return fetch()
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC"
           "?range=2y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = {}
    for i, t in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None not in (o, h, l, c):
            out[datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")] = (o, h, l, c)
    return out


def gates(days, bars):
    """{date: {"gap": skip?, "range": skip?, "vrp": skip?, ...diagnostics}}."""
    dates = sorted(bars)
    out = {}
    for d, row in days.items():
        atr, pc, vix = _num(row.get("atr20")), _num(row.get("prior_close")), _num(row.get("vix"))
        if d not in bars or d not in dates:
            continue
        i = dates.index(d)
        g = {}
        if atr and pc:
            g["gap_atr"] = (bars[d][0] - pc) / atr
            g["gap"] = abs(g["gap_atr"]) > GAP_ATR
            if i >= 1:
                ph, pl = bars[dates[i - 1]][1], bars[dates[i - 1]][2]
                g["range_atr"] = (ph - pl) / atr
                g["range"] = g["range_atr"] > RANGE_ATR
        if vix and i >= 6:
            cl = [bars[x][3] for x in dates[i - 6:i]]          # 6 closes -> 5 returns, to prior close
            rets = [math.log(cl[k + 1] / cl[k]) for k in range(5)]
            m = sum(rets) / 5
            rv5 = math.sqrt(sum((x - m) ** 2 for x in rets) / 4) * math.sqrt(252) * 100
            g["rv5"], g["vix"] = rv5, vix
            g["vrp"] = not (vix > rv5)                          # True = skip
        out[d] = g
    return out


def max_dd(pnls):
    eq = pk = dd = 0.0
    for p in pnls:
        eq += p
        pk = max(pk, eq)
        dd = min(dd, eq - pk)
    return dd


def fuse(sess, limit):
    """(kept dict date->pnl, halted dates) under the pre-registered fuse."""
    armed, eq, peak, closes, kept, halted = True, 0.0, 0.0, [], OrderedDict(), []
    for d, p in sess.items():
        if armed:
            kept[d] = p
        else:
            halted.append(d)
        eq += p
        closes.append(eq)
        if armed:
            peak = max(peak, eq)
            if peak - eq >= limit:
                armed = False
        else:
            avg10 = sum(closes[-10:]) / len(closes[-10:])
            if eq > avg10:
                armed, peak = True, eq
    return kept, halted


def compare(sess, kept_dates):
    """Stats for as-traded vs with-rule, history and forward."""
    def block(ds):
        allp = [sess[d] for d in ds]
        keep = [sess[d] for d in ds if d in kept_dates]
        skipped = [sess[d] for d in ds if d not in kept_dates]
        return {"sessions": len(allp), "skipped": len(skipped),
                "pnl_without": round(sum(allp), 2), "pnl_with": round(sum(keep), 2),
                "diff": round(sum(keep) - sum(allp), 2),
                "pnl_on_skipped": round(sum(skipped), 2),
                "dd_without": round(max_dd(allp), 2), "dd_with": round(max_dd(keep), 2)}
    ds = list(sess)
    return {"history": block([d for d in ds if d < FORWARD_FROM]),
            "forward": block([d for d in ds if d >= FORWARD_FROM])}


def run(bars_fetch=None):
    S = sessions()
    G = gates(day_rows(), spx_bars(bars_fetch))
    res = {"asof": max(d for s in S.values() for d in s) if S else None,
           "forward_from": FORWARD_FROM, "rules": {}}
    r1 = {}
    for s, sess in S.items():
        kept, halted = fuse(sess, FUSE_LIMIT)
        r1[s] = compare(sess, set(kept)) | {"halted_dates": halted,
            "sens": {str(int(L)): compare(sess, set(fuse(sess, L)[0]))["history"]["diff"] for L in FUSE_SENS}}
    res["rules"]["fuse"] = r1
    for rule in ("gap", "range", "vrp"):
        rr = {}
        for s in SELLERS:
            if s not in S:
                continue
            sess = S[s]
            # a day with no gate value (data gap) is traded, i.e. not skipped
            kept = {d for d in sess if not G.get(d, {}).get(rule, False)}
            rr[s] = compare(sess, kept) | {"no_data": [d for d in sess if rule not in G.get(d, {})]}
        res["rules"][rule] = rr
    res["gates"] = {d: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in g.items()}
                    for d, g in sorted(G.items())}
    return res


def _total(rule):
    t = defaultdict(float)
    for s, v in rule.items():
        if s == "MEIC real":
            continue
        for k in ("pnl_without", "pnl_with", "diff"):
            t[k] += v["history"][k]
    return t


def text(res):
    names = {"fuse": f"1 · Fuse (halt at -${FUSE_LIMIT:,.0f} from peak)",
             "gap": f"2a · Skip big-gap days (|gap| > {GAP_ATR} ATR)",
             "range": f"2b · Skip after wild days (range > {RANGE_ATR} ATR)",
             "vrp": "3 · Volatility check (trade only when VIX > 5-day realised)"}
    out = [f"Shadow rules — journal to {res['asof']}; forward test from {res['forward_from']}"]
    for k, rule in res["rules"].items():
        out.append("\n" + names[k])
        out.append(f"  {'strategy':<10}{'sessions':>9}{'skipped':>8}{'without':>11}{'with':>11}{'diff':>10}"
                   f"{'DD w/o':>10}{'DD with':>10}")
        for s, v in rule.items():
            h = v["history"]
            out.append(f"  {s:<10}{h['sessions']:>9}{h['skipped']:>8}{h['pnl_without']:>11,.0f}"
                       f"{h['pnl_with']:>11,.0f}{h['diff']:>+10,.0f}{h['dd_without']:>10,.0f}{h['dd_with']:>10,.0f}")
        t = _total(rule)
        out.append(f"  {'paper all':<10}{'':>17}{t['pnl_without']:>11,.0f}{t['pnl_with']:>11,.0f}{t['diff']:>+10,.0f}")
    return "\n".join(out)


def _selftest():
    # fuse: -2,100 trips it; halted sessions are shadow; re-arms above the 10-close average
    seq = OrderedDict((f"2026-01-{i:02d}", p) for i, p in enumerate([500, -1300, -1300, 100, 100, 900, 50]))
    kept, halted = fuse(seq, 2000)
    # closes 500, -800, -2100 (trip: 2,600 below peak), -2000, -1900, -1000 (> its
    # 6-close average -1,217 -> re-arm), so d03-d05 are shadow-only
    assert halted == ["2026-01-03", "2026-01-04", "2026-01-05"], halted
    assert list(kept) == ["2026-01-00", "2026-01-01", "2026-01-02", "2026-01-06"]
    c = compare(seq, set(kept))["history"]
    assert c["skipped"] == 3 and c["diff"] == -1100
    # gates on synthetic bars: day 7 gaps 40 pts on ATR 50 (> 0.5), day 6 range 70 (> 1.25 x 50)
    bars = {f"2026-01-{d:02d}": (100.0 * d, 100.0 * d + 10, 100.0 * d - 10, 100.0 * d) for d in range(1, 8)}
    bars["2026-01-06"] = (600.0, 650.0, 580.0, 600.0)
    bars["2026-01-07"] = (640.0, 650.0, 630.0, 645.0)
    days = {"2026-01-07": {"atr20": "50", "prior_close": "600", "vix": "1"}}
    g = gates(days, bars)["2026-01-07"]
    assert g["gap"] and g["range"] and g["vrp"]     # VIX 1 < realised vol -> skip
    print("shadow_rules selftest: ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit()
    res = run()
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(res, indent=1))
    print(text(res))
