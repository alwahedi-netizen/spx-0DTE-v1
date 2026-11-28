"""O-2026-11-28-MPMREVIEW — Options team, league round 3 (2026-11-28), lab.
MPM (morning put-spread ladder) at its ~100-trade checkpoint: keep or retire?

CONTEXT: owner 2026-11-08 ("retire MEP · keep MPM, OCB"; RETIRED.md): MPM
stays on paper "until it has ~100 trades". It has 89 closed put spreads over
30 sessions (2026-10-15 .. 11-27), ~3 a day, so it reaches 100 in about four
sessions; this study judges it now, on everything through CUTOFF, and the
pre-registered rules below do not change if it is re-run at 100. The league
has never studied MPM. Its paper P&L appears in the nightly digest
(shadow_rules.py), so the record is not blind to the owner — it is blind to
this desk (no MPM outcome was computed while writing this).
Engine hypothesis (paper_engine.py "mpm"): early-session short premium
(tastylive 0DTE studies) in the lab's put-spread structure: 10:00/10:30/
11:00, $1.50 credit, 30 wide, stop 2x own credit, TP short <= 0.05. The MEP
lesson (RETIRED.md): a one-sided put ladder must survive a down tape — MPM's
record contains the late-October sell-offs and the -9% week of 11-16..20.

HYPOTHESIS (written before any run, direction fixed): MPM has a positive
edge after simulated fills: mean MPM session P&L (pnl_actual) > 0.

MEASURE: session = a date with >= 1 closed MPM side; session P&L = sum of
pnl_actual. Day-resampled bootstrap (boot_pos / boot_ci). Reported beside
it (NOT judged): pnl_theo (mid); P without the best session; worst 3
sessions; MPM on SPX down sessions vs up sessions (session return = band.csv
16:05 spx_close / day.csv prior_close - 1, both the lab's own values) — the
MEP down-tape question; and the paired same-day comparison the engine
comment states (MPM per-side P&L minus MEIC PUT-side per-side P&L, sessions
where both traded) — "the morning pays at least as well as the afternoon".

DATA-TIMING: nothing is predicted; each side's realised outcome is its own
same-day exit (TP/STOP) or 16:00 settlement. Rows dated <= CUTOFF. On an
early-close date (2026-11-27, 13:00 ET) any row with signal_ts at/after
13:00 is dropped (MPM's 10:00-11:00 entries are kept).

SPLIT (pre-declared): develop = 2026-10-15 .. 2026-11-06 (the record the
owner saw when retiring MEP and keeping MPM; 16 sessions); confirm =
2026-11-09 .. CUTOFF (14 sessions).

PASS CRITERION: develop mean > 0 AND confirm mean > 0 AND confirm
P(mean > 0) >= P_REQ. Family "O-MPM", trials 1 -> P_REQ = 0.90.
DECISION (pre-registered, the owner decides): PASS -> "KEEP: edge
confirmed, eligible for a re-arm discussion only after the MEIC20GATE
read"; all-session P(mean > 0) <= 0.15 AND confirm mean < 0 -> "RETIRE
RECOMMENDED" (precedent: BAND retired at 88%, LATE at 87% confidence of a
negative edge); otherwise "COLLECT: re-judge at 45 sessions".
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

ID = "O-2026-11-28-MPMREVIEW"
FAMILY, FAMILY_TRIALS = "O-MPM", 1
P_REQ = 1 - 0.10 / FAMILY_TRIALS
RETIRE_P = 0.15
DEV_START, DEV_END, CONF_START = "2026-10-15", "2026-11-06", "2026-11-09"
EARLY_CLOSE = {"2026-11-27": "13:00", "2026-12-24": "13:00"}
LANE = "MPM"

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


def session_returns():
    band = {r["date"]: fnum(r.get("spx_close")) for r in read("band.csv")}
    out = {}
    for d, r in day_tags().items():
        pc, c = fnum(r.get("prior_close")), band.get(d)
        if pc and c:
            out[d] = c / pc - 1
    return out


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    sa = sides(LANE, "pnl_actual")
    st = sides(LANE, "pnl_theo")
    da, dt = day_pnl(sa), day_pnl(st)
    res["sides"] = len(sa)
    res["develop"] = stats(da, DEV_START, DEV_END)
    res["confirm"] = stats(da, CONF_START, CUTOFF)
    res["all"] = stats(da, DEV_START, CUTOFF)
    res["confirm_pnl_theo"] = stats(dt, CONF_START, CUTOFF)
    res["all_pnl_theo"] = stats(dt, DEV_START, CUTOFF)

    # descriptive: down-tape sessions (MEP lesson)
    ret = session_returns()
    down = [v for d, v in da.items() if d in ret and ret[d] < 0]
    up = [v for d, v in da.items() if d in ret and ret[d] >= 0]
    res["descriptive_down_vs_up_sessions"] = {
        "down_n": len(down), "down_mean": r2(mean(down)),
        "up_n": len(up), "up_mean": r2(mean(up)), "unmatched": len(da) - len(down) - len(up)}

    # descriptive: MPM per side vs MEIC PUT sides per side, same sessions
    meic_put = [s for s in sides("MEIC", "pnl_actual") if s["side"] == "PUT"]
    mp_n, mp_sum = defaultdict(int), defaultdict(float)
    for s in meic_put:
        mp_n[s["date"]] += 1
        mp_sum[s["date"]] += s["pnl"]
    mm_n = defaultdict(int)
    for s in sa:
        mm_n[s["date"]] += 1
    common = sorted(d for d in da if mp_n.get(d))
    diff = [da[d] / mm_n[d] - mp_sum[d] / mp_n[d] for d in common]
    res["descriptive_mpm_minus_meic_put_per_side"] = {
        "sessions": len(common), "mean_diff": r2(mean(diff)), "p_boot_gt0": boot_pos(diff)}

    d, c, a = res["develop"], res["confirm"], res["all"]
    passed = (d.get("mean") is not None and d["mean"] > 0
              and c.get("mean") is not None and c["mean"] > 0
              and c.get("p_boot_mean_gt0") is not None and c["p_boot_mean_gt0"] >= P_REQ)
    res["verdict"] = "PASS" if passed else "FAIL"
    if passed:
        res["decision"] = "KEEP: edge confirmed (re-arm talk only after the MEIC20GATE read)"
    elif (a.get("p_boot_mean_gt0") is not None and a["p_boot_mean_gt0"] <= RETIRE_P
          and c.get("mean") is not None and c["mean"] < 0):
        res["decision"] = "RETIRE RECOMMENDED (owner's call)"
    else:
        res["decision"] = "COLLECT: re-judge at 45 sessions"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
