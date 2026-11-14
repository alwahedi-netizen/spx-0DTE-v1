"""L-2026-11-14-MBSVOL — agency MBS only when rate volatility is low (lab).
Scripts the bond desk's queued row L-2026-11-11-MBSVOL (same rule).

RATIONALE (written 2026-11-11, before any run): an agency MBS is a
Treasury plus a short position in the borrower's prepayment option, so
its spread over Treasuries is largely a payment for selling rate
volatility (Boyarchenko, Fuster & Lucca, "Understanding Mortgage
Spreads", RFS 32(10) 2019, https://doi.org/10.1093/rfs/hhz005: MBS OAS
compensates prepayment and rate-vol risk; Hanson JFE 2014: convexity
hedging amplifies rate moves). Like any short-vol carry trade it should
pay in calm regimes and lose when rate volatility is elevated (negative
convexity bites: 2008, 2013 taper, 2020 refi wave, 2022). Hold MBS only
while rate vol is below normal; park in duration-similar Treasuries
otherwise. The MBS sleeve is a new ingredient (no ledger row trades it).
Lab idea: no published rule to replicate (RESEARCH.md §2b); the
mechanism's evidence is the papers above.
RULE (fixed before any run): on the first trading day of each month
(weights at that close), from the PREVIOUS trading day's close: ^MOVE
(ICE BofA MOVE, Yahoo) < its average over the last WIN = 252 MOVE bars
(all dated before the trade day) -> MBB 1.0 for the month, else IEF 1.0.
Held all month. ^MOVE is loaded once outside the price panel (from
2002-11), so the evaluation period starts with MBB at 2007-04.
Benchmark: AGG buy & hold (as queued). Costs 3bp. Start 2007-04-01 (MBB
listed 2007-03-16; ^MOVE from 2002-11, so the 252-day average is full).
Variants (4): WIN 126 and 504; threshold x0.9 and x1.1 of the average.
trials = 5 (new family L-2026-11-14-MBSVOL).
CONTROL (printed, not a test, no evaluate call): the static 50/50
MBB/IEF mix and MBB buy & hold through the same simulate(), so the red
team can see whether the timing or merely owning MBB/IEF does the work
(theme 22).
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs AGG, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating AGG) AND a full-period
Sharpe above the static 50/50 MBB/IEF control.
DATA TIMING: the signal reads only ^MOVE values dated strictly before
dates[i] (the prior trading day's close; MOVE is an end-of-day options
index); the weight
decided at close i earns close i -> close i+1.
"""
import bisect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-14-MBSVOL"
BENCH, MBS, TSY, VOL = "AGG", "MBB", "IEF", "^MOVE"
START = "2007-04-01"


_MOVE = {}


def move_history():
    """^MOVE closes from 2002-11 (loaded once OUTSIDE the price panel so the
    average is full at START); only dates strictly before the trade day are read."""
    if not _MOVE:
        d, p = rb.prices([VOL], "2002-11-01")
        _MOVE["d"] = [x for x, v in zip(d, p[VOL]) if v]
        _MOVE["v"] = [v for v in p[VOL] if v]
    return _MOVE["d"], _MOVE["v"]


def make(win=252, mult=1.0):
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0 or dates[i][:7] != dates[i - 1][:7]:
            md, mv = move_history()
            k = bisect.bisect_left(md, dates[i])          # MOVE bars strictly before dates[i]
            hist = mv[max(0, k - win):k]
            if k == 0 or len(hist) < int(0.9 * win):
                st["w"] = {BENCH: 1.0} if px[BENCH][i] else {}
                return st["w"]
            now = mv[k - 1]
            sym = MBS if now < mult * sum(hist) / len(hist) else TSY
            st["w"] = {sym: 1.0} if px[sym][i] else {}
        return st["w"]
    return weights


def control():
    """Static 50/50 MBB/IEF and MBB buy & hold on the same calendar (printed only)."""
    dates, px = rb.prices([BENCH, MBS, TSY], START)
    keep = [k for k, d in enumerate(dates) if START <= d < rb.VAULT_FROM]
    dates = [dates[k] for k in keep]
    px = {s: [px[s][k] for k in keep] for s in px}
    rf = rb.tbill(dates)
    out = {}
    for name, w in (("STATIC_5050", {MBS: 0.5, TSY: 0.5}), ("MBB_BH", {MBS: 1.0})):
        rets, _ = rb.simulate(lambda i, d, p, w=w: w, dates, px, rf, 3.0)
        out[name] = {"cagr": round(rb.cagr(rets), 4), "sharpe": round(rb.sharpe(rets, rf[1:]), 3),
                     "maxdd": round(rb.max_dd(rets), 4)}
    return out


weights = make()

if __name__ == "__main__":
    r = rb.evaluate(ID, weights, [MBS, TSY], BENCH, start=START,
                    asset_class="bonds", trials=5, family=ID,
                    variants={"WIN126": make(126), "WIN504": make(504),
                              "X0.9": make(252, 0.9), "X1.1": make(252, 1.1)},
                    notes="first trading day of each month: ^MOVE (prior close) < its 252-day "
                          "average -> MBB, else IEF; bench AGG; lab (MBS = short rate-vol carry)")
    r["control_not_a_test"] = control()
    print(json.dumps(r, indent=1))
