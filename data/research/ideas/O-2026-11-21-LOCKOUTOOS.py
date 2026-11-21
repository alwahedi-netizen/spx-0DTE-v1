"""O-2026-11-21-LOCKOUTOOS — Options team, league round 2 (2026-11-21), lab.
Theme 27 out of sample: do same-side entries after a same-day stop lose?

SOURCE: KNOWLEDGE.md theme 27 (options desk, 2026-11-11, in-sample on
paper MEIC + MNG through 2026-11-11): after a side is stopped, later
same-day entries on that SAME side lost -$9.1k on paper (166 sides) and
-$5.9k live (89), vs +$10.8k / +$8.2k for all other sides — concentrated
in ~5 trend days. It created paper lane MIIL (same-side lockout). No
session after 2026-11-11 was seen by that analysis.

STEP 1 — REPLICATION (league rule 1, sign and rough size): on paper MEIC +
MNG sessions <= 2026-11-11, post-stop same-side sides must sum <= -$5,000
(the source's -$9.1k, sign and rough size) while all other sides sum > 0.
If not, the verdict is FAIL "harness/data suspect" and step 2 is moot.

STEP 2 — HYPOTHESIS (written before any run): on the unseen sessions
2026-11-12 .. CUTOFF, MEIC's post-stop same-side sides lose money, so a
same-side lockout would have saved money: saving/day = -(sum pnl_actual
of that day's post-stop same-side MEIC sides), $0 on days without any.

DEFINITION: a side is post-stop same-side if an earlier position of the
SAME strategy, date and side has exit_reason STOPPED and its exit_ts is
before this side's signal_ts — exactly the engine's lockout test
(paper_engine.stopped_sides_today at slot time). MNG duplicates MEIC's
entries on negative-GEX days, so the confirm test uses MEIC only.
Caveat stated up front: dropping sides frees risk budget that could let a
later slot fill; MEIC's $5,000 budget rarely binds since late October, so
the replay ignores it. Supporting (not judged): the same counterfactual
on MNG, MIIS, MIIE, MIIF, MIIW in the confirm window (same days, not
independent), the MIIL lane minus MEIC paired by day, and live MEIC's own
post-stop same-side rows (opened_ts / closed_ts) in both windows.

DATA-TIMING: the lockout flag reads only exits stamped before the side's
own entry time on the same day; each side earns to its own same-day exit.
Sessions <= CUTOFF.

SPLIT (pre-declared): replication/develop = sessions <= 2026-11-11 (the
source's own window); confirm = 2026-11-12 .. CUTOFF (7 sessions — low
power, stated before the run).

PASS CRITERION: replication holds AND confirm mean daily saving > 0 with
day-bootstrap P(mean > 0) >= P_REQ. Family "O-LOCKOUT" (theme 27's
original split + this), trials 2 -> P_REQ = 0.95.
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

ID = "O-2026-11-21-LOCKOUTOOS"
FAMILY, FAMILY_TRIALS = "O-LOCKOUT", 2
P_REQ = 1 - 0.10 / FAMILY_TRIALS
DEV_END, CONF_START = "2026-11-11", "2026-11-12"
REPL_MAX = -5000.0
SUPPORT = ("MNG", "MIIS", "MIIE", "MIIF", "MIIW")


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


def flag_post_stop(items):
    """items: dicts with date, side, entry, exit, stopped. Adds 'post'."""
    g = defaultdict(list)
    for it in items:
        g[(it["date"], it["side"])].append(it)
    for grp in g.values():
        stops = [it["exit"] for it in grp if it["stopped"] and it["exit"]]
        for it in grp:
            it["post"] = any(x < it["entry"] for x in stops)
    return items


def paper_items(strategy, field="pnl_actual"):
    out = []
    for s in closed_sides(strategy, field):
        out.append({"date": s["date"], "side": s["side"], "entry": s["signal_ts"],
                    "exit": s["exit_ts"], "stopped": s["exit_reason"] == "STOPPED",
                    "pnl": s["pnl"]})
    return flag_post_stop(out)


def live_items():
    out = []
    for r in live_rows("MEIC"):
        v = fnum(r["pnl_live"])
        if v is None or not r.get("opened_ts"):
            continue
        out.append({"date": r["date"], "side": r["side"], "entry": r["opened_ts"],
                    "exit": r.get("closed_ts") or "", "stopped": r["exit_reason"] == "STOPPED",
                    "pnl": v})
    return flag_post_stop(out)


def split_sums(items, lo, hi):
    post = [it["pnl"] for it in items if lo <= it["date"] <= hi and it["post"]]
    other = [it["pnl"] for it in items if lo <= it["date"] <= hi and not it["post"]]
    return {"post_sides": len(post), "post_sum": r2(sum(post)),
            "other_sides": len(other), "other_sum": r2(sum(other))}


def savings(items, lo, hi):
    days = sorted({it["date"] for it in items if lo <= it["date"] <= hi})
    s = defaultdict(float)
    for it in items:
        if lo <= it["date"] <= hi and it["post"]:
            s[it["date"]] -= it["pnl"]
    return [s.get(d, 0.0) for d in days]


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "p_req": round(P_REQ, 3), "cutoff": CUTOFF}
    meic, mng = paper_items("MEIC"), paper_items("MNG")
    rep_meic = split_sums(meic, "0000", DEV_END)
    rep_mng = split_sums(mng, "0000", DEV_END)
    rep_post = (rep_meic["post_sum"] or 0) + (rep_mng["post_sum"] or 0)
    rep_other = (rep_meic["other_sum"] or 0) + (rep_mng["other_sum"] or 0)
    replicated = rep_post <= REPL_MAX and rep_other > 0
    res["replication"] = {"meic": rep_meic, "mng": rep_mng,
                          "post_sides": rep_meic["post_sides"] + rep_mng["post_sides"],
                          "post_sum": r2(rep_post), "other_sum": r2(rep_other),
                          "source": "-$9.1k over 166 sides vs +$10.8k others",
                          "replicated": replicated}
    sv = savings(meic, CONF_START, CUTOFF)
    res["confirm"] = {"sessions": len(sv), **split_sums(meic, CONF_START, CUTOFF),
                      "saving_sum": r2(sum(sv)), "saving_mean_day": r2(mean(sv)),
                      "days_with_post_sides": sum(1 for v in sv if v != 0),
                      "p_boot_saving_gt0": boot_pos(sv)}
    res["support_confirm_paper"] = {
        k: {**split_sums(paper_items(k), CONF_START, CUTOFF),
            "saving_sum": r2(sum(savings(paper_items(k), CONF_START, CUTOFF)))}
        for k in SUPPORT}
    miil = {d: v for d, v in day_pnl(closed_sides("MIIL")).items() if d >= CONF_START}
    base = {d: v for d, v in day_pnl(closed_sides("MEIC")).items() if d >= CONF_START}
    dd = [miil.get(d, 0.0) - base.get(d, 0.0) for d in sorted(set(miil) | set(base))]
    res["support_miil_minus_meic"] = {"sessions": len(dd), "sum": r2(sum(dd)),
                                      "mean_day": r2(mean(dd))}
    lv = live_items()
    res["support_live"] = {"develop": split_sums(lv, "0000", DEV_END),
                           "confirm": split_sums(lv, CONF_START, CUTOFF)}
    c = res["confirm"]
    passed = (replicated and c["saving_mean_day"] is not None and c["saving_mean_day"] > 0
              and c["p_boot_saving_gt0"] is not None and c["p_boot_saving_gt0"] >= P_REQ)
    if not replicated:
        res["verdict"] = "FAIL"
        res["reason"] = "replication failed: harness/data suspect"
    else:
        res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
