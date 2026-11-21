"""O-2026-11-21-PRIORRET — Options team, league round 2 (2026-11-21), lab.
Daily volatility clustering: is MEIC worse after a big SPX day?

CONTEXT: second of two "yesterday's tape" predictors known before the
09:30 open (with O-2026-11-21-PRIORDAY). Round 1's VIX level/change and
VRP gate used implied vol or a 20-day realised range; this uses the single
most recent realised move, the quantity GARCH says carries most of the
next day's variance (Bollerslev 1986). A big move yesterday should raise
the odds of a trend or whipsaw afternoon that stops MEIC's sides.

HYPOTHESIS (written before any run, direction fixed): mean MEIC day P&L
on sessions whose PREVIOUS trading day had a large SPX close-to-close move
is LOWER than on sessions after a quiet day.

MEASURE: r_prev = SPX close(t-1) / close(t-2) - 1 on the Yahoo ^GSPC
trading calendar (fallback: consecutive day.csv prior_close values).
"Large" = |r_prev| >= the 67th percentile of |r_prev| over DEVELOP MEIC
sessions (top tercile; the threshold uses develop returns only, never
P&L, and is frozen for confirm). Statistic: mean(quiet) - mean(large) of
MEIC day pnl_actual, group days resampled (boot_diff). Reported beside
it: the threshold, the same on pnl_theo, and "skip after a large day"
totals.

DATA-TIMING: r_prev reads closes dated t-1 and t-2, both final before
session t opens; session t's sides earn to their own same-day exits.
Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09; confirm =
2026-10-12 .. CUTOFF.

PASS CRITERION: confirm diff > 0 with P(diff > 0) >= P_REQ AND develop
diff > 0. Family "O-CLUSTER" (this + O-2026-11-21-PRIORDAY), trials 2 ->
P_REQ = 0.95.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-20"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261121, 10000

ID = "O-2026-11-21-PRIORRET"
FAMILY, FAMILY_TRIALS = "O-CLUSTER", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END, CONF_START = "2026-10-09", "2026-10-12"
Q_LARGE = 2 / 3


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


def prev_returns():
    """date -> SPX return of the PREVIOUS trading day (close t-1 / close t-2 - 1)."""
    out, src = {}, "yahoo"
    try:
        sys.path.insert(0, str(ROOT))
        import research_bt as rb
        dates, px = rb.prices(["^GSPC"], start="2026-07-01")
        c = px["^GSPC"]
        for i in range(2, len(dates)):
            if c[i - 1] and c[i - 2]:
                out[dates[i]] = c[i - 1] / c[i - 2] - 1
    except Exception as e:                      # noqa: BLE001 — report, fall back
        print(f"yahoo unavailable ({e}); using day.csv prior_close", file=sys.stderr)
        src = "day.csv"
    rows = sorted((d, fnum(r.get("prior_close"))) for d, r in day_tags().items())
    for i in range(1, len(rows)):
        d, pc = rows[i]
        _, pc0 = rows[i - 1]
        if d not in out and pc and pc0:
            out[d] = pc / pc0 - 1
    return out, src


def window(rows, thr, lo, hi):
    sel = [(d, v, a) for d, v, a in rows if lo <= d <= hi]
    large = [v for _, v, a in sel if a >= thr]
    quiet = [v for _, v, a in sel if a < thr]
    m_q, m_l = mean(quiet), mean(large)
    return {
        "sessions": len(sel), "large_n": len(large), "quiet_n": len(quiet),
        "large_mean": r2(m_l), "quiet_mean": r2(m_q),
        "diff_quiet_minus_large": r2(m_q - m_l) if m_q is not None and m_l is not None else None,
        "p_boot_diff_gt0": boot_diff(quiet, large),
        "all_sum": r2(sum(v for _, v, _ in sel)), "skip_after_large_sum": r2(sum(quiet)),
    }


def main():
    rp, src = prev_returns()
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF, "return_source": src}
    out = {}
    for field in ("pnl_actual", "pnl_theo"):
        dp = day_pnl(closed_sides("MEIC", field))
        out[field] = [(d, v, abs(rp[d])) for d, v in sorted(dp.items()) if d in rp]
    res["sessions_without_return"] = len(day_pnl(closed_sides("MEIC"))) - len(out["pnl_actual"])
    thr = pctl([a for d, _, a in out["pnl_actual"] if d <= DEV_END], Q_LARGE)
    res["threshold_abs_prev_return"] = None if thr is None else round(thr, 5)
    res["develop"] = window(out["pnl_actual"], thr, "0000", DEV_END)
    res["confirm"] = window(out["pnl_actual"], thr, CONF_START, CUTOFF)
    res["confirm_pnl_theo"] = window(out["pnl_theo"], thr, CONF_START, CUTOFF)
    c, d = res["confirm"], res["develop"]
    passed = (c["diff_quiet_minus_large"] is not None and c["diff_quiet_minus_large"] > 0
              and c["p_boot_diff_gt0"] is not None and c["p_boot_diff_gt0"] >= P_REQ
              and d["diff_quiet_minus_large"] is not None and d["diff_quiet_minus_large"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
