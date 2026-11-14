"""O-2026-11-14-ENTRYSLOT — Options team, league round 1 (2026-11-14), lab.
Do MEIC's early slots earn more per side than its late slots?

CONTEXT: MEIC ladders six condors 12:00-14:30, each walked to a $1.50
per-side credit. Later entries collect the same credit with less time left,
so their shorts sit CLOSER to spot (more gamma per dollar of credit) and a
late afternoon move has less time to mean-revert. MIIE (paper since
2026-11-12) tests an earlier ladder (11:00-13:30); this study asks whether
the existing journal already shows a slot gradient.

HYPOTHESIS (written before any run): per-side P&L of the early slots
(12:00, 12:30, 13:00) exceeds that of the late slots (13:30, 14:00, 14:30)
on the same day.

MEASURE: paired by day — for each MEIC session with at least one early
AND one late side: d = mean per-side pnl_actual (early) - (late). Days are
the resampling unit. Caveat stated up front: late slots are skipped by the
shared risk budget (SKIP/RISK) more often; pairing within a day removes the
day-level regime but not that selection.

DATA-TIMING: the slot label is the entry time itself (known at entry);
each side earns to its own journaled exit the same day (0DTE).
Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09; confirm =
2026-10-12 .. CUTOFF.

PASS CRITERION: confirm mean d > 0 with day-bootstrap P >= P_REQ, AND
develop mean d > 0. Family "O-ENTRYTIME", trials 1 -> P_REQ = 0.90.
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

ID = "O-2026-11-14-ENTRYSLOT"
FAMILY, FAMILY_TRIALS = "O-ENTRYTIME", 1
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END = "2026-10-09"
EARLY = {"12:00", "12:30", "13:00"}
LATE = {"13:30", "14:00", "14:30"}


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


def window(sides, lo, hi):
    by_day = defaultdict(lambda: {"e": [], "l": []})
    by_slot = defaultdict(list)
    for s in sides:
        if not (lo <= s["date"] <= hi):
            continue
        by_slot[s["slot"]].append(s["pnl"])
        if s["slot"] in EARLY:
            by_day[s["date"]]["e"].append(s["pnl"])
        elif s["slot"] in LATE:
            by_day[s["date"]]["l"].append(s["pnl"])
    d = [mean(v["e"]) - mean(v["l"]) for _, v in sorted(by_day.items()) if v["e"] and v["l"]]
    return {
        "paired_days": len(d),
        "mean_d_per_side": r2(mean(d)),
        "p_boot_d_gt0": boot_pos(d),
        "per_slot": {k: [len(v), r2(mean(v)), r2(sum(v))] for k, v in sorted(by_slot.items())},
    }


def main():
    sides = closed_sides("MEIC", "pnl_actual")
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF,
           "per_slot_format": "[sides, mean per side, sum]"}
    dev = window(sides, "0000", DEV_END)
    conf = window(sides, "2026-10-12", CUTOFF)
    res["develop"], res["confirm"] = dev, conf
    p = conf["p_boot_d_gt0"]
    passed = (p is not None and p >= P_REQ and conf["mean_d_per_side"] > 0
              and dev["mean_d_per_side"] is not None and dev["mean_d_per_side"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
