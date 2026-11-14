"""O-2026-11-14-GEXOOS — Options team, league round 1 (2026-11-14).
Replication + out-of-sample test of the MNG premise: MEIC earns more on
negative-GEX days than on positive-GEX days.

SOURCE (our own journal, SANDBOX_PLAYBOOK.md §6a): splitting MEIC's paper
P&L by the daily GEX tag gave "+$2,230 negative-GEX vs -$1,821 positive".
MNG (MEIC on negative-GEX days only) was created from that split on
2026-09-29 and promoted to dry-run on 2026-11-07. Every session since
2026-09-30 is data the split never saw: a true out-of-sample window.

HYPOTHESIS (written before any run): MEIC's mean day P&L on negative-GEX
days exceeds its mean day P&L on positive-GEX days in the out-of-sample
window. Theory is ambiguous (long-gamma dealers should PIN positive-GEX
days, which would favour condors); the split is empirical, which is why it
needs this confirmation before MNG gets real money.

DATA-TIMING: gex_sign is read from day.csv, written at the 09:00 ET
pre-market step (platform GEX from the prior session's open interest),
before the first MEIC entry at 12:00. Each MEIC side is entered at its slot
and earns to its own exit the same day (0DTE); no tag read on or after the
entry time. pnl = pnl_actual (after simulated fills). Sessions <= CUTOFF.

SPLIT (pre-declared): replication/develop = MEIC sessions <= 2026-09-29
(the source's window); confirm = 2026-09-30 .. CUTOFF. 'unknown' tags are
excluded from both groups.

REPLICATION GATE (rule 1): on the source window, the negative-GEX sum must
be > 0 and the positive-GEX sum < 0, each within 0.5x-2.0x of the source
(+2,230 / -1,821), on pnl_actual OR pnl_theo (the source did not say which).
If it fails: verdict FAIL "replication failed (harness/data suspect)" and
the confirm window is NOT tested.

PASS CRITERION (confirm window only): mean day P&L(neg) - mean day
P&L(pos) > 0 with day-bootstrap P >= P_REQ, AND mean day P&L(neg) > 0.
Family "O-GEXREGIME", trials 1 -> P_REQ = 1 - 0.10/1 = 0.90.
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

ID = "O-2026-11-14-GEXOOS"
FAMILY, FAMILY_TRIALS = "O-GEXREGIME", 1
P_REQ = 1 - 0.10 / FAMILY_TRIALS
SRC_END = "2026-09-29"
SRC_NEG, SRC_POS = 2230.0, -1821.0


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


def split(days_pnl, tags, lo, hi):
    neg = [v for d, v in sorted(days_pnl.items())
           if lo <= d <= hi and (tags.get(d) or {}).get("gex_sign") == "negative"]
    pos = [v for d, v in sorted(days_pnl.items())
           if lo <= d <= hi and (tags.get(d) or {}).get("gex_sign") == "positive"]
    return neg, pos


def main():
    tags = day_tags()
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}

    # 1. replication on the source window
    rep = {}
    ok_any = False
    for field in ("pnl_actual", "pnl_theo"):
        dp = day_pnl(closed_sides("MEIC", field))
        neg, pos = split(dp, tags, "0000", SRC_END)
        sn, sp = sum(neg), sum(pos)
        ok = (sn > 0 and sp < 0 and 0.5 <= sn / SRC_NEG <= 2.0
              and 0.5 <= sp / SRC_POS <= 2.0)
        ok_any = ok_any or ok
        rep[field] = {"neg_days": len(neg), "neg_sum": r2(sn),
                      "pos_days": len(pos), "pos_sum": r2(sp), "matches": ok}
    res["replication"] = dict(rep, source={"neg": SRC_NEG, "pos": SRC_POS},
                              window=f"<= {SRC_END}", passed=ok_any)
    if not ok_any:
        res["verdict"] = "FAIL"
        res["reason"] = "replication failed (harness/data suspect); confirm not tested"
        print(json.dumps(res, indent=1))
        return

    # 2. out-of-sample confirm window
    dp = day_pnl(closed_sides("MEIC", "pnl_actual"))
    neg, pos = split(dp, tags, "2026-09-30", CUTOFF)
    mn, mp = mean(neg), mean(pos)
    p = boot_diff(neg, pos)
    mng = day_pnl(closed_sides("MNG", "pnl_actual"))
    mng_c = {d: v for d, v in mng.items() if "2026-09-30" <= d <= CUTOFF}
    unknown = [d for d in dp if "2026-09-30" <= d <= CUTOFF
               and (tags.get(d) or {}).get("gex_sign") not in ("negative", "positive")]
    res["confirm"] = {
        "window": f"2026-09-30..{CUTOFF}", "neg_days": len(neg), "pos_days": len(pos),
        "unknown_days_excluded": len(unknown),
        "neg_mean_day": r2(mn), "pos_mean_day": r2(mp),
        "neg_sum": r2(sum(neg)), "pos_sum": r2(sum(pos)),
        "diff_mean_day": r2(None if mn is None or mp is None else mn - mp),
        "p_boot_diff_gt0": p,
        "mng_paper_sum": r2(sum(mng_c.values())), "mng_paper_days": len(mng_c),
        "meic_all_days_sum": r2(sum(v for d, v in dp.items() if "2026-09-30" <= d <= CUTOFF)),
    }
    passed = (p is not None and p >= P_REQ and mn is not None and mn > 0)
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
