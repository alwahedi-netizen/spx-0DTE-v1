"""O-2026-11-14-VIXCHG — Options team, league round 1 (2026-11-14), lab.
A rising-VIX day filter for MEIC.

CONTEXT: a VIX that has risen over the last week marks stress that is
building (volatility clusters and trends persist for days — the GARCH /
"leverage effect" canon: Black 1976; Bollerslev 1986). MEIC's losses cluster
on trend days (KNOWLEDGE theme 27). A 5-day VIX rise is known before the
open and is a different variable from the VIX level (O-2026-11-14-VIXLEVEL).

HYPOTHESIS (written before any run; direction PRE-DECLARED): MEIC's mean
day P&L is lower on days when the VIX has risen over the last 5 sessions
(vix_chg_5d > 0) than on days when it has fallen or is flat, and the
rising days lose money on average.

RULE: x = day.csv vix_chg_5d (09:00 VIX quote minus the close 5 sessions
earlier). Good = x <= 0 (trade), bad = x > 0 (skip). Neighbours: thresholds
-1.0, -0.5, +0.5, +1.0 VIX points, same direction.

DATA-TIMING: vix_chg_5d is written at the 09:00 pre-market step from the
09:00 quote and earlier daily closes, before the first MEIC entry (12:00);
entries earn to their own journaled exits the same day. Days with no value
are excluded. Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09; confirm =
2026-10-12 .. CUTOFF.

PASS CRITERION: confirm mean day P&L(good) - (bad) > 0 with day-bootstrap
P >= P_REQ, AND confirm mean day P&L(bad) < 0, AND the develop difference
is also > 0 (pre-declared direction), AND >= 3 of 4 neighbour thresholds
give a positive confirm difference.
Family "O-VOLREGIME" (VIXLEVEL, VIXCHG, VRPGATE), trials 3 -> P_REQ = 0.967.
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

ID = "O-2026-11-14-VIXCHG"
FAMILY, FAMILY_TRIALS = "O-VOLREGIME", 3
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END = "2026-10-09"
THR = 0.0
NEIGH_T = (-1.0, -0.5, 0.5, 1.0)


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


def tag_x(tags):
    return {d: fnum(r.get("vix_chg_5d")) for d, r in tags.items()
            if fnum(r.get("vix_chg_5d")) is not None}


def split(dp, xs, lo, hi, thr, high_good):
    good, bad = [], []
    for d, v in sorted(dp.items()):
        if lo <= d <= hi and d in xs:
            (good if (xs[d] > thr) == high_good else bad).append(v)
    return good, bad


def stats(good, bad):
    mg, mb = mean(good), mean(bad)
    return {"good_days": len(good), "bad_days": len(bad),
            "good_mean_day": r2(mg), "bad_mean_day": r2(mb),
            "diff": r2(None if mg is None or mb is None else mg - mb),
            "filtered_sum": r2(sum(good)), "unfiltered_sum": r2(sum(good) + sum(bad))}


def main():
    dp = day_pnl(closed_sides("MEIC", "pnl_actual"))
    xs = tag_x(day_tags())
    high_good = False                      # pre-declared: rising VIX is bad
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF, "threshold": THR,
           "direction": "trade when vix_chg_5d <= threshold (pre-declared)"}
    res["develop"] = stats(*split(dp, xs, "0000", DEV_END, THR, high_good))
    good, bad = split(dp, xs, "2026-10-12", CUTOFF, THR, high_good)
    res["confirm"] = stats(good, bad)
    p = boot_diff(good, bad)
    res["confirm"]["p_boot_diff_gt0"] = p
    neigh = {}
    for t in NEIGH_T:
        g, b = split(dp, xs, "2026-10-12", CUTOFF, t, high_good)
        neigh[f"thr={t:+.1f}"] = stats(g, b)["diff"]
    res["neighbours_confirm_diff"] = neigh
    n_ok = sum(1 for v in neigh.values() if v is not None and v > 0)
    res["neighbours_positive"] = f"{n_ok}/{len(NEIGH_T)}"
    mb = res["confirm"]["bad_mean_day"]
    dd = res["develop"]["diff"]
    passed = (p is not None and p >= P_REQ and mb is not None and mb < 0
              and dd is not None and dd > 0 and n_ok >= 3)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
