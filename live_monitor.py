"""
live_monitor.py — trading-cost analysis + live-vs-paper drift (owner 2026-11-07:
"cover all 6 shortfalls": #4 transaction-cost analysis from real fills,
#5 live-versus-backtest monitoring).

Every live MEIC/ORB/FLY position mirrors a paper position with the SAME
position_id, so each live trade has an exact theoretical twin:

  entry slippage  = (paper credit - live fill)            per contract, $
  exit slippage   = (live close fill - paper exit value)  per contract, $ (closed by order)
  fees            = $1.18 per leg (4 legs when closed by order, 2 when expired)
  shortfall       = paper P&L - live net P&L   (= entry + exit slippage + fees + mismatches)
  capture         = live net / paper P&L       (share of the paper edge that reached the account)
Sign convention everywhere: POSITIVE = cost to us, NEGATIVE = price improvement
(holds for debit trades too: they are stored with negative credits).

Drift flags (per strategy, last N live trades): capture < 50% while paper is
positive, or live win rate more than 15 points below paper on the same trades.
Read-only: reads the journal CSVs, never trades. Stdlib only.

    python3 live_monitor.py            text report
    python3 live_monitor.py --json f   also write JSON
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
LIVE = BASE / "data" / "paper" / "live" / "live_trades.csv"
PAPER = BASE / "data" / "paper" / "positions.csv"
FEE_PER_LEG = 1.18
RECENT = 20


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def strat_of(pid):
    parts = (pid or "").split("-")
    s = parts[3] if len(parts) > 3 else "?"
    return s.rstrip("0123456789") or s


def pairs(live_rows, paper_rows):
    """Closed real live trades joined to their paper twin."""
    pp = {r["position_id"]: r for r in paper_rows}
    out = []
    for r in live_rows:
        if (r.get("order_id") or "").startswith("dry-") or r.get("status") not in ("CLOSED", "EXPIRED"):
            continue
        p = pp.get(r["position_id"])
        if not p:
            continue
        qty = int(_f(r.get("qty")) or 1)
        pc = int(_f(p.get("contracts")) or 1)
        by_order = bool((r.get("close_order_id") or "").strip())
        fees = FEE_PER_LEG * (4 if by_order else 2) * qty
        live_net = (_f(r.get("pnl_live")) or 0.0) - fees
        paper = (_f(p.get("pnl_theo")) or 0.0) * qty / pc
        ct, cf = _f(p.get("credit_theo")), _f(r.get("credit_fill"))
        entry = (ct - cf) * 100 * qty if ct is not None and cf is not None else None
        ev, xf = _f(p.get("exit_value_theo")), _f(r.get("close_fill"))
        exit_ = (xf - ev) * 100 * qty if by_order and ev is not None and xf is not None else None
        out.append({"position_id": r["position_id"], "strategy": strat_of(r["position_id"]),
                    "day": r["position_id"][:10], "paper": round(paper, 2), "live_net": round(live_net, 2),
                    "fees": round(fees, 2), "entry_slip": None if entry is None else round(entry, 2),
                    "exit_slip": None if exit_ is None else round(exit_, 2),
                    "shortfall": round(paper - live_net, 2)})
    return sorted(out, key=lambda x: x["position_id"])


def summarize(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["strategy"]].append(r)
    rep = {}
    for s, rs in sorted(by.items()):
        def agg(xs):
            paper = sum(x["paper"] for x in xs)
            live = sum(x["live_net"] for x in xs)
            ent = [x["entry_slip"] for x in xs if x["entry_slip"] is not None]
            ex = [x["exit_slip"] for x in xs if x["exit_slip"] is not None]
            return {
                "trades": len(xs), "paper": round(paper, 2), "live_net": round(live, 2),
                "capture": round(live / paper, 2) if paper > 0 else None,
                "shortfall_per_trade": round((paper - live) / len(xs), 2) if xs else 0.0,
                "entry_slip_per_trade": round(sum(ent) / len(ent), 2) if ent else None,
                "exit_slip_per_close": round(sum(ex) / len(ex), 2) if ex else None,
                "fees_per_trade": round(sum(x["fees"] for x in xs) / len(xs), 2) if xs else 0.0,
                "win_live": round(sum(x["live_net"] > 0 for x in xs) / len(xs), 2) if xs else None,
                "win_paper": round(sum(x["paper"] > 0 for x in xs) / len(xs), 2) if xs else None,
            }
        allt, recent = agg(rs), agg(rs[-RECENT:])
        flags = []
        if recent["trades"] >= 10:
            if recent["paper"] > 0 and (recent["capture"] or 0) < 0.5:
                flags.append(f"DRIFT: last {recent['trades']} trades kept {round(100 * (recent['capture'] or 0))}% of the paper edge")
            if recent["win_paper"] is not None and recent["win_live"] is not None \
                    and recent["win_live"] < recent["win_paper"] - 0.15:
                flags.append(f"DRIFT: live win rate {round(100 * recent['win_live'])}% vs paper {round(100 * recent['win_paper'])}% on the same trades")
        rep[s] = {"all": allt, "recent": recent, "flags": flags}
    return rep


def text(rep):
    lines = ["Live trading cost & drift (every live trade vs its exact paper twin; + = cost, - = better than paper)"]
    for s, v in rep.items():
        a, r = v["all"], v["recent"]
        cap = f"{round(100 * a['capture'])}%" if a["capture"] is not None else "n/a"
        lines.append(
            f"  {s:5s} {a['trades']:4d} trades  paper ${a['paper']:>9,.0f}  live ${a['live_net']:>9,.0f}  "
            f"kept {cap:>5s}  cost/trade ${a['shortfall_per_trade']:.2f} "
            f"(entry ${a['entry_slip_per_trade'] if a['entry_slip_per_trade'] is not None else 'n/a'}, "
            f"exit ${a['exit_slip_per_close'] if a['exit_slip_per_close'] is not None else 'n/a'}, fees ${a['fees_per_trade']:.2f})")
        for f in v["flags"]:
            lines.append(f"        ⚠ {f}")
    return "\n".join(lines)


def build(live_path=LIVE, paper_path=PAPER):
    live = list(csv.DictReader(open(live_path)))
    paper = list(csv.DictReader(open(paper_path)))
    return summarize(pairs(live, paper))


if __name__ == "__main__":
    rep = build()
    print(text(rep))
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(rep, indent=1))
