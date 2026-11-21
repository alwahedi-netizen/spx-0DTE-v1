"""O-2026-11-21-PRIORDAY — Options team, league round 2 (2026-11-21), lab.
Loss clustering: is MEIC worse on the session after a MEIC losing day?

CONTEXT: the owner's question — are bad days predictable from what is
known at 09:30? Round 1 failed VIX level, VIX 5-day change, the VRP gate
and the noon move. None of them used the strategy's OWN recent outcome.
Volatility clusters (Bollerslev 1986, J. Econometrics) and trend days
come in runs, so a MEIC losing day (stops hit = the tape moved) may
predict another. If true, "stand aside the day after a loss" is a rule
known before the open.

HYPOTHESIS (written before any run, direction fixed): mean MEIC day P&L
on sessions that follow a MEIC LOSING session is LOWER than on sessions
that follow a winning (>= 0) session.

MEASURE: MEIC day pnl_actual (sum of closed sides). For each MEIC session
except the first, prior = the previous MEIC session in the journal.
Groups: after-loss (prior < 0) vs after-win (prior >= 0). Statistic:
mean(after-win) - mean(after-loss), group days resampled
(boot_diff). Reported beside it: the same on pnl_theo, and the "skip the
day after a loss" rule's total vs trading every day.

DATA-TIMING: the flag reads only the PREVIOUS session's realised MEIC P&L
(final at its 16:00 settlement), known before today's 09:30 open; today's
sides earn to their own same-day exits. Sessions <= CUTOFF.

SPLIT (pre-declared): develop = MEIC sessions <= 2026-10-09; confirm =
2026-10-12 .. CUTOFF (the first confirm session's prior is the last
develop session — a reading of a past outcome, not a leak).

PASS CRITERION: confirm diff > 0 with P(diff > 0) >= P_REQ AND develop
diff > 0. Family "O-CLUSTER" (this + O-2026-11-21-PRIORRET), trials 2 ->
P_REQ = 0.95.
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

ID = "O-2026-11-21-PRIORDAY"
FAMILY, FAMILY_TRIALS = "O-CLUSTER", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END, CONF_START = "2026-10-09", "2026-10-12"


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


def tagged(field):
    dp = day_pnl(closed_sides("MEIC", field))
    days = sorted(dp)
    return [(d, dp[d], dp[days[i - 1]] < 0) for i, d in enumerate(days) if i > 0]


def window(rows, lo, hi):
    sel = [(d, v, f) for d, v, f in rows if lo <= d <= hi]
    after_loss = [v for _, v, f in sel if f]
    after_win = [v for _, v, f in sel if not f]
    m_w, m_l = mean(after_win), mean(after_loss)
    return {
        "sessions": len(sel), "after_loss_n": len(after_loss), "after_win_n": len(after_win),
        "after_loss_mean": r2(m_l), "after_win_mean": r2(m_w),
        "diff_win_minus_loss": r2(m_w - m_l) if m_w is not None and m_l is not None else None,
        "p_boot_diff_gt0": boot_diff(after_win, after_loss),
        "all_sum": r2(sum(v for _, v, _ in sel)),
        "skip_after_loss_sum": r2(sum(after_win)),
    }


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    act, theo = tagged("pnl_actual"), tagged("pnl_theo")
    res["develop"] = window(act, "0000", DEV_END)
    res["confirm"] = window(act, CONF_START, CUTOFF)
    res["confirm_pnl_theo"] = window(theo, CONF_START, CUTOFF)
    c, d = res["confirm"], res["develop"]
    passed = (c["diff_win_minus_loss"] is not None and c["diff_win_minus_loss"] > 0
              and c["p_boot_diff_gt0"] is not None and c["p_boot_diff_gt0"] >= P_REQ
              and d["diff_win_minus_loss"] is not None and d["diff_win_minus_loss"] > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
