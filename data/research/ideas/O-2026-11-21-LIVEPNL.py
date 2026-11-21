"""O-2026-11-21-LIVEPNL — Options team, league round 2 (2026-11-21), lab.
Did real-money MEIC have a positive expectancy net of fees?

CONTEXT: the owner disarmed every live option module on 2026-11-19 ("even
Meic kept losing money"). The live ledger's final figure is about +$963
over 327 filled sides (2026-09-23 .. 11-18), net of fees. This study gives
that record a pre-registered verdict and, whatever the verdict, the number
of further sessions a re-arm decision would need (power), so "keep off and
collect N more days" can be stated with an N.

HYPOTHESIS (written before any run): live MEIC's mean DAILY P&L, net of
fees, is positive.

MEASURE: real-money MEIC rows of data/paper/live/live_trades.csv (order_id
not "dry-"), pnl_live summed per session. A session = a date with at least
one real MEIC row (skipped rows count as $0, so days where every order was
rejected stay in as zero days). HALT exits and cash settlements stay in:
they are what the account actually booked. Rows whose note says fees were
added later (2026-11-15 fee fix) are counted and reported.

DATA-TIMING: nothing is predicted; each session's realised, fee-net P&L is
measured. Sessions <= CUTOFF (live trading ended 2026-11-18).

SPLIT (pre-declared, same as O-2026-11-14-LIVEDRIFT): develop = live
sessions <= 2026-10-16; confirm = 2026-10-19 .. CUTOFF.

PASS CRITERION: confirm mean daily P&L > 0 with day-bootstrap
P(mean > 0) >= P_REQ, AND develop mean daily P&L > 0.
Family "O-MEICEDGE" (this + O-2026-11-21-FAIRMEIC: the same hypothesis
"MEIC earns money after real costs"), trials 2 -> P_REQ = 1 - 0.10/2 = 0.95.

POWER (reported, not judged): sessions needed for a one-sided t of 1.645
at the whole-life mean and sd, n = (1.645 * sd / mean)^2, and at a mean of
+$50/day (the size that would matter to the owner).
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

ID = "O-2026-11-21-LIVEPNL"
FAMILY, FAMILY_TRIALS = "O-MEICEDGE", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
LIVE_DEV_END = "2026-10-16"
CONF_START = "2026-10-19"
MATTERS = 50.0                   # $/day a re-arm would need to be worth it


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


def sd(x):
    if len(x) < 2:
        return None
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def max_dd(series):
    peak = cum = dd = 0.0
    for v in series:
        cum += v
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return dd


def n_needed(m, s):
    if m is None or s is None or m <= 0:
        return None
    return int(math.ceil((1.645 * s / m) ** 2))


def summarise(days, rows, lo, hi):
    ds = [d for d in sorted(days) if lo <= d <= hi]
    x = [days[d] for d in ds]
    filled = [r for r in rows if lo <= r["date"] <= hi and fnum(r["pnl_live"]) is not None]
    skipped = [r for r in rows if lo <= r["date"] <= hi and r["status"] == "SKIPPED"]
    by_exit = defaultdict(lambda: [0, 0.0])
    for r in filled:
        k = r["exit_reason"] or r["status"]
        by_exit[k][0] += 1
        by_exit[k][1] += float(r["pnl_live"])
    return {
        "sessions": len(x), "filled_sides": len(filled), "skipped_sides": len(skipped),
        "sum": r2(sum(x)), "mean_day": r2(mean(x)), "sd_day": r2(sd(x)),
        "mean_per_filled_side": r2(mean([float(r["pnl_live"]) for r in filled])),
        "p_boot_mean_gt0": boot_pos(x), "ci95_mean_day": boot_ci(x),
        "worst_day": r2(min(x, default=None)), "best_day": r2(max(x, default=None)),
        "max_drawdown": r2(max_dd(x)),
        "by_exit_reason": {k: [v[0], r2(v[1])] for k, v in sorted(by_exit.items())},
    }


def main():
    rows = live_rows("MEIC")
    days = defaultdict(float)
    for r in rows:
        days[r["date"]] += fnum(r["pnl_live"]) or 0.0
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF,
           "fee_fixed_rows": sum(1 for r in rows if "fees added" in (r.get("note") or "")),
           "by_exit_reason_format": "[sides, sum pnl_live]"}
    res["whole_life"] = summarise(days, rows, "0000", CUTOFF)
    res["develop"] = summarise(days, rows, "0000", LIVE_DEV_END)
    res["confirm"] = summarise(days, rows, CONF_START, CUTOFF)
    w = res["whole_life"]
    x = [days[d] for d in sorted(days)]
    res["power"] = {
        "sessions_needed_at_observed_mean": n_needed(mean(x), sd(x)),
        "sessions_needed_at_50_per_day": n_needed(MATTERS, sd(x)),
        "note": "one-sided t 1.645 at the whole-life sd; observed sessions = %d" % w["sessions"],
    }
    c, d = res["confirm"], res["develop"]
    passed = (c["mean_day"] is not None and c["mean_day"] > 0
              and c["p_boot_mean_gt0"] is not None and c["p_boot_mean_gt0"] >= P_REQ
              and d["mean_day"] is not None and d["mean_day"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
