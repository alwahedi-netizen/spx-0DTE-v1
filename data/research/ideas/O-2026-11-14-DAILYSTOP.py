"""O-2026-11-14-DAILYSTOP — Options team, league round 1 (2026-11-14), lab.
Does a MEIC daily stop on NEW ENTRIES earn its keep on paper?

CONTEXT: live MEIC has a per-strategy daily stop (live_meic.py STRATS:
realized <= -$1,000 halts AND flattens); paper MEIC has none, only the
shared risk-budget skip. KNOWLEDGE theme 27: after a side is stopped, later
same-day entries on that side lost on paper and live (in-sample, both
halves) — MIIL tests the same-SIDE lockout on paper since 2026-11-12. This
study tests the coarser rail that is already live: stop opening new MEIC
condors once the day's realized MEIC P&L is <= -X. (The "flatten" half of
the live rail cannot be replayed on paper — no intraday marks are journaled;
O-2026-11-14-HALTVALUE measures it from live fills.)

HYPOTHESIS (written before any run): MEIC losses cluster on trend days;
once realized day P&L reaches -$1,000, the remaining slots of that day have
negative expectation, so skipping them raises total P&L.

RULE (replayed exactly from the journal, no marks needed): MEIC entries in
time order; an entry at signal_ts e is KEPT unless the realized P&L of
already-kept MEIC sides with exit_ts < e is <= -X; once one entry is
skipped for this reason, every later entry that day is skipped too. Kept
sides keep their journaled exit and pnl_actual. X = 1000 (the live rail);
neighbours X = 500, 750, 1250, 1500.

DATA-TIMING: the halt decision at entry time e reads only exits stamped
before e on the same day (journal exit_ts); entries earn to their own
journaled exit the same day (0DTE). Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09 (23 sessions);
confirm = 2026-10-12 .. CUTOFF.

PASS CRITERION: in confirm, sum over days of (rule - baseline) > 0 with
day-bootstrap P(mean delta > 0) >= P_REQ; develop delta also > 0; and >= 3
of the 4 neighbour X values also give a positive confirm delta.
Family "O-DAILYSTOP" (this + HALTVALUE), trials 2 -> P_REQ = 0.95.
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

ID = "O-2026-11-14-DAILYSTOP"
FAMILY, FAMILY_TRIALS = "O-DAILYSTOP", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END = "2026-10-09"
X_MAIN, X_NEIGH = 1000.0, (500.0, 750.0, 1250.0, 1500.0)


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


def replay(sides, x):
    """Day -> (baseline pnl, rule pnl, entries skipped)."""
    by_day = defaultdict(list)
    for s in sides:
        by_day[s["date"]].append(s)
    out = {}
    for d, ss in by_day.items():
        entries = sorted({s["signal_ts"] for s in ss})
        kept, halted, skipped = [], False, 0
        for e in entries:
            if not halted:
                realized = sum(k["pnl"] for k in kept if k["exit_ts"] < e)
                halted = realized <= -x
            group = [s for s in ss if s["signal_ts"] == e]
            if halted:
                skipped += 1
            else:
                kept.extend(group)
        out[d] = (sum(s["pnl"] for s in ss), sum(k["pnl"] for k in kept), skipped)
    return out


def window(rep, lo, hi):
    days = sorted(d for d in rep if lo <= d <= hi)
    delta = [rep[d][1] - rep[d][0] for d in days]
    return {
        "days": len(days),
        "baseline_sum": r2(sum(rep[d][0] for d in days)),
        "rule_sum": r2(sum(rep[d][1] for d in days)),
        "delta_sum": r2(sum(delta)),
        "days_halted": sum(1 for d in days if rep[d][2] > 0),
        "entries_skipped": sum(rep[d][2] for d in days),
        "worst_day_baseline": r2(min((rep[d][0] for d in days), default=None)),
        "worst_day_rule": r2(min((rep[d][1] for d in days), default=None)),
        "p_boot_delta_gt0": boot_pos(delta),
    }, delta


def main():
    sides = closed_sides("MEIC", "pnl_actual")
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF, "x_main": X_MAIN}
    rep = replay(sides, X_MAIN)
    dev, _ = window(rep, "0000", DEV_END)
    conf, delta = window(rep, "2026-10-12", CUTOFF)
    res["develop"], res["confirm"] = dev, conf
    neigh = {}
    for x in X_NEIGH:
        w, _ = window(replay(sides, x), "2026-10-12", CUTOFF)
        neigh[str(int(x))] = w["delta_sum"]
    res["neighbours_confirm_delta"] = neigh
    n_ok = sum(1 for v in neigh.values() if v is not None and v > 0)
    res["neighbours_positive"] = f"{n_ok}/{len(X_NEIGH)}"
    p = conf["p_boot_delta_gt0"]
    passed = (conf["delta_sum"] > 0 and p is not None and p >= P_REQ
              and dev["delta_sum"] > 0 and n_ok >= 3)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
