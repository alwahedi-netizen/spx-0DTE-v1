"""O-2026-11-21-LOSSANATOMY — Options team, league round 2 (2026-11-21), lab.
Where do MEIC's stop losses come from: one-way trend days or whipsaw days?

CONTEXT: the MEIC 2.0 lanes bet on different failure modes. A looser stop
(MIIS) helps if losses come from WHIPSAW (both sides stopped on an
intraday round trip — BAND's death, RETIRED.md); a same-side lockout
(MIIL) or a directional filter helps if they come from ONE-WAY trend
days (theme 27). Stop marks are not journaled (STOPMULT untestable), but
which sides stopped is. This measurement decides which lane family more
paper days should be spent on before any re-arm talk.

HYPOTHESIS (written before any run): most of MEIC's stop-loss dollars
come from one-way sessions — sessions on which only ONE side (only PUT or
only CALL) was ever stopped.

MEASURE: for each MEIC session, stopped-side loss = sum of pnl_actual of
its STOPPED sides. A session is one-way if all its stopped sides are on
the same side, whipsaw if both PUT and CALL sides were stopped. share =
one-way stop losses / all stop losses. Day-bootstrap 90% interval of the
share (resampling sessions). Reported beside it: session counts, net day
P&L by type, and condors (same slot) with both sides stopped.

DATA-TIMING: nothing is predicted; same-day realised exits only.
Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09; confirm =
2026-10-12 .. CUTOFF.

PASS CRITERION (measurement): share >= 0.60 in BOTH develop and confirm.
Pre-declared reading: PASS -> one-way days dominate (direction-aware
fixes such as MIIL deserve the paper days); share <= 0.40 in both ->
whipsaw dominates (stop design, MIIS); otherwise mixed — no single fix.
Family "O-LOSSANATOMY", trials 1.
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

ID = "O-2026-11-21-LOSSANATOMY"
FAMILY, FAMILY_TRIALS = "O-LOSSANATOMY", 1
DEV_END, CONF_START = "2026-10-09", "2026-10-12"
SHARE_MIN, SHARE_MAX_WHIP = 0.60, 0.40


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


def sessions(lo, hi):
    g = defaultdict(lambda: {"stop_loss": 0.0, "stop_sides": set(), "net": 0.0,
                             "slots": defaultdict(set)})
    for s in closed_sides("MEIC", "pnl_actual"):
        if not (lo <= s["date"] <= hi):
            continue
        x = g[s["date"]]
        x["net"] += s["pnl"]
        if s["exit_reason"] == "STOPPED":
            x["stop_loss"] += s["pnl"]
            x["stop_sides"].add(s["side"])
            x["slots"][s["slot"]].add(s["side"])
    out = []
    for d in sorted(g):
        x = g[d]
        kind = "none" if not x["stop_sides"] else ("whipsaw" if len(x["stop_sides"]) > 1 else "oneway")
        out.append({"date": d, "kind": kind, "stop_loss": x["stop_loss"], "net": x["net"],
                    "double_condors": sum(1 for v in x["slots"].values() if len(v) > 1)})
    return out


def share(rows):
    tot = sum(r["stop_loss"] for r in rows)
    one = sum(r["stop_loss"] for r in rows if r["kind"] == "oneway")
    return one / tot if tot < 0 else None


def boot_share(rows, lo=0.05, hi=0.95, seed=SEED, n=NBOOT):
    if len(rows) < 2:
        return None
    rng = random.Random(seed)
    v = []
    for _ in range(n):
        s = share([rng.choice(rows) for _ in rows])
        if s is not None:
            v.append(s)
    v.sort()
    if not v:
        return None
    return [round(v[int(lo * (len(v) - 1))], 3), round(v[int(hi * (len(v) - 1))], 3)]


def window(lo, hi):
    rows = sessions(lo, hi)
    by = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        by[r["kind"]][0] += 1
        by[r["kind"]][1] += r["stop_loss"]
        by[r["kind"]][2] += r["net"]
    sh = share(rows)
    return {"sessions": len(rows), "oneway_share": None if sh is None else round(sh, 3),
            "ci90_share": boot_share(rows),
            "by_kind": {k: [v[0], r2(v[1]), r2(v[2])] for k, v in sorted(by.items())},
            "double_stopped_condors": sum(r["double_condors"] for r in rows)}


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS, "cutoff": CUTOFF,
           "by_kind_format": "[sessions, stop-loss sum, net day P&L sum]"}
    res["develop"], res["confirm"] = window("0000", DEV_END), window(CONF_START, CUTOFF)
    res["whole_life"] = window("0000", CUTOFF)
    sd_, sc = res["develop"]["oneway_share"], res["confirm"]["oneway_share"]
    passed = sd_ is not None and sc is not None and sd_ >= SHARE_MIN and sc >= SHARE_MIN
    whip = sd_ is not None and sc is not None and sd_ <= SHARE_MAX_WHIP and sc <= SHARE_MAX_WHIP
    res["reading"] = "oneway dominates" if passed else ("whipsaw dominates" if whip else "mixed")
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
