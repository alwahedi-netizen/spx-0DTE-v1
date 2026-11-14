"""O-2026-11-14-STOPVSHOLD — Options team, league round 1 (2026-11-14), lab.
What has MEIC's per-side stop cost or saved, measured at settlement?

CONTEXT: each MEIC side is stopped when its spread value reaches the
condor's total credit (stop/side = total credit, ~2x the side's own
credit). BAND died because a per-side stop turned contained days into
double-stop losses (RETIRED.md); MIIS (paper since 2026-11-12) tests a
looser 1.5x stop. Without intraday marks a looser stop cannot be replayed,
but the far end of the dial — no stop, hold to the 16:00 settlement — can
be computed exactly for every stopped side. That bounds what loosening can
buy, and the tail it adds (no-stop sides can lose the full 30-point width).

HYPOTHESIS (written before any run): most stopped MEIC sides recover
before the close (0DTE whipsaw), so holding the stopped sides to settlement
would have earned MORE in total than the stops did.
This is a measurement for the stop-design lanes (MIIS), NOT a proposal to
trade without a stop: RETIRED.md (PBW) records that an unprotected 0DTE
short wing is a crash bet. The worst day under "hold" is reported beside
the totals for exactly that reason.

MEASURE: for each STOPPED MEIC side: hold_pnl = (credit_actual -
settle_value) x 100, settle_value = the spread's intrinsic value at the SPX
close (put: clip(short - S, 0, short - long); call: clip(S - short, 0,
long - short)); delta = hold_pnl - pnl_actual. Per day sums. S = Yahoo
^GSPC close of the trade date (SPXW 0DTE are PM-settled on the close);
fallback: the next day.csv row's prior_close.

DATA-TIMING: nothing is predicted; the counterfactual reads only the trade
date's own 16:00 close, which is the option's settlement value.
Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09; confirm =
2026-10-12 .. CUTOFF.

PASS CRITERION: confirm sum of daily delta > 0 with day-bootstrap
P(mean daily delta > 0) >= P_REQ, AND develop sum > 0.
Family "O-SIDESTOP", trials 1 -> P_REQ = 0.90.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-13"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261114, 10000

ID = "O-2026-11-14-STOPVSHOLD"
FAMILY, FAMILY_TRIALS = "O-SIDESTOP", 1
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END = "2026-10-09"


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


def settles():
    """date -> SPX close (Yahoo ^GSPC; fallback next day.csv prior_close)."""
    out = {}
    try:
        sys.path.insert(0, str(ROOT))
        import research_bt as rb
        dates, px = rb.prices(["^GSPC"], start="2026-08-01")
        out = {d: v for d, v in zip(dates, px["^GSPC"]) if v}
    except Exception as e:                      # noqa: BLE001 — report, fall back
        print(f"yahoo unavailable ({e}); using day.csv prior_close", file=sys.stderr)
    rows = sorted((r["date"], fnum(r.get("prior_close"))) for r in read("day.csv"))
    for i, (d, _) in enumerate(rows):
        if d in out:
            continue
        nxt = next((pc for d2, pc in rows[i + 1:] if pc), None)
        if nxt:
            out[d] = nxt
    return out


def intrinsic(side, short, long_, s):
    if side == "PUT":
        return min(max(short - s, 0.0), short - long_)
    return min(max(s - short, 0.0), long_ - short)


def window(sides, close, lo, hi):
    day_d, day_act, day_hold = defaultdict(float), defaultdict(float), defaultdict(float)
    n_stop = n_otm = n_missing = 0
    full_loss = 0
    for s in sides:
        if not (lo <= s["date"] <= hi):
            continue
        day_act[s["date"]] += s["pnl"]
        if s["exit_reason"] != "STOPPED":
            day_hold[s["date"]] += s["pnl"]
            continue
        S = close.get(s["date"])
        if S is None:
            n_missing += 1
            day_hold[s["date"]] += s["pnl"]
            continue
        k, l = float(s["short_strike"]), float(s["long_strike"])
        v = intrinsic(s["side"], k, l, S)
        hold = (float(s["credit_actual"]) - v) * 100
        n_stop += 1
        n_otm += v == 0.0
        full_loss += v >= abs(k - l) - 1e-9
        day_d[s["date"]] += hold - s["pnl"]
        day_hold[s["date"]] += hold
    days = sorted(day_act)
    delta = [day_d.get(d, 0.0) for d in days]
    return {
        "days": len(days), "stopped_sides": n_stop,
        "stopped_expired_otm": n_otm,
        "stopped_settled_full_width": full_loss,
        "stopped_without_settle_price": n_missing,
        "actual_sum": r2(sum(day_act.values())),
        "hold_sum": r2(sum(day_hold.values())),
        "delta_sum": r2(sum(delta)),
        "worst_day_actual": r2(min(day_act.values(), default=None)),
        "worst_day_hold": r2(min(day_hold.values(), default=None)),
        "p_boot_delta_gt0": boot_pos(delta),
    }


def main():
    sides = closed_sides("MEIC", "pnl_actual")
    close = settles()
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    dev = window(sides, close, "0000", DEV_END)
    conf = window(sides, close, "2026-10-12", CUTOFF)
    res["develop"], res["confirm"] = dev, conf
    p = conf["p_boot_delta_gt0"]
    passed = (conf["delta_sum"] > 0 and p is not None and p >= P_REQ
              and dev["delta_sum"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
