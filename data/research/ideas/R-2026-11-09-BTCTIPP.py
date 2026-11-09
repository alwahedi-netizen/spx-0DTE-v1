"""R-2026-11-09-BTCTIPP — Time-Invariant Portfolio Protection (TIPP) on Bitcoin:
exposure = multiplier x cushion above a floor that ratchets up with the
strategy's own high-water mark, reset once a year. Canon mining (§2).

Sources:
  * Estep & Kritzman, "TIPP: Insurance without Complexity", Journal of
    Portfolio Management, Summer 1988, pp. 38-42 (the canon rule: CPPI whose
    floor = a fixed share of the portfolio's highest value to date).
  * Quantpedia (Baglini & Berrada), "Time Invariant Portfolio Protection",
    2023-10-11, https://quantpedia.com/time-invariant-portfolio-protection/ —
    worked example floor 85% of capital, multiplier m = 4; suggests m 2-4;
    daily rebalancing best Sharpe, weekly used in the cost example; tested on
    simulated GBM/jump processes only (no real-asset backtest).
  * AXA IM, "Understanding portfolio insurance management (CPPI/TIPP)",
    https://core.axa-im.com/investment-strategies/multi-asset/insights/understanding-portfolio-insurance-management-cppitipp
    — the TIPP ratchet is typically RESET annually in products (fixes the
    'cash lock' after a floor breach).
No published crypto backtest: the canon is the rule, BTC is our application.

Varies DD-2026-11-TREND / L-2026-11-07-BTCTRENDVOL / L-2026-11-08-BTC52WH:
those cut exposure on the PRICE's trend, volatility or distance from its
high; TIPP cuts on the STRATEGY'S OWN drawdown (path of its NAV), with
graded exposure. It is a loss-limit, not a forecast — a different mechanism
for the same product theme 10/16 says crypto rules deliver (crash
protection). Judged on risk-adjusted return and worst drop.

Rationale (written before any run): a convex payoff bought by dynamic
trading — de-levers as losses mount, so a slow −80% bear costs at most about
the cushion; the price is whipsaw (selling low/buying high in chop) and gap
risk (one −40% day, e.g. 2020-03-12, jumps through the floor and locks the
book in cash until the yearly reset). Counter-hypothesis: BTC's volatility
(~70%/yr) makes a 15% cushion too thin — the book sits mostly in cash and
only matches T-bills plus a sliver of BTC.

RULE (fixed before any run; Quantpedia's worked example + AXA's annual reset):
  * NAV V tracked inside the rule from BTC's close-to-close moves and the
    held weight (cash interest and costs ignored in V — small, stated).
  * Floor F: starts at f x V with f = 0.85; ratchets every close to
    max(F, f x V); RESET to f x V at the first close of each calendar year.
  * Each Sunday UTC close: weight = clip(m x (V - F) / V, 0, 1), m = 4 (so
    60% BTC at a fresh high-water mark). Between Sundays the weight drifts.
  * First day: weight = clip(m x (1 - f), 0, 1) = 0.60.
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (asset_class crypto).
Variants: m 3 / 5; f 0.80 / 0.90; daily rebalancing.
trials: 1 + 5 variants = 6; new family btc-portfolio-insurance."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "BTC-USD"


def make(m=4.0, f=0.85, daily=False, weekday=6):
    st = {}

    def target():
        if st["V"] <= 0:
            return 0.0
        return max(0.0, min(1.0, m * (st["V"] - st["F"]) / st["V"]))

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st.update(V=1.0, F=f, w=0.0)
            st["w"] = target()
            return {SYM: st["w"]} if st["w"] else {}
        a, b = px[SYM][i - 1], px[SYM][i]
        r = b / a - 1 if (a and b) else 0.0
        w = st["w"]
        st["V"] *= 1 + w * r
        st["w"] = w * (1 + r) / (1 + w * r) if 1 + w * r else 0.0   # drift
        if dates[i][:4] != dates[i - 1][:4]:
            st["F"] = f * st["V"]                                     # annual reset
        st["F"] = max(st["F"], f * st["V"])                           # ratchet
        if daily or date.fromisoformat(dates[i]).weekday() == weekday:
            st["w"] = target()
        return {SYM: st["w"]} if st["w"] else {}
    return weights


weights = make()

VARIANTS = {
    "m3": make(m=3.0),
    "m5": make(m=5.0),
    "f80": make(f=0.80),
    "f90": make(f=0.90),
    "daily": make(daily=True),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-09-BTCTIPP", weights, [SYM], bench=SYM, start="2015-01-01",
        asset_class="crypto", trials=6, family="btc-portfolio-insurance", variants=VARIANTS,
        notes="canon TIPP (Estep-Kritzman 1988; Quantpedia 2023 example f=0.85, m=4) on BTC: weight = "
              "clip(4 x (V-F)/V, 0, 1) each Sunday, floor ratchets at 85% of the strategy's high-water mark, "
              "reset each Jan; weights drift between Sundays; 25bp; vault sealed from 2024-11"),
        indent=1))
