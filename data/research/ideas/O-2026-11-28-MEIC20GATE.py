"""O-2026-11-28-MEIC20GATE — Options team, league round 3 (2026-11-28), lab.
The MEIC 2.0 judgement, frozen in code BEFORE its data exists.

WHAT THIS IS: the script for the gate pre-registered in round 1
(ideas.csv O-2026-11-14-MEIC20GATE, never run): "lane PASS = mean paired
day diff (lane - MEIC) > 0 with day-bootstrap P >= 0.98 (5 lanes -> 1 -
0.10/5) over the first 15 sessions from 2026-11-12, plus worst day no worse
than MEIC's." The lanes have 11 sessions at writing (11-12 .. 11-27); the
15th MEIC session is expected on 2026-12-03. Until 15 sessions exist the
script prints verdict NOT_READY and NO lane statistic (no peeking, no
trial spent). Run it once, on or after the 15th session; that run is the
judgement (one trial, family O-MEIC20).

LANES (paper only, own risk budgets, each changes ONE thing vs MEIC):
MIIS stop 1.5x condor credit; MIIE ladder 11:00-13:30; MIIF $1.00 shorts;
MIIW 50-point wings; MIIL same-side lockout. MIIL's evidence so far is a
trend-week effect (theme 36; LOCKOUTOOS) — this gate judges it on the same
terms as the others; a MIIL pass on mostly trend sessions is to be reported
with that caveat and the trend/range session count (descriptive).

HYPOTHESIS (round 1, unchanged): each lane earns more per session than MEIC
on the same sessions (paired day difference > 0).

MEASURE: sessions = the first 15 MEIC session dates >= 2026-11-12 (a MEIC
session = a date with >= 1 closed MEIC side). d = lane day pnl_actual -
MEIC day pnl_actual on each (a lane with no closed side that day counts
$0). Day-resampled bootstrap P(mean d > 0). Tail: lane worst day >= MEIC
worst day. Reported (NOT judged): pnl_theo version; a first-8 / last-7
chronological split of mean d; the count of "range" sessions (no MEIC
side stopped) and "whipsaw" sessions (MEIC stopped on both PUT and CALL).

DATA-TIMING: nothing is predicted; same-day realised outcomes of rules fixed
in paper_engine.py since 2026-11-11. Early-close rule: on 2026-11-27 (and
any date in EARLY_CLOSE) rows with signal_ts at/after the 13:00 close are
dropped for every strategy (league brief). 2026-11-27 counts as a session
(MEIC traded its 12:00/12:30 slots).

SPLIT: the round-1 pre-registration has no develop/confirm split (the lanes
are themselves forward tests); the first-8 / last-7 split is reported only.

PASS CRITERION (per lane, round 1): mean d > 0 AND P(mean d > 0) >= 0.98
AND lane worst day >= MEIC worst day. Study verdict = PASS if any lane
passes (listed); NOT_READY if fewer than 15 MEIC sessions exist.
"""
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "9999-12-31"            # sessions are fixed by count (first 15), not by date
SEED, NBOOT = 20261128, 10000

ID = "O-2026-11-28-MEIC20GATE"
FAMILY, FAMILY_TRIALS = "O-MEIC20", 1
LANES = ("MIIS", "MIIE", "MIIF", "MIIW", "MIIL")
P_LANE = 1 - 0.10 / len(LANES)
START, N_SESSIONS = "2026-11-12", 15
EARLY_CLOSE = {"2026-11-27": "13:00", "2026-12-24": "13:00"}

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


def keep(s):
    d = s["date"]
    return not (d in EARLY_CLOSE and s["signal_ts"][11:16] >= EARLY_CLOSE[d])


def sides(strategy, field):
    return [s for s in closed_sides(strategy, field) if keep(s)]


def lane_result(lane, field, base, days):
    lm = day_pnl([s for s in sides(lane, field) if s["date"] in days])
    d_all = [lm.get(d, 0.0) - base.get(d, 0.0) for d in days]
    lane_days = [lm.get(d, 0.0) for d in days]
    base_days = [base.get(d, 0.0) for d in days]
    return {
        "lane_sum": r2(sum(lane_days)), "meic_sum": r2(sum(base_days)),
        "mean_d": r2(mean(d_all)), "p_boot_d_gt0": boot_pos(d_all),
        "ci95_mean_d": boot_ci(d_all),
        "mean_d_first8": r2(mean(d_all[:8])), "mean_d_last7": r2(mean(d_all[8:])),
        "lane_worst_day": r2(min(lane_days)), "meic_worst_day": r2(min(base_days)),
        "lane_sessions_traded": sum(1 for d in days if d in lm),
    }


def passes(r):
    return (r["mean_d"] is not None and r["mean_d"] > 0
            and r["p_boot_d_gt0"] is not None and r["p_boot_d_gt0"] >= P_LANE
            and r["lane_worst_day"] >= r["meic_worst_day"])


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_lane": round(P_LANE, 4), "sessions_required": N_SESSIONS}
    meic = sides("MEIC", "pnl_actual")
    all_days = sorted({s["date"] for s in meic if s["date"] >= START})
    res["meic_sessions_available"] = len(all_days)
    if len(all_days) < N_SESSIONS:
        res["verdict"] = "NOT_READY"
        res["note"] = (f"{len(all_days)} of {N_SESSIONS} sessions; no statistic computed, "
                       "no trial spent. Re-run after the 15th MEIC session (~2026-12-03).")
        print(json.dumps(res, indent=1))
        return
    days = all_days[:N_SESSIONS]
    res["sessions"] = [days[0], days[-1]]
    base_a = day_pnl([s for s in meic if s["date"] in days])
    base_t = day_pnl([s for s in sides("MEIC", "pnl_theo") if s["date"] in days])
    # descriptive: whipsaw (both PUT and CALL stopped) vs range sessions for MEIC
    stopped = defaultdict(set)
    for s in meic:
        if s["date"] in days and s["exit_reason"] == "STOPPED":
            stopped[s["date"]].add(s["side"])
    res["meic_whipsaw_sessions"] = sum(1 for d in days if stopped[d] >= {"PUT", "CALL"})
    res["meic_range_sessions"] = sum(1 for d in days if not stopped[d])
    res["primary_pnl_actual"], res["secondary_pnl_theo"] = {}, {}
    winners = []
    for lane in LANES:
        ra = lane_result(lane, "pnl_actual", base_a, days)
        ra["lane_pass"] = passes(ra)
        res["primary_pnl_actual"][lane] = ra
        res["secondary_pnl_theo"][lane] = lane_result(lane, "pnl_theo", base_t, days)
        if ra["lane_pass"]:
            winners.append(lane)
    res["lanes_passing"] = winners
    res["verdict"] = "PASS" if winners else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
