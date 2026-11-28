"""O-2026-11-28-JOURNALQA — Options team, league round 3 (2026-11-28), lab.
Data-quality audit of the paper journal itself, before anyone builds on it.

CONTEXT: theme 35 (round 2): a data/timing error costs -5 and, worse, puts
a wrong number in front of the owner. Every Options study so far trusted
data/paper/positions.csv row by row. This study checks, row by row, that
the journal obeys the engine's OWN rules (paper_engine.py:
vertical_pnl, sim_entry_credit / sim_exit_value with 0.05 slippage,
settle_value at spx_close_for(d), stop_triggered, the fly group rule)
and the calendar (2026-11-27 closed at 13:00 ET; the engine has no
early-close logic, and its 16:05 settlement read a quote 3 h after the
close). It also cross-checks every EXPIRED settlement against the
official index close (Yahoo ^GSPC; for 11-27 that is the 13:00 close).

HYPOTHESIS (written before any run): the journal is internally consistent:
every closed row of the ACTIVE lanes satisfies all scored checks below.

SCORED CHECKS (active lanes: MEIC MNG MPM MIIS MIIE MIIF MIIW MIIL FLY FLYR
ORB OCB; retired lanes METF BAND LATE PBW MEP are reported, never scored):
 Q1 position_id unique (whole file).
 Q2 closed row complete: exit_reason in {TP, STOPPED, EXPIRED}; credit_theo,
    exit_value_theo, pnl_theo, credit_actual, exit_value_actual,
    pnl_actual all numeric. An OPEN row dated before the last journal date
    is a violation (stale open).
 Q3 pnl_theo   == (credit_theo - exit_value_theo) * 100 * contracts  (+-0.011)
 Q4 pnl_actual == (credit_actual - exit_value_actual) * 100 * contracts (+-0.011)
 Q5 SIM fill (fill_notes starting "SIM fill", errata rows excepted):
    credit_actual == credit_theo - 0.05 (floored at 0 for credits) and
    exit_value_actual == exit_value_theo (+0.05 unless EXPIRED)  (+-0.001)
 Q6 timing: position date == signal_ts date; exit_ts >= signal_ts; TP /
    STOPPED exits on the position date at or before 16:00:59 ET; on an
    early-close date (2026-11-27) no signal_ts at/after 13:00 and no TP /
    STOPPED exit after 13:05 ET.
 Q7 width: |short - long| == the lane's configured wing (30; MIIW 50;
    FLY/FLYR 40).
 Q8 EXPIRED settlement: exit_value_theo == settle_value(side, short, long,
    S_engine) (+-0.011), S_engine = band.csv spx_close else next session's
    day.csv prior_close (the engine's own spx_close_for). AND the same value
    at S_index (Yahoo ^GSPC close of that date) differs by <= 0.25 points
    of spread value ($25/contract; smaller gaps are quote-vs-official-close
    noise, not an error). If Yahoo is unavailable, the index half is
    skipped and said so (not a pass by default: the verdict needs it).
 Q9 stop / TP: per-side-stop lanes (MEIC MNG MPM MIIx): STOPPED exit_value_
    theo >= stop_level - 0.005; TP exit_value_theo <= 0.055 (TP fires when
    the short leg's mid <= 0.05, so the spread is worth <= 0.05). Fly
    groups (FLY, FLYR; rows sharing date+strategy+signal_ts): STOPPED sum
    exit >= 1.25 * sum credit - 0.01; TP sum exit <= 0.75 * sum credit + 0.01.
 Q10 linkage: every slotted ladder row (MEIC MNG MPM MIIx) has a signals.csv
    SELL_CONDOR / SELL_VERTICAL row with the same date, strategy and slot
    whose strikes contain the row's short and long strikes; MNG's signal
    reads gex_sign == "negative".
REPORTED ONLY: retired-lane violations; EXPIRED rows booked after their
date; day.csv OK rows on non-trading dates (11-26 holiday); MNG missing on
a negative-GEX session where MEIC traded; the S_engine-vs-S_index gap per
EXPIRED date.

PRE-DECLARED KNOWN EXCEPTIONS (listed, not scored): the 2026-11-27 FLY rows
(entered 13:00:06 on frozen quotes — league brief: excluded everywhere);
the three 2026-09-29 errata rows (heal_journal); MNG 2026-11-25 (regime
feed "unknown" — missing, not a decision).

DATA-TIMING: nothing is predicted; this audits realised journal rows dated
<= CUTOFF against the engine's own rules and the official close of the
SAME date (an audit, not a signal — no trading decision reads it).

SPLIT (pre-declared): develop = rows dated <= 2026-11-20 (everything
earlier league studies used); confirm = 2026-11-23 .. CUTOFF (new rows).

PASS CRITERION: zero scored violations in develop AND zero in confirm AND
the index cross-check ran. Family "O-JOURNALQA", trials 1 (a measurement;
no P-value). A FAIL lists every violation so the lead can say which past
results it touches.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "data" / "paper"
CUTOFF = "2026-11-27"            # last session included (frozen at pre-registration)
SEED, NBOOT = 20261128, 10000

ID = "O-2026-11-28-JOURNALQA"
FAMILY, FAMILY_TRIALS = "O-JOURNALQA", 1
DEV_END, CONF_START = "2026-11-20", "2026-11-23"
EARLY_CLOSE = {"2026-11-27": "13:00", "2026-12-24": "13:00"}
ACTIVE = ("MEIC", "MNG", "MPM", "MIIS", "MIIE", "MIIF", "MIIW", "MIIL",
          "FLY", "FLYR", "ORB", "OCB")
PER_SIDE_STOP = ("MEIC", "MNG", "MPM", "MIIS", "MIIE", "MIIF", "MIIW", "MIIL")
FLY_GROUP = ("FLY", "FLYR")
WIDTH = {s: 30.0 for s in ACTIVE}
WIDTH.update({"MIIW": 50.0, "FLY": 40.0, "FLYR": 40.0})
SLIP = 0.05
KNOWN_FLY_DAY = "2026-11-27"
KNOWN_MNG_MISSING = {"2026-11-25"}
INDEX_TOL = 0.25                 # points of spread value ($25 per contract)

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


def hm(ts):
    """'2026-11-27T13:00:06-05:00' -> ('2026-11-27', '13:00:06') (ET wall clock)."""
    return (ts[:10], ts[11:19]) if ts and len(ts) >= 19 else (None, None)


def intrinsic(side, strike, spx):
    return max(0.0, spx - strike) if side == "CALL" else max(0.0, strike - spx)


def settle_value(side, short, long_, spx):
    return intrinsic(side, short, spx) - intrinsic(side, long_, spx)


def engine_close():
    """paper_engine.spx_close_for: band.csv spx_close, else the next session's prior_close."""
    band = {r["date"]: fnum(r.get("spx_close")) for r in read("band.csv")}
    rows = sorted((d, fnum(r.get("prior_close"))) for d, r in day_tags().items())
    nxt = {}
    for i in range(len(rows) - 1):
        nxt[rows[i][0]] = rows[i + 1][1]

    def f(d):
        if band.get(d) is not None:
            return band[d]
        return nxt.get(d)
    return f


