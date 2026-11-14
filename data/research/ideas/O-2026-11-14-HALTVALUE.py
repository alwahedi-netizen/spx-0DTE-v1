"""O-2026-11-14-HALTVALUE — Options team, league round 1 (2026-11-14), lab.
Has the live daily stop's FLATTEN saved money?

CONTEXT: when live MEIC's realized day P&L reaches -$1,000 (or all live
strategies reach -$2,000), live_meic.py halts the strategy and closes every
open side at market (exit_reason HALT). The paper twin of each such side
keeps running to its own exit (stop / take-profit / expiry). The gap
between the two is the measured value of flattening.

HYPOTHESIS (written before any run): on a day bad enough to trip the stop,
open sides are more likely to be stopped later than to recover, so the
HALT closes earn more than their paper twins held to the paper exit.

MEASURE: for every real-money (non "dry-") live MEIC side with exit_reason
HALT: saving = pnl_live - pnl_actual(paper twin) - base_drift, where
base_drift = the median (pnl_live - pnl_actual) of the same window's
non-HALT filled live MEIC sides (removes fees and normal fill slippage, so
only the decision to flatten is measured). Summed per halt day.

DATA-TIMING: nothing is predicted; both P&Ls are realized outcomes of the
same side on the same day. The halt fires on realized P&L only (exits
already printed); the paper twin's exit is its own journaled exit.
Sessions <= CUTOFF.

SPLIT (pre-declared): develop = live sessions <= 2026-10-16; confirm =
2026-10-19 .. CUTOFF.

PASS CRITERION: pooled mean saving per halt day > 0 with day-bootstrap
P >= P_REQ, AND the saving sum is > 0 in BOTH windows. Halt days are few
(about a dozen): a FAIL from low power is reported as such ("n too small"),
not as evidence the flatten is harmful.
Family "O-DAILYSTOP" (this + DAILYSTOP), trials 2 -> P_REQ = 0.95.
"""
import csv
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-13"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261114, 10000

ID = "O-2026-11-14-HALTVALUE"
FAMILY, FAMILY_TRIALS = "O-DAILYSTOP", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
LIVE_DEV_END = "2026-10-16"


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


def analyse(live, paper, lo, hi):
    rows = [r for r in live if lo <= r["date"] <= hi]
    filled = [r for r in rows if fnum(r["pnl_live"]) is not None
              and r["position_id"] in paper]
    normal = [fnum(r["pnl_live"]) - paper[r["position_id"]] for r in filled
              if r["exit_reason"] != "HALT"]
    base = statistics.median(normal) if normal else 0.0
    halts = [r for r in filled if r["exit_reason"] == "HALT"]
    per_day = defaultdict(float)
    raw = 0.0
    for r in halts:
        gap = fnum(r["pnl_live"]) - paper[r["position_id"]]
        raw += gap
        per_day[r["date"]] += gap - base
    cash_settled = sum(1 for r in halts if r["status"] == "EXPIRED")
    return {
        "halt_sides": len(halts), "halt_days": len(per_day),
        "halt_sides_flatten_failed_cash_settled": cash_settled,
        "base_drift_median_per_side": r2(base),
        "raw_gap_sum": r2(raw),
        "saving_sum": r2(sum(per_day.values())),
        "saving_by_day": {d: r2(v) for d, v in sorted(per_day.items())},
    }, list(per_day.values())


def main():
    paper = {r["position_id"]: float(r["pnl_actual"])
             for r in read("positions.csv") if r["exit_ts"] and fnum(r["pnl_actual"]) is not None}
    live = live_rows("MEIC")
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    dev, dv = analyse(live, paper, "0000", LIVE_DEV_END)
    conf, cv = analyse(live, paper, "2026-10-19", CUTOFF)
    pooled = dv + cv
    p = boot_pos(pooled)
    res["develop"], res["confirm"] = dev, conf
    res["pooled"] = {"halt_days": len(pooled), "mean_saving_per_day": r2(mean(pooled)),
                     "p_boot_mean_gt0": p}
    passed = (p is not None and p >= P_REQ and dev["saving_sum"] > 0
              and conf["saving_sum"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    if not passed and len(pooled) < 15:
        res["note"] = "n too small: fewer than 15 halt days"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
