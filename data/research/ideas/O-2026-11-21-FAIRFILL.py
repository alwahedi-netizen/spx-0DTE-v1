"""O-2026-11-21-FAIRFILL — Options team, league round 2 (2026-11-21), lab.
What drives the theo-vs-SIM gap, and is "mid minus a measured cost" a
faithful live proxy for the paper lanes?

CONTEXT: paper MEIC whole life is -$1,550 on pnl_actual (SIM fills) but
+$3,622 on pnl_theo (mid). The SIM rule (paper_config.yaml execution:
entry credit - $0.05, stop/TP exit + $0.05, no fees) makes the gap
MECHANICAL: $5 on every entry plus $5 on every STOPPED or TP exit, $0 on
EXPIRED. The 292 paper TP exits are almost all at a theo value of 0.00
(all after 15:00), while live let 95 of its 111 TP sides cash-settle at
0.00 ("too late to close") — so part of the SIM gap is a paper artefact.
Theme 32: live filled sides beat paper pnl_actual by +$8.7/side. If the
SIM is too harsh, every paper lane (MEIC 2.0, MNG, MPM) is being judged on
the wrong cost, and any re-arm decision with it.

HYPOTHESIS (written before any run): a 3-number fair-fill model fitted on
the live DEVELOP window — cost[t] = mean(pnl_theo - pnl_live) over filled
live MEIC sides whose PAPER exit type is t (TP / STOPPED / EXPIRED) —
predicts the live P&L of filled sides in the CONFIRM window without bias
(within $5/side), and better than the SIM's pnl_actual does.

MEASURE: real-money MEIC sides with a fill (pnl_live set), excluding live
exit_reason HALT (the live daily rail; paper has none) and shifted strikes
(shift set), matched to the paper twin by position_id. Confirm error per
side e = pnl_live - (pnl_theo - cost[paper exit type]); SIM error
e_sim = pnl_live - pnl_actual. Per-session mean error; sessions are the
resampling unit. A type absent from develop falls back to the develop
all-type mean cost. Also reported (information, not judged): the SIM gap
decomposed by exit type, live entry slip (credit_theo - credit_fill) by
slot, and every MEIC-mechanics lane re-priced with the fair costs (MIIF's
lower credit and MIIW's wider wings may cost differently live: caveat).

DATA-TIMING: nothing is predicted; costs are fitted on develop sessions
only and applied unchanged to later sessions. Sessions <= CUTOFF.

SPLIT (pre-declared, same as O-2026-11-14-LIVEDRIFT): develop = live
sessions <= 2026-10-16; confirm = 2026-10-19 .. CUTOFF.

PASS CRITERION (confirm): |mean per-session fair error| <= 5, AND the
day-bootstrap interval of that mean (level 1 - 0.10/3) lies inside
[-15, +15], AND |fair bias| < |SIM bias|. Family "O-LIVEDRIFT" (LIVEDRIFT,
MISSEDFILLS, this), trials 3.
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

ID = "O-2026-11-21-FAIRFILL"
FAMILY, FAMILY_TRIALS = "O-LIVEDRIFT", 3
ALPHA = 0.10 / FAMILY_TRIALS
LIVE_DEV_END = "2026-10-16"
CONF_START = "2026-10-19"
BIAS_MAX, CI_MAX = 5.0, 15.0
LANES = ("MEIC", "MNG", "MIIS", "MIIE", "MIIF", "MIIW", "MIIL", "MPM")


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


def paper_index():
    return {r["position_id"]: r for r in read("positions.csv")}


def usable_live(paper, lo, hi):
    """Filled, non-HALT, unshifted real-money MEIC sides with a paper twin."""
    out = []
    for r in live_rows("MEIC"):
        if not (lo <= r["date"] <= hi):
            continue
        if fnum(r["pnl_live"]) is None or r["exit_reason"] == "HALT" or (r.get("shift") or "").strip():
            continue
        p = paper.get(r["position_id"])
        if not p or fnum(p["pnl_theo"]) is None or fnum(p["pnl_actual"]) is None:
            continue
        out.append((r, p))
    return out


def fit_costs(pairs):
    g = defaultdict(list)
    for r, p in pairs:
        g[p["exit_reason"]].append(float(p["pnl_theo"]) - float(r["pnl_live"]))
    allc = [c for v in g.values() for c in v]
    costs = {k: mean(v) for k, v in g.items()}
    costs["_ALL"] = mean(allc)
    counts = {k: len(v) for k, v in g.items()}
    return costs, counts


def fair(p, costs):
    return float(p["pnl_theo"]) - costs.get(p["exit_reason"], costs["_ALL"])


def errors(pairs, costs):
    fe, se = defaultdict(list), defaultdict(list)
    for r, p in pairs:
        live = float(r["pnl_live"])
        fe[r["date"]].append(live - fair(p, costs))
        se[r["date"]].append(live - float(p["pnl_actual"]))
    days = sorted(fe)
    return [mean(fe[d]) for d in days], [mean(se[d]) for d in days], sum(len(v) for v in fe.values())


def sim_gap(lo, hi):
    """theo - actual by paper exit type, MEIC (the mechanical SIM cost)."""
    g = defaultdict(list)
    for s in closed_sides("MEIC", "pnl_actual"):
        if lo <= s["date"] <= hi and fnum(s["pnl_theo"]) is not None:
            g[s["exit_reason"]].append(float(s["pnl_theo"]) - s["pnl"])
    return {k: [len(v), r2(mean(v)), r2(sum(v))] for k, v in sorted(g.items())}


def entry_slip(pairs):
    g = defaultdict(list)
    for r, p in pairs:
        cf, ct = fnum(r["credit_fill"]), fnum(p["credit_theo"])
        if cf is not None and ct is not None:
            g[r["slot"]].append((ct - cf) * 100)
    return {k: [len(v), r2(mean(v))] for k, v in sorted(g.items())}


def lane_table(costs, lo, hi):
    out = {}
    for lane in LANES:
        th = ac = fa = 0.0
        n = 0
        days = set()
        for s in closed_sides(lane, "pnl_actual"):
            if not (lo <= s["date"] <= hi) or fnum(s["pnl_theo"]) is None:
                continue
            n += 1
            days.add(s["date"])
            th += float(s["pnl_theo"])
            ac += s["pnl"]
            fa += fair(s, costs)
        out[lane] = {"sessions": len(days), "sides": n, "theo": r2(th),
                     "sim_actual": r2(ac), "fair": r2(fa)}
    return out


def main():
    paper = paper_index()
    dev = usable_live(paper, "0000", LIVE_DEV_END)
    conf = usable_live(paper, CONF_START, CUTOFF)
    costs, counts = fit_costs(dev)
    fe, se, n_conf = errors(conf, costs)
    fe_dev, se_dev, n_dev = errors(dev, costs)
    bias, bias_sim = mean(fe), mean(se)
    ci = boot_ci(fe, lo=ALPHA / 2, hi=1 - ALPHA / 2)
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS,
           "ci_level": round(1 - ALPHA, 4), "cutoff": CUTOFF,
           "fair_costs_per_side": {k: r2(v) for k, v in costs.items()},
           "fit_sides_by_type": counts,
           "develop": {"sides": n_dev, "sessions": len(fe_dev),
                       "fair_bias_in_sample": r2(mean(fe_dev)), "sim_bias": r2(mean(se_dev))},
           "confirm": {"sides": n_conf, "sessions": len(fe),
                       "fair_bias": r2(bias), "fair_ci": ci, "sim_bias": r2(bias_sim),
                       "fair_mae_day": r2(mean([abs(v) for v in fe])),
                       "sim_mae_day": r2(mean([abs(v) for v in se]))},
           "sim_gap_by_exit_meic_whole_life": sim_gap("0000", CUTOFF),
           "sim_gap_format": "[sides, mean theo-actual, sum]",
           "live_entry_slip_by_slot_confirm": entry_slip(conf),
           "lanes_whole_life": lane_table(costs, "0000", CUTOFF),
           "lanes_confirm_window": lane_table(costs, CONF_START, CUTOFF)}
    passed = (bias is not None and abs(bias) <= BIAS_MAX and ci is not None
              and ci[0] >= -CI_MAX and ci[1] <= CI_MAX
              and bias_sim is not None and abs(bias) < abs(bias_sim))
    res["verdict"] = "PASS" if passed else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
