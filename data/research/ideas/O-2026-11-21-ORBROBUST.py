"""O-2026-11-21-ORBROBUST — Options team, league round 2 (2026-11-21), lab.
Is ORB's paper edge robust enough to be the options desk's next candidate?

HONESTY NOTE (read first): this is NOT a blind pre-registration. Before
writing it the team saw ORB's whole-life paper total (+$11,732 on
pnl_actual, 51 sessions) and its 2026-10-10 6-week gate review (+$126 /
PF 1.02 over 22 sessions, "one +$967 lottery day", RETIRED.md footer).
Because the outcome direction is known, the bar is set as a ROBUSTNESS
test that a few lucky days or optimistic fills could not pass.

CONTEXT: the owner switched off every option module; ORB (opening-range
breakout, one 30-wide debit vertical per day at the first breakout check
10:30 / 11:30 / 13:00, stop at half the debit, else held to settlement)
never traded real money beyond 4 rows, so its live fill cost is unknown.
Debit verticals have no short-tail risk beyond the debit, unlike the
condor family. OCB (calls only, paper since 2026-10-16) is reported
beside it, not judged.

HYPOTHESIS (written knowing the total, bar fixed before any run): ORB's
confirm-window edge survives BOTH (a) removing its 2 best confirm days and
(b) an extra $10 per trade of fill cost on top of the SIM's $0.05/leg-event.

MEASURE: ORB day pnl_actual (one trade per day) minus $10; drop the 2
largest confirm days; day-bootstrap P(mean > 0). Reported beside it: raw
confirm stats, win rate, average win / loss, max drawdown, P with only the
best day removed, and the same for develop and OCB.

DATA-TIMING: each trade's direction reads the 09:30-10:00 opening range
and the breakout at the check time (both before entry); it earns to its
own same-day exit. Sessions <= CUTOFF.

SPLIT (pre-declared): develop = ORB sessions <= 2026-10-09 (the 6-week
gate window); confirm = 2026-10-12 .. CUTOFF.

PASS CRITERION: confirm robust mean (cost +$10, best 2 days removed) > 0
with day-bootstrap P >= P_REQ, AND develop raw mean > 0.
Family "O-ORB", trials 1, but P_REQ = 0.95 (not 0.90) because the outcome
direction was known when the script was written.
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

ID = "O-2026-11-21-ORBROBUST"
FAMILY, FAMILY_TRIALS = "O-ORB", 1
P_REQ = 0.95
DEV_END, CONF_START = "2026-10-09", "2026-10-12"
EXTRA_COST, DROP_BEST = 10.0, 2


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


def max_dd(series):
    peak = cum = dd = 0.0
    for v in series:
        cum += v
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return dd


def drop_best(x, k):
    s = sorted(x)
    return s[:-k] if len(s) > k else []


def window(strategy, lo, hi):
    sides = [s for s in closed_sides(strategy, "pnl_actual") if lo <= s["date"] <= hi]
    dp = day_pnl(sides)
    days = sorted(dp)
    x = [dp[d] for d in days]
    trades = [s["pnl"] for s in sides]
    wins = [v for v in trades if v > 0]
    losses = [v for v in trades if v <= 0]
    robust = drop_best([v - EXTRA_COST * sum(1 for s in sides if s["date"] == d)
                        for d, v in zip(days, x)], DROP_BEST)
    return {
        "sessions": len(x), "trades": len(trades), "sum": r2(sum(x)), "mean_day": r2(mean(x)),
        "p_boot_mean_gt0": boot_pos(x), "ci95_mean_day": boot_ci(x),
        "p_boot_without_best_day": boot_pos(drop_best(x, 1)),
        "win_rate": r2(len(wins) / len(trades)) if trades else None,
        "avg_win": r2(mean(wins)), "avg_loss": r2(mean(losses)),
        "max_drawdown": r2(max_dd(x)),
        "robust_mean_day": r2(mean(robust)), "robust_sum": r2(sum(robust)),
        "p_boot_robust_gt0": boot_pos(robust),
    }


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": P_REQ, "cutoff": CUTOFF, "extra_cost_per_trade": EXTRA_COST,
           "dropped_best_days": DROP_BEST, "blind": False}
    res["develop"] = window("ORB", "0000", DEV_END)
    res["confirm"] = window("ORB", CONF_START, CUTOFF)
    res["whole_life"] = window("ORB", "0000", CUTOFF)
    res["ocb_whole_life_info"] = window("OCB", "0000", CUTOFF)
    c, d = res["confirm"], res["develop"]
    passed = (c["robust_mean_day"] is not None and c["robust_mean_day"] > 0
              and c["p_boot_robust_gt0"] is not None and c["p_boot_robust_gt0"] >= P_REQ
              and d["mean_day"] is not None and d["mean_day"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
