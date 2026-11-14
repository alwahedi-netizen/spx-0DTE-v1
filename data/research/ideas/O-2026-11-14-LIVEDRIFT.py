"""O-2026-11-14-LIVEDRIFT — Options team, league round 1 (2026-11-14), lab.
Is the paper journal a faithful proxy for live MEIC (per filled side)?

CONTEXT: every paper lane (MNG, MEIC 2.0 MIIS/MIIE/MIIF/MIIW/MIIL) is judged
on paper with a simple fill model (entry credit - $0.05, stop/TP exit +
$0.05, no fees). Live MEIC mirrors the paper journal side by side
(same position_id), so the paper-to-live haircut is measurable directly.

HYPOTHESIS (written before any run): on sides that actually filled live,
live P&L net of fees is within $10 per side of the paper twin's pnl_actual
on average (fees are ~$4.72 per round trip at $1.18/leg; the paper's $0.05
slippage each way should roughly cover the rest).

MEASURE: real-money (non "dry-") live MEIC sides with a fill (pnl_live set),
excluding exit_reason HALT (a deliberate rail difference, measured in
O-2026-11-14-HALTVALUE) and shifted strikes. drift = pnl_live - pnl_actual.
Decomposed: entry = (credit_fill - paper credit_actual) x 100; exit =
(paper exit_value_actual - close_fill) x 100; fees+other = the remainder.
Close failures that cash-settled stay IN (they are real execution).

DATA-TIMING: nothing is predicted; both sides are realized outcomes of the
same position on the same day. Sessions <= CUTOFF.

SPLIT (pre-declared): develop = live sessions <= 2026-10-16; confirm =
2026-10-19 .. CUTOFF.

PASS CRITERION (confirm window): mean drift per side >= -10 AND the lower
end of the day-bootstrap 95% interval of the per-day mean drift >= -25.
A FAIL means paper overstates live; the confirm mean is then the haircut
to apply to every paper lane. Family "O-LIVEDRIFT" (this + MISSEDFILLS),
trials 2 (interval 95%, i.e. 1 - 0.10/2 two-sided-equivalent).
"""
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-13"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261114, 10000

ID = "O-2026-11-14-LIVEDRIFT"
FAMILY, FAMILY_TRIALS = "O-LIVEDRIFT", 2
LIVE_DEV_END = "2026-10-16"
MEAN_FLOOR, CI_FLOOR = -10.0, -25.0


