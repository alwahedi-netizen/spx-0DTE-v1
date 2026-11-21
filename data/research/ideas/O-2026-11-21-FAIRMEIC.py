"""O-2026-11-21-FAIRMEIC — Options team, league round 2 (2026-11-21), lab.
Does paper MEIC make money once it is priced with LIVE-measured costs?

CONTEXT: the re-arm question in one number. Paper MEIC (52 sessions,
2026-09-08 .. 11-20) is -$1,550 at SIM fills and +$3,622 at mid; the SIM
charges a flat $0.05 per leg-event that live did not pay on filled sides
(theme 32; O-2026-11-21-FAIRFILL measures the fair cost). This study
prices paper MEIC with costs fitted ONLY on the live develop window and
asks whether the strategy itself (all sides assumed filled) is positive on
the later sessions. Skipped live orders (rejections, unfilled reprices)
are NOT modelled here: they are the other half of the live gap (theme 32)
and are measured in O-2026-11-21-LIVEPNL, which shares this family.

HYPOTHESIS (written before any run): paper MEIC's mean daily P&L at fair
fills is positive in the confirm window.

MEASURE: fair pnl per paper MEIC side = pnl_theo - cost[paper exit type],
cost[t] = mean(pnl_theo - pnl_live) over filled real-money live MEIC sides
of the develop window with paper exit type t (TP / STOPPED / EXPIRED),
excluding live HALT exits and shifted strikes (fit identical to
O-2026-11-21-FAIRFILL; a type absent from develop uses the all-type mean).
Summed per session; sessions are the resampling unit. Reported beside it:
the same windows at SIM (pnl_actual) and at mid (pnl_theo), the worst
day, P(mean > 0) without the best confirm day, and the sessions needed for
a one-sided t of 1.645 at the observed mean and sd.

DATA-TIMING: costs are fitted on live sessions <= 2026-10-16 and applied
unchanged to later paper sessions; nothing reads a later date. Paper
sessions <= CUTOFF (paper ran through 2026-11-20 after the live disarm).

SPLIT (pre-declared, aligned with the cost-fit window): develop = paper
MEIC sessions <= 2026-10-16; confirm = 2026-10-19 .. CUTOFF.

PASS CRITERION: confirm mean daily fair P&L > 0 with day-bootstrap
P(mean > 0) >= P_REQ, AND develop mean daily fair P&L > 0.
Family "O-MEICEDGE" (this + O-2026-11-21-LIVEPNL), trials 2 -> P_REQ 0.95.
"""
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-20"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261121, 10000

ID = "O-2026-11-21-FAIRMEIC"
FAMILY, FAMILY_TRIALS = "O-MEICEDGE", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END = "2026-10-16"
CONF_START = "2026-10-19"


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


def fit_costs():
    paper = {r["position_id"]: r for r in read("positions.csv")}
    g = defaultdict(list)
    for r in live_rows("MEIC"):
        if r["date"] > DEV_END:
            continue
        if fnum(r["pnl_live"]) is None or r["exit_reason"] == "HALT" or (r.get("shift") or "").strip():
            continue
        p = paper.get(r["position_id"])
        if not p or fnum(p["pnl_theo"]) is None:
            continue
        g[p["exit_reason"]].append(float(p["pnl_theo"]) - float(r["pnl_live"]))
    costs = {k: mean(v) for k, v in g.items()}
    costs["_ALL"] = mean([c for v in g.values() for c in v])
    return costs, {k: len(v) for k, v in g.items()}


def sd(x):
    if len(x) < 2:
        return None
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def window(sides, costs, lo, hi):
    fair_d, sim_d, theo_d = defaultdict(float), defaultdict(float), defaultdict(float)
    for s in sides:
        if not (lo <= s["date"] <= hi) or fnum(s["pnl_theo"]) is None:
            continue
        th = float(s["pnl_theo"])
        fair_d[s["date"]] += th - costs.get(s["exit_reason"], costs["_ALL"])
        sim_d[s["date"]] += s["pnl"]
        theo_d[s["date"]] += th
    days = sorted(fair_d)
    x = [fair_d[d] for d in days]
    best = max(x) if x else None
    x_nb = list(x)
    if best is not None:
        x_nb.remove(best)
    m, s_ = mean(x), sd(x)
    return {
        "sessions": len(x),
        "fair_sum": r2(sum(x)), "fair_mean_day": r2(m), "fair_sd_day": r2(s_),
        "p_boot_fair_gt0": boot_pos(x), "ci95_fair_mean_day": boot_ci(x),
        "p_boot_fair_gt0_without_best_day": boot_pos(x_nb),
        "fair_worst_day": r2(min(x, default=None)),
        "sim_sum": r2(sum(sim_d.values())), "theo_sum": r2(sum(theo_d.values())),
        "sessions_needed_t1645": (int(math.ceil((1.645 * s_ / m) ** 2))
                                  if m and s_ and m > 0 else None),
    }


def main():
    costs, counts = fit_costs()
    sides = closed_sides("MEIC", "pnl_actual")
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF,
           "fair_costs_per_side": {k: r2(v) for k, v in costs.items()},
           "fit_sides_by_type": counts}
    res["develop"] = window(sides, costs, "0000", DEV_END)
    res["confirm"] = window(sides, costs, CONF_START, CUTOFF)
    res["whole_life"] = window(sides, costs, "0000", CUTOFF)
    c, d = res["confirm"], res["develop"]
    passed = (c["fair_mean_day"] is not None and c["fair_mean_day"] > 0
              and c["p_boot_fair_gt0"] is not None and c["p_boot_fair_gt0"] >= P_REQ
              and d["fair_mean_day"] is not None and d["fair_mean_day"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
