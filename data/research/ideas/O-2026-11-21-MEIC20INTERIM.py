"""O-2026-11-21-MEIC20INTERIM — Options team, league round 2 (2026-11-21), lab.
INTERIM read of the MEIC 2.0 paper lanes against MEIC on the SAME days.

HONESTY NOTE (read first): the lanes started 2026-11-12, so this is 7
sessions. The pre-registered gate O-2026-11-14-MEIC20GATE (15 sessions,
earliest ~2026-12-03) stays THE judgement and is not replaced or moved by
this study. A PASS here means only "on track, keep collecting"; it cannot
promote a lane to live. MIIL (same-side lockout) is left out because its
hypothesis is tested separately, replication first, in
O-2026-11-21-LOCKOUTOOS (counting it twice would double-count evidence).

HYPOTHESIS (written before any run): each structural change — MIIS (stop
1.5x the condor credit), MIIE (ladder 11:00-13:30), MIIF ($1.00 shorts),
MIIW (50-point wings) — earns more per session than MEIC on the same
sessions (paired day difference > 0).

MEASURE: d = lane day pnl_actual - MEIC day pnl_actual over the union of
sessions in [2026-11-12, CUTOFF] where either closed a side (a missing
strategy-day counts $0). Lanes run on their own risk budget, so MEIC's
entries are never starved by them (paper_engine own_budget). Reported
beside it: the same on pnl_theo (mid, friction-neutral — MIIF's $1.00
credits pay the same $10 SIM friction on less premium), each lane's and
MEIC's worst day, and per-lane totals.

DATA-TIMING: nothing is predicted; same-day realised outcomes of rules
fixed in paper_engine.py since 2026-11-11. Sessions <= CUTOFF.

SPLIT (pre-declared): develop = 2026-11-12 .. 2026-11-16 (3 sessions);
confirm = 2026-11-17 .. CUTOFF (4 sessions).

PASS CRITERION (per lane): develop mean d > 0 AND confirm mean d > 0 AND
the all-7-session day-bootstrap P(mean d > 0) >= P_LANE AND lane worst day
>= MEIC worst day (the MEIC20GATE tail condition). P_LANE = 1 - 0.10/4 =
0.975 (4 lanes). Study verdict = PASS if any lane passes (lanes listed).
Family "O-MEIC20", trials 1 (MEIC20GATE was pre-registered, never run).
"""
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-20"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261121, 10000

ID = "O-2026-11-21-MEIC20INTERIM"
FAMILY, FAMILY_TRIALS = "O-MEIC20", 1
LANES = ("MIIS", "MIIE", "MIIF", "MIIW")
P_LANE = 1 - 0.10 / len(LANES)
START, DEV_END, CONF_START = "2026-11-12", "2026-11-16", "2026-11-17"


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


def day_map(strategy, field):
    return {d: v for d, v in day_pnl(closed_sides(strategy, field)).items()
            if START <= d <= CUTOFF}


def lane_result(lane, field, base):
    lm = day_map(lane, field)
    days = sorted(set(lm) | set(base))
    d_all = [lm.get(d, 0.0) - base.get(d, 0.0) for d in days]
    d_dev = [lm.get(d, 0.0) - base.get(d, 0.0) for d in days if d <= DEV_END]
    d_conf = [lm.get(d, 0.0) - base.get(d, 0.0) for d in days if d >= CONF_START]
    lane_days = [lm.get(d, 0.0) for d in days]
    base_days = [base.get(d, 0.0) for d in days]
    return {
        "sessions": len(days),
        "lane_sum": r2(sum(lane_days)), "meic_sum": r2(sum(base_days)),
        "mean_d_all": r2(mean(d_all)), "mean_d_develop": r2(mean(d_dev)),
        "mean_d_confirm": r2(mean(d_conf)), "p_boot_d_gt0_all": boot_pos(d_all),
        "lane_worst_day": r2(min(lane_days, default=None)),
        "meic_worst_day": r2(min(base_days, default=None)),
    }


def passes(r):
    return (r["mean_d_develop"] is not None and r["mean_d_develop"] > 0
            and r["mean_d_confirm"] is not None and r["mean_d_confirm"] > 0
            and r["p_boot_d_gt0_all"] is not None and r["p_boot_d_gt0_all"] >= P_LANE
            and r["lane_worst_day"] is not None and r["lane_worst_day"] >= r["meic_worst_day"])


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_lane": round(P_LANE, 4), "cutoff": CUTOFF, "interim": True,
           "note": "INTERIM (7 sessions). MEIC20GATE (15 sessions) stays the judgement."}
    base_a = day_map("MEIC", "pnl_actual")
    base_t = day_map("MEIC", "pnl_theo")
    res["primary_pnl_actual"], res["secondary_pnl_theo"] = {}, {}
    winners = []
    for lane in LANES:
        ra = lane_result(lane, "pnl_actual", base_a)
        ra["lane_pass"] = passes(ra)
        res["primary_pnl_actual"][lane] = ra
        res["secondary_pnl_theo"][lane] = lane_result(lane, "pnl_theo", base_t)
        if ra["lane_pass"]:
            winners.append(lane)
    res["lanes_passing"] = winners
    res["verdict"] = "PASS" if winners else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
