"""O-2026-11-14-MISSEDFILLS — Options team, league round 1 (2026-11-14), lab.
Are the live MEIC sides that never filled adversely selected?

CONTEXT: 41 live MEIC sides are SKIPPED (no fill). The strike-overlap
rejections ("not an opening transaction") were already studied on
2026-11-13 (16 rejections, paper twins +$581) and get a fix; they are a
mechanical clash with our own ladder, not market selection, so they are
EXCLUDED here. What remains is mostly "unfilled after reprice" plus other
broker rejections.

HYPOTHESIS (written before any run): a credit limit fails to fill when the
spread's price falls away from the limit, i.e. when SPX moves AWAY from the
short strike right after the signal — the side that then usually wins. So
paper twins of missed (non-overlap) sides earn MORE per side than paper
twins of sides that did fill, and live systematically under-earns paper
beyond the per-fill drift (O-2026-11-14-LIVEDRIFT).

MEASURE: per-side paper pnl_actual of the twins; groups = missed
(status SKIPPED, note not an overlap rejection) vs filled (pnl_live set).
Cluster unit = day (each group's sides pooled per day, days resampled).

DATA-TIMING: nothing is predicted; fill/no-fill is the live outcome at the
signal, paper P&L is the same side's realized result that day.
Sessions <= CUTOFF.

SPLIT (pre-declared): develop = live sessions <= 2026-10-16; confirm =
2026-10-19 .. CUTOFF.

PASS CRITERION: pooled mean per-side paper P&L (missed) - (filled) > 0 with
day-cluster bootstrap P >= P_REQ, AND the difference is > 0 in BOTH windows.
Missed sides are few (~25): a FAIL from low power is labelled "n too small".
Family "O-LIVEDRIFT" (this + LIVEDRIFT), trials 2 -> P_REQ = 0.95.
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

ID = "O-2026-11-14-MISSEDFILLS"
FAMILY, FAMILY_TRIALS = "O-LIVEDRIFT", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
LIVE_DEV_END = "2026-10-16"
OVERLAP_TXT = "not an opening transaction"


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


def cluster_boot_diff(a_days, b_days, seed=SEED, n=NBOOT):
    """a_days/b_days: list of per-day lists of side P&Ls. P(mean side
    P&L of a - of b > 0), resampling days within each group."""
    if len(a_days) < 2 or len(b_days) < 2:
        return None
    rng, hit = random.Random(seed), 0
    for _ in range(n):
        ra = [v for _ in a_days for v in rng.choice(a_days)]
        rb = [v for _ in b_days for v in rng.choice(b_days)]
        if mean(ra) - mean(rb) > 0:
            hit += 1
    return hit / n


def groups(live, paper, lo, hi):
    miss, fill = defaultdict(list), defaultdict(list)
    reasons = defaultdict(int)
    overlap = 0
    for r in live:
        if not (lo <= r["date"] <= hi) or r["position_id"] not in paper:
            continue
        p = paper[r["position_id"]]
        if r["status"] == "SKIPPED":
            if OVERLAP_TXT in (r["note"] or ""):
                overlap += 1
                continue
            miss[r["date"]].append(p)
            reasons[(r["note"] or "?").split("|")[0].strip()[:40]] += 1
        elif fnum(r["pnl_live"]) is not None:
            fill[r["date"]].append(p)
    return miss, fill, dict(reasons), overlap


def summary(miss, fill, reasons, overlap):
    m = [v for vs in miss.values() for v in vs]
    f = [v for vs in fill.values() for v in vs]
    mm, mf = mean(m), mean(f)
    return {"missed_sides": len(m), "missed_days": len(miss), "filled_sides": len(f),
            "overlap_rejections_excluded": overlap, "missed_reasons": reasons,
            "missed_mean_paper_pnl": r2(mm), "filled_mean_paper_pnl": r2(mf),
            "missed_paper_pnl_sum": r2(sum(m)),
            "missed_paper_win_rate": r2(sum(1 for v in m if v > 0) / len(m)) if m else None,
            "diff": r2(None if mm is None or mf is None else mm - mf)}


def main():
    paper = {r["position_id"]: float(r["pnl_actual"]) for r in read("positions.csv")
             if r["exit_ts"] and fnum(r["pnl_actual"]) is not None}
    live = live_rows("MEIC")
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    gd = groups(live, paper, "0000", LIVE_DEV_END)
    gc = groups(live, paper, "2026-10-19", CUTOFF)
    res["develop"], res["confirm"] = summary(*gd), summary(*gc)
    ga = groups(live, paper, "0000", CUTOFF)
    res["pooled"] = summary(*ga)
    p = cluster_boot_diff(list(ga[0].values()), list(ga[1].values()))
    res["pooled"]["p_boot_diff_gt0"] = p
    dd, dc = res["develop"]["diff"], res["confirm"]["diff"]
    passed = (p is not None and p >= P_REQ and dd is not None and dd > 0
              and dc is not None and dc > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    if not passed and res["pooled"]["missed_sides"] < 40:
        res["note"] = "n too small: fewer than 40 missed sides"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
