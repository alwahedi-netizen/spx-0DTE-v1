"""O-2026-11-28-FLYREVIEW — Options team, league round 3 (2026-11-28), lab.
FLY (13:00 ATM iron butterfly, 40 wide, whole-fly TP/stop at 25%):
keep or retire after 38 usable sessions?

CONTEXT: FLY has run on paper since 2026-09-17 and is the longest-running
lane the league has never judged (RETIRED.md's LATE lesson made the fly
family "the working way to own the last-hour window"). Round 2 did not test
FLYPIN for lack of positive-GEX sessions and noted FLY was negative at mid
over its first 35 sessions (-$1,948 pnl_theo) — so the SIGN of the full
record is NOT blind to this desk; the confirm half's size is. That is why
this study is framed as a pre-registered keep/retire decision with the
lab's own retirement precedent, not as a discovery. Live FLY rows exist
in live_trades.csv (round 2 counted 10 real-money rows); not studied here.

HYPOTHESIS (the lane's own premise, direction fixed): FLY has a positive
edge after simulated fills: mean FLY session P&L (pnl_actual) > 0.

MEASURE: session = a date with a closed FLY fly (two rows, PUT + CALL);
session P&L = sum of pnl_actual. Day-resampled bootstrap. Reported beside
it (NOT judged): pnl_theo (mid — the SIM charges $20 per fly round trip,
$0.05 per row each way, vs a median fly credit of ~$16.76 = $1,676, so the
fill model barely moves FLY); P without the best
session; worst 3; the fly FAMILY (FLY + its reload FLYR, same day) since
FLYR exists only after a FLY take-profit; and a FLYPIN descriptive split
by the 09:00 day.csv gex_sign (positive / negative / unknown each listed) —
labelled descriptive, NOT a test (too few positive-GEX sessions; FLYPIN
stays queued until >= 10 of them after 2026-10-12).

DATA-TIMING: nothing is predicted; each fly's realised outcome is its own
same-day exit or 16:00 settlement; gex_sign (descriptive only) is the 09:00
pre-market value, known before the 13:00 entry. Rows dated <= CUTOFF.
EXCLUDED (league brief): 2026-11-27, an early-close day (13:00 ET) on which
FLY entered at 13:00:06 on frozen quotes — every row with signal_ts at/after
the early close is dropped (also applied to FLYR and MEIC lanes).

SPLIT (pre-declared): develop = 2026-09-17 .. 2026-10-16 (20 sessions);
confirm = 2026-10-19 .. CUTOFF (18 usable sessions).

PASS CRITERION: develop mean > 0 AND confirm mean > 0 AND confirm
P(mean > 0) >= P_REQ. Family "O-FLY", trials 1 -> P_REQ = 0.90.
DECISION (pre-registered, the owner decides): PASS -> "KEEP"; all-session
P(mean > 0) <= 0.15 AND confirm mean < 0 -> "RETIRE RECOMMENDED (FLY and
its derivative FLYR)" (precedent: BAND retired at 88%, LATE at 87%
confidence of a negative edge); otherwise "COLLECT: re-judge at 60
sessions".
"""
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-27"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261128, 10000

ID = "O-2026-11-28-FLYREVIEW"
FAMILY, FAMILY_TRIALS = "O-FLY", 1
P_REQ = 1 - 0.10 / FAMILY_TRIALS
RETIRE_P = 0.15
DEV_START, DEV_END, CONF_START = "2026-09-17", "2026-10-16", "2026-10-19"
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
    """Half-day rule: drop rows entered at/after the early close."""
    d = s["date"]
    return not (d in EARLY_CLOSE and s["signal_ts"][11:16] >= EARLY_CLOSE[d])


def sides(strategy, field):
    return [s for s in closed_sides(strategy, field) if keep(s)]


def stats(days, lo, hi):
    sel = sorted((d, v) for d, v in days.items() if lo <= d <= hi)
    x = [v for _, v in sel]
    if not x:
        return {"sessions": 0}
    best = max(x)
    xb = list(x)
    xb.remove(best)
    return {
        "sessions": len(x), "sum": r2(sum(x)), "mean": r2(mean(x)),
        "p_boot_mean_gt0": boot_pos(x), "ci95_mean": boot_ci(x),
        "win_sessions": sum(v > 0 for v in x),
        "best": r2(best), "p_without_best": boot_pos(xb),
        "worst3": [[d, r2(v)] for d, v in sorted(sel, key=lambda t: t[1])[:3]],
    }


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    fa = sides("FLY", "pnl_actual")
    da = day_pnl(fa)
    dt = day_pnl(sides("FLY", "pnl_theo"))
    res["fly_rows"] = len(fa)
    res["excluded_rows"] = sum(1 for s in closed_sides("FLY") if not keep(s))
    res["develop"] = stats(da, DEV_START, DEV_END)
    res["confirm"] = stats(da, CONF_START, CUTOFF)
    res["all"] = stats(da, DEV_START, CUTOFF)
    res["confirm_pnl_theo"] = stats(dt, CONF_START, CUTOFF)
    res["all_pnl_theo"] = stats(dt, DEV_START, CUTOFF)

    # descriptive: fly family (FLY + FLYR same day)
    fam = defaultdict(float, da)
    for d, v in day_pnl(sides("FLYR", "pnl_actual")).items():
        fam[d] += v
    res["descriptive_family_fly_plus_flyr"] = {
        "all": stats(dict(fam), DEV_START, CUTOFF),
        "confirm": stats(dict(fam), CONF_START, CUTOFF)}

    # descriptive only: FLYPIN split by 09:00 gex_sign
    tags = day_tags()
    split = defaultdict(list)
    for d, v in da.items():
        split[(tags.get(d) or {}).get("gex_sign") or "missing"].append(v)
    res["descriptive_flypin_by_gex"] = {
        k: {"n": len(v), "mean": r2(mean(v))} for k, v in sorted(split.items())}
    res["descriptive_flypin_positive_after_1012"] = sum(
        1 for d in da if d >= "2026-10-12" and (tags.get(d) or {}).get("gex_sign") == "positive")

    d, c, a = res["develop"], res["confirm"], res["all"]
    passed = (d.get("mean") is not None and d["mean"] > 0
              and c.get("mean") is not None and c["mean"] > 0
              and c.get("p_boot_mean_gt0") is not None and c["p_boot_mean_gt0"] >= P_REQ)
    res["verdict"] = "PASS" if passed else "FAIL"
    if passed:
        res["decision"] = "KEEP"
    elif (a.get("p_boot_mean_gt0") is not None and a["p_boot_mean_gt0"] <= RETIRE_P
          and c.get("mean") is not None and c["mean"] < 0):
        res["decision"] = "RETIRE RECOMMENDED: FLY and its derivative FLYR (owner's call)"
    else:
        res["decision"] = "COLLECT: re-judge at 60 sessions"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