# ── common journal helpers (identical in every O-2026-11-14 script) ─────────
def read(name):
    with open(PAPER / name, newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_pid(pid):
    """'2026-09-08-MEIC-12:00-PUT' -> (date, strategy, slot, side)."""
    d, rest = pid[:10], pid[11:].split("-")
    return d, rest[0], (rest[1] if len(rest) >= 3 else ""), rest[-1]


def closed_sides(strategy="MEIC", field="pnl_actual"):
    out = []
    for r in read("positions.csv"):
        if r["strategy"] != strategy or not r["exit_ts"]:
            continue
        d, _, slot, side = parse_pid(r["position_id"])
        if d > CUTOFF or fnum(r[field]) is None:
            continue
        out.append(dict(r, date=d, slot=slot, pnl=float(r[field])))
    return out


def day_pnl(sides):
    g = defaultdict(float)
    for s in sides:
        g[s["date"]] += s["pnl"]
    return dict(g)


def day_tags():
    """First OK day.csv row per date (the 09:00 pre-market row)."""
    out = {}
    for r in read("day.csv"):
        if r.get("status") == "OK" and r["date"] not in out:
            out[r["date"]] = r
    return out


def mean(x):
    return sum(x) / len(x) if x else None


def boot_diff(a, b, seed=SEED, n=NBOOT):
    """P(mean(a) - mean(b) > 0), resampling each group's days."""
    if len(a) < 2 or len(b) < 2:
        return None
    rng, hit = random.Random(seed), 0
    for _ in range(n):
        if mean([rng.choice(a) for _ in a]) - mean([rng.choice(b) for _ in b]) > 0:
            hit += 1
    return hit / n


def r2(x):
    return None if x is None else round(x, 2)


def boot_pos(x, seed=SEED, n=NBOOT):
    """P(mean(x) > 0), resampling days."""
    if len(x) < 2:
        return None
    rng, hit = random.Random(seed), 0
    for _ in range(n):
        if mean([rng.choice(x) for _ in x]) > 0:
            hit += 1
    return hit / n


def boot_ci(x, lo=0.025, hi=0.975, seed=SEED, n=NBOOT):
    """Percentile interval of mean(x), resampling days."""
    if len(x) < 2:
        return None
    rng = random.Random(seed)
    ms = sorted(mean([rng.choice(x) for _ in x]) for _ in range(n))
    return [round(ms[int(lo * (n - 1))], 2), round(ms[int(hi * (n - 1))], 2)]


def pctl(x, q):
    """Linear-interpolated q-quantile (0..1) of x."""
    s = sorted(x)
    if not s:
        return None
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def live_rows(strategy="MEIC"):
    """Real-money live ledger rows of one strategy (dry-run rehearsals out)."""
    out = []
    for r in read("live/live_trades.csv"):
        d, strat, slot, side = parse_pid(r["position_id"])
        if strat != strategy or d > CUTOFF or str(r["order_id"]).startswith("dry"):
            continue
        out.append(dict(r, date=d, slot=slot))
    return out


# ─────────────────────────────────────────────────────────────────────────────


def analyse(live, paper, lo, hi):
    rows = [r for r in live if lo <= r["date"] <= hi and fnum(r["pnl_live"]) is not None
            and r["exit_reason"] != "HALT" and not (r.get("shift") or "").strip()
            and r["position_id"] in paper]
    drift, ent, ext, oth = [], [], [], []
    by_day = defaultdict(list)
    by_reason = defaultdict(list)
    for r in rows:
        p = paper[r["position_id"]]
        d = fnum(r["pnl_live"]) - float(p["pnl_actual"])
        e = ((fnum(r["credit_fill"]) or 0.0) - (fnum(p["credit_actual"]) or 0.0)) * 100
        x = ((fnum(p["exit_value_actual"]) or 0.0) - (fnum(r["close_fill"]) or 0.0)) * 100
        drift.append(d)
        ent.append(e)
        ext.append(x)
        oth.append(d - e - x)
        by_day[r["date"]].append(d)
        by_reason[r["exit_reason"] or "?"].append(d)
    day_means = [mean(v) for _, v in sorted(by_day.items())]
    return {
        "sides": len(rows), "days": len(by_day),
        "mean_drift_per_side": r2(mean(drift)),
        "sum_drift": r2(sum(drift)),
        "mean_entry_component": r2(mean(ent)),
        "mean_exit_component": r2(mean(ext)),
        "mean_fees_other_component": r2(mean(oth)),
        "ci95_day_mean_drift": boot_ci(day_means),
        "mean_drift_by_exit_reason": {k: [len(v), r2(mean(v))] for k, v in sorted(by_reason.items())},
        "paper_pnl_same_sides": r2(sum(float(paper[r["position_id"]]["pnl_actual"]) for r in rows)),
        "live_pnl_same_sides": r2(sum(fnum(r["pnl_live"]) for r in rows)),
    }


def main():
    paper = {r["position_id"]: r for r in read("positions.csv")
             if r["exit_ts"] and fnum(r["pnl_actual"]) is not None}
    live = live_rows("MEIC")
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS, "cutoff": CUTOFF,
           "mean_floor": MEAN_FLOOR, "ci_floor": CI_FLOOR}
    res["develop"] = analyse(live, paper, "0000", LIVE_DEV_END)
    conf = analyse(live, paper, "2026-10-19", CUTOFF)
    res["confirm"] = conf
    ci = conf["ci95_day_mean_drift"]
    passed = (conf["mean_drift_per_side"] is not None
              and conf["mean_drift_per_side"] >= MEAN_FLOOR
              and ci is not None and ci[0] >= CI_FLOOR)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