def index_close():
    try:
        sys.path.insert(0, str(ROOT))
        import research_bt as rb
        dates, px = rb.prices(["^GSPC"], start="2026-08-01")
        return dict(zip(dates, px["^GSPC"])), "yahoo ^GSPC"
    except Exception as e:                      # noqa: BLE001 — report it
        return {}, f"unavailable: {e}"


class Book:
    def __init__(self):
        self.v = defaultdict(list)              # (half, check) -> [msg]
        self.rep = defaultdict(list)            # report-only

    def add(self, d, check, msg, scored=True):
        if not scored:
            self.rep[check].append(msg)
            return
        half = "develop" if d <= DEV_END else "confirm"
        self.v[(half, check)].append(msg)

    def summary(self, half):
        out = {}
        for (h, c), m in sorted(self.v.items()):
            if h == half:
                out[c] = {"n": len(m), "examples": m[:6]}
        return out


def main():
    res = {"id": ID, "family": FAMILY, "family_trials": FAMILY_TRIALS, "cutoff": CUTOFF}
    pos = read("positions.csv")
    sig = read("signals.csv")
    S_eng = engine_close()
    S_idx, idx_src = index_close()
    res["index_source"] = idx_src
    bk = Book()
    known = []
    last_date = max(r["position_id"][:10] for r in pos if r["position_id"][:10] <= CUTOFF)

    # Q1 duplicates
    seen = defaultdict(int)
    for r in pos:
        seen[r["position_id"]] += 1
    for pid, n in seen.items():
        if n > 1 and pid[:10] <= CUTOFF:
            bk.add(pid[:10], "Q1_duplicate_id", f"{pid} x{n}")

    sig_ix = defaultdict(list)
    for s in sig:
        if s["action"] in ("SELL_CONDOR", "SELL_VERTICAL"):
            sig_ix[(s["date"], s["strategy"], s["slot"])].append(s)

    groups = defaultdict(list)
    counts = defaultdict(int)
    expired_gap = {}
    for r in pos:
        pid, st = r["position_id"], r["strategy"]
        d = pid[:10]
        if d > CUTOFF:
            continue
        scored = st in ACTIVE
        tag = pid
        if "errata" in (r.get("fill_notes") or ""):
            known.append(f"{pid}: 2026-09-29 errata row (heal_journal)")
            continue
        sd, stime = hm(r["signal_ts"])
        if st == "FLY" and d == KNOWN_FLY_DAY and stime and stime >= "13:00:00":
            known.append(f"{pid}: FLY entered {stime} on the 13:00 close day (excluded by brief)")
            continue
        counts[("develop" if d <= DEV_END else "confirm", scored)] += 1
        if not r["exit_ts"]:
            if d < last_date:
                bk.add(d, "Q2_stale_open", tag, scored)
            continue
        ct, et, pt = fnum(r["credit_theo"]), fnum(r["exit_value_theo"]), fnum(r["pnl_theo"])
        ca, ea, pa = fnum(r["credit_actual"]), fnum(r["exit_value_actual"]), fnum(r["pnl_actual"])
        k = int(fnum(r["contracts"]) or 1)
        reason = r["exit_reason"]
        if reason not in ("TP", "STOPPED", "EXPIRED") or None in (ct, et, pt, ca, ea, pa):
            bk.add(d, "Q2_incomplete", f"{tag} reason={reason}", scored)
            continue
        # Q3 / Q4 arithmetic
        if abs((ct - et) * 100 * k - pt) > 0.011:
            bk.add(d, "Q3_pnl_theo", f"{tag} {ct}-{et} vs {pt}", scored)
        if abs((ca - ea) * 100 * k - pa) > 0.011:
            bk.add(d, "Q4_pnl_actual", f"{tag} {ca}-{ea} vs {pa}", scored)
        # Q5 SIM fill model
        if (r.get("fill_notes") or "").startswith("SIM fill"):
            want_c = ct - SLIP if ct <= 0 else max(0.0, ct - SLIP)
            want_e = et if reason == "EXPIRED" else et + SLIP
            if abs(ca - want_c) > 0.001 or abs(ea - want_e) > 0.001:
                bk.add(d, "Q5_sim_fill", f"{tag} credit {ct}->{ca} exit {et}->{ea} ({reason})", scored)
        # Q6 timing
        xd, xtime = hm(r["exit_ts"])
        if sd != d:
            bk.add(d, "Q6_signal_date", f"{tag} signal {r['signal_ts']}", scored)
        if r["exit_ts"] < r["signal_ts"]:
            bk.add(d, "Q6_exit_before_entry", f"{tag}", scored)
        if reason in ("TP", "STOPPED") and (xd != d or xtime > "16:00:59"):
            bk.add(d, "Q6_exit_time", f"{tag} {reason} at {r['exit_ts']}", scored)
        if reason == "EXPIRED" and xd != d:
            bk.add(d, "late_settlement_booking", f"{tag} booked {r['exit_ts']}", False)
        if d in EARLY_CLOSE:
            if stime and stime >= EARLY_CLOSE[d] + ":00":
                bk.add(d, "Q6_entry_after_early_close", f"{tag} signal {stime}", scored)
            if reason in ("TP", "STOPPED") and xtime and xtime > "13:05:00":
                bk.add(d, "Q6_exit_after_early_close", f"{tag} {reason} {xtime}", scored)
        sk, lk = fnum(r["short_strike"]), fnum(r["long_strike"])
        # Q7 width
        if st in WIDTH and sk is not None and lk is not None and abs(abs(sk - lk) - WIDTH[st]) > 0.001:
            bk.add(d, "Q7_width", f"{tag} {sk}/{lk}", scored)
        # Q8 settlement
        if reason == "EXPIRED" and sk is not None and lk is not None:
            se = S_eng(d)
            if se is None:
                bk.add(d, "Q8_no_engine_close", tag, scored)
            else:
                v = settle_value(r["side"], sk, lk, se)
                if abs(v - et) > 0.011:
                    bk.add(d, "Q8_settle_engine", f"{tag} booked {et} vs {v:.2f} at {se}", scored)
                si = S_idx.get(d)
                if si is not None:
                    expired_gap[d] = round(se - si, 2)
                    vi = settle_value(r["side"], sk, lk, si)
                    if abs(vi - et) > INDEX_TOL:
                        bk.add(d, "Q8_settle_index",
                               f"{tag} booked {et} at {se} vs {vi:.2f} at index close {si:.2f}"
                               f" (booked P&L {'over' if vi > et else 'under'}stated by ${abs(vi - et) * 100 * k:.0f})",
                               scored)
                elif S_idx:
                    bk.add(d, "Q8_no_index_close", tag, scored)
        # Q9 stop / TP
        if st in PER_SIDE_STOP:
            sl = fnum(r["stop_level"])
            if reason == "STOPPED" and sl is not None and et < sl - 0.005:
                bk.add(d, "Q9_stop_below_level", f"{tag} exit {et} < stop {sl}", scored)
            if reason == "TP" and et > 0.055:
                bk.add(d, "Q9_tp_value", f"{tag} TP at {et}", scored)
        if st in FLY_GROUP:
            groups[(d, st, r["signal_ts"])].append((reason, ct, et))
        # Q10 linkage
        if st in PER_SIDE_STOP:
            _, _, slot, _ = parse_pid(pid)
            cands = sig_ix.get((d, st, slot), [])
            ok = False
            for s in cands:
                shorts = {fnum(s["short_strike"]), fnum(s["short_strike_2"])}
                longs = {fnum(s["long_strike"]), fnum(s["long_strike_2"])}
                if sk in shorts and lk in longs:
                    ok = True
                    if st == "MNG" and s.get("gex_sign") != "negative":
                        bk.add(d, "Q10_mng_not_negative", f"{tag} gex={s.get('gex_sign')}", scored)
            if not ok:
                bk.add(d, "Q10_no_signal", f"{tag} ({len(cands)} candidate signals)", scored)

    for (d, st, ts), legs in groups.items():
        reasons = {x[0] for x in legs}
        sc, se_ = sum(x[1] for x in legs), sum(x[2] for x in legs)
        if len(reasons) > 1:
            bk.add(d, "Q9_fly_split_exit", f"{d} {st} {ts} reasons {sorted(reasons)}")
        elif "STOPPED" in reasons and se_ < 1.25 * sc - 0.01:
            bk.add(d, "Q9_fly_stop", f"{d} {st} {ts} value {se_:.2f} < 1.25x{sc:.2f}")
        elif "TP" in reasons and se_ > 0.75 * sc + 0.01:
            bk.add(d, "Q9_fly_tp", f"{d} {st} {ts} value {se_:.2f} > 0.75x{sc:.2f}")

    # report-only: holiday rows in day.csv, missing MNG days
    traded = {r["position_id"][:10] for r in pos}
    tags = day_tags()
    res["daycsv_rows_without_trades"] = sorted(d for d in tags if d not in traded and d <= CUTOFF
                                               and d >= "2026-09-08")
    meic_days = {r["position_id"][:10] for r in pos if r["strategy"] == "MEIC"}
    mng_days = {r["position_id"][:10] for r in pos if r["strategy"] == "MNG"}
    miss = sorted(d for d in meic_days if d >= "2026-09-30" and d <= CUTOFF and d not in mng_days
                  and (tags.get(d) or {}).get("gex_sign") == "negative")
    res["mng_missing_on_negative_gex_days"] = miss
    res["known_exceptions"] = known + [f"{d}: MNG skipped (regime unknown)" for d in sorted(KNOWN_MNG_MISSING)]
    res["engine_minus_index_close_on_expiry_dates"] = expired_gap
    res["rows_checked"] = {f"{h}_{'active' if s else 'retired'}": n for (h, s), n in sorted(counts.items())}
    res["develop_violations"] = bk.summary("develop")
    res["confirm_violations"] = bk.summary("confirm")
    res["report_only"] = {c: {"n": len(m), "examples": m[:6]} for c, m in bk.rep.items()}
    nd = sum(x["n"] for x in res["develop_violations"].values())
    nc = sum(x["n"] for x in res["confirm_violations"].values())
    res["develop_n"], res["confirm_n"] = nd, nc
    index_ran = bool(S_idx)
    res["index_check_ran"] = index_ran
    res["verdict"] = "PASS" if (nd == 0 and nc == 0 and index_ran) else "FAIL"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
