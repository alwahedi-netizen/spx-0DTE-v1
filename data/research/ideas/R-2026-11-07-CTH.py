"""R-2026-11-07-CTH — carry-trend-hedge duration timing (Newfound Research).
Source: Newfound Research, "A Carry-Trend-Hedge Approach to Duration Timing"
(2018-10-15): https://blog.thinknewfound.com/2018/10/a-carry-trend-hedge-approach-to-duration-timing/
(companion: "Timing Bonds with Value, Momentum, and Carry",
https://blog.thinknewfound.com/2018/01/timing-bonds-value-momentum-carry/).
Source result 1972-2018 (10y vs short-term, long/short, gross): integrated
vote 3.5%/yr, Sharpe 0.49 vs long-only 0.27.

Rationale: three independently documented duration premia — carry (a steep
curve pays the holder; Koijen et al.), trend (bond excess returns are
autocorrelated; Durham), and the flight-to-quality hedge (Treasuries rally
after equity sell-offs). Each is weak alone; a vote needs two to agree.
VARIES nothing in the ledger directly; its trend leg overlaps DD-2026-11-TREND
(bond trend alone did nothing) — the combination is what is tested.

RULE (fixed before any run; the source's "integrated" majority vote, in the
long-only form a Schwab cash account can hold):
  decided on the first trading day of each month from data through the
  previous (month-end) close, traded at that day's close:
  * CARRY: s = ^TNX - ^IRX (10y minus 13-week bill; Yahoo has no 1-year
    yield, the source used 10y-1y). Percentile of today's s among the daily
    s of the prior 10 years (>= 5 years needed). vote +1 if pct >= 1/3, else -1.
  * TREND: daily excess log return of the bond fund over T-bills; EWMA with
    spans 21 and 252 days. +1 if both > 0, -1 if both < 0, else 0.
  * HEDGE: 63-day-span EWMA of daily S&P 500 (^GSPC) log returns; percentile
    among its prior 10 years of daily values. +1 if pct <= 0.25 (stocks have
    been weak -> own duration), -1 if pct >= 0.75, else 0.
  net = sum of votes (missing signal = 0). net > 0: 100% VFITX; else T-bills
  (the source's short leg becomes cash: the lab does not short bonds).
Bond: VFITX (Vanguard Intermediate-Term Treasury, IEF proxy, 1991-10+).
Benchmark: VFITX buy & hold. Costs 3bp. Backtest 1993-01-04+; signal history
before that (Yahoo 1985+) is pre-loaded from dates strictly BEFORE the start
(PRE), so no future data is ever used.
Variants: every lookback (21/252/63 spans and the 10y/5y percentile windows)
scaled by 0.5, 0.75, 1.25, 1.5. trials = 9 (the source compared 5
specifications — 3 single signals, combined, integrated — + our 4 neighbours)."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BOND, START = "VFITX", "1993-01-04"
SYMS = [BOND, "^TNX", "^IRX", "^GSPC"]
PRE = {"dates": [], "px": {s: [] for s in SYMS}}   # history strictly before START


def make(f=1.0):
    w_pct, min_pct = int(round(2520 * f)), int(round(1260 * f))
    a_fast, a_slow, a_eq = (2 / (21 * f + 1), 2 / (252 * f + 1), 2 / (63 * f + 1))
    st = {}

    def reset():
        st.update(spread=[], eqv=[], ef=None, es=None, eq=None, nb=0,
                  lastb=None, lastg=None, rf=0.0, w=None)

    def step(bond, tnx, irx, gspc):
        """Absorb ONE day's observations (called in date order)."""
        if tnx is not None and irx is not None:
            st["spread"].append(tnx - irx)
        if irx is not None:
            st["rf"] = irx / 100 / 252
        if bond and st["lastb"]:
            x = math.log(bond / st["lastb"]) - st["rf"]
            st["ef"] = x if st["ef"] is None else st["ef"] + a_fast * (x - st["ef"])
            st["es"] = x if st["es"] is None else st["es"] + a_slow * (x - st["es"])
            st["nb"] += 1
        if bond:
            st["lastb"] = bond
        if gspc and st["lastg"]:
            g = math.log(gspc / st["lastg"])
            st["eq"] = g if st["eq"] is None else st["eq"] + a_eq * (g - st["eq"])
            st["eqv"].append(st["eq"])
        if gspc:
            st["lastg"] = gspc

    def pct(hist):
        h = hist[-w_pct:]
        if len(h) < min_pct:
            return None
        v = h[-1]
        return sum(1 for x in h if x <= v) / len(h)

    def decide():
        votes = 0
        p = pct(st["spread"])
        if p is not None:
            votes += 1 if p >= 1 / 3 else -1
        if st["ef"] is not None and st["nb"] >= int(252 * f):
            if st["ef"] > 0 and st["es"] > 0:
                votes += 1
            elif st["ef"] < 0 and st["es"] < 0:
                votes -= 1
        q = pct(st["eqv"])
        if q is not None:
            votes += 1 if q <= 0.25 else (-1 if q >= 0.75 else 0)
        return {BOND: 1.0} if votes > 0 else {}

    def weights(i, dates, px):
        if i == 0:
            reset()
            for k in range(len(PRE["dates"])):
                step(*(PRE["px"][s][k] for s in SYMS))
        # decide from data through the previous close (day i not yet absorbed)
        if i == 0 or dates[i][:7] != dates[i - 1][:7]:
            st["w"] = decide()
        step(*(px[s][i] for s in SYMS))
        return st["w"] if st["w"] is not None else {BOND: 1.0}
    return weights


weights = make(1.0)

if __name__ == "__main__":
    import json
    d0, p0 = rb.prices(SYMS, "1985-01-01")
    keep = [k for k, d in enumerate(d0) if d < START]
    PRE["dates"] = [d0[k] for k in keep]
    PRE["px"] = {s: [p0[s][k] for k in keep] for s in SYMS}
    r = rb.evaluate("R-2026-11-07-CTH", weights, SYMS, BOND, start=START,
                    asset_class="bonds", trials=9, family="R-2026-11-07-CTH",
                    variants={f"x{f}": make(f) for f in (0.5, 0.75, 1.25, 1.5)},
                    notes="Newfound carry(10y-3m pct)+trend(EWMA 21/252)+hedge(S&P EWMA63 pct) "
                          "majority vote -> VFITX else T-bills; monthly; bench VFITX; 1993+")
    print(json.dumps(r, indent=1))
