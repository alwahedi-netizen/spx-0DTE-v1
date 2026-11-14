"""L-2026-11-14-HAVENSPLIT — pick the crisis currency by the kind of bear
market: yen + franc when yields fall, the dollar when they do not (lab
original, RESEARCH.md §2b: a combination of a shortlist block with the fix
for its stated gap).

VARIES: L-2026-11-08-HAVENRATES (shortlist, potential 3; unchanged by harness
fix 2: FXY + FXF only when SPY < 10-mo SMA AND IEF > 10-mo SMA; Sharpe 0.175,
worst drop -11%, confidence 77%). It sits in T-bills in the OTHER bear state
(SPY down, IEF down: 2022, 2018 Q4) — the rate-driven bear in which yen and
franc fall. HAVENSPLIT fills exactly that state with UUP (the sister script
L-2026-11-14-DOLHAVEN tests the dollar leg alone in all bears).
INGREDIENTS: DD-2026-11-TREND (SPY 10-mo SMA bear flag; IEF 10-mo SMA as the
yield-direction gauge, both exactly as HAVENRATES); Ranaldo & Soderlind,
"Safe Haven Currencies", Review of Finance 14(3) 2010
(https://econpapers.repec.org/RePEc:oup:revfin:v:14:y:2010:i:3:p:385-407):
JPY/CHF gain when US stocks fall AND US bond prices rise; Lilley, Maggiori,
Neiman & Schreger, REStat 2022 (https://www.nber.org/papers/w26046): the
dollar appreciates in post-2007 risk-off.
RATIONALE (written before any run): two different crisis mechanisms. A
deflationary flight to quality (Treasuries rally) unwinds carry trades
funded in yen and francs, so the funding currencies rise. An inflationary or
rate-driven bear (Treasuries fall) widens the dollar's rate advantage and
adds dollar funding stress, so the dollar rises while the yen falls. One
bond-trend reading tells which mechanism is running.
OVERFITTING NOTE: the split was designed after seeing SAFEHAVEN fail in
2022 and HAVENRATES sit out 2022; the shared family's trial count (and the
one-time vault) is the guard. Vault caveat on the record: April 2025, the
dollar fell while SPY and IEF fell together (tariff shock) — the UUP leg's
known adverse event.

PASS CRITERION (pre-registered): research_bt verdict vs T-bills (§4 +
world-class gates); expected FAIL on t >= 3 (in the market only in bear
months). Building-block claim (potential >= 3): positive active return
overall AND in the recent half, worst drop no worse than HAVENRATES' -11%,
and Sharpe above HAVENRATES' 0.175 (i.e. the UUP leg must ADD, not dilute);
fit judged by the lead's portfolio.marginal.
DATA-TIMING: both flags read the month-end closes of SPY and IEF on bar i
(the month's last trading day) and earlier month-ends; instruments FXY, FXF,
UUP are US-listed 4pm closes (no `=X` data). Weights decided at close i earn
close i -> close i+1, held through the next month-end.
RULE (fixed before any run):
  * At each month-end close: bear = SPY < mean of its last N month-end
    closes; rally = IEF > mean of its last N month-end closes; N = 10.
  * bear AND rally -> FXY 50% + FXF 50%; bear AND NOT rally -> UUP 100%;
    not bear -> T-bills. Missing price / fewer than N month-ends -> T-bills.
  * Variants (same N on both flags): 8, 9, 11, 12.
Instruments: CurrencyShares FXY / FXF (deposit-backed), UUP (futures +
T-bills), all Schwab-tradeable. Benchmark T-bills; asset_class "fx" (2bp).
Start 2007-03-01 (UUP lists 2007-02-20; FXY 2007-02). FAMILY "L-fx-safehaven"
(42 lifetime trials + DOLHAVEN 5 if run first) -> honest trials 52.
Never vault.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "L-2026-11-14-HAVENSPLIT"
HAVENS = ["FXY", "FXF"]
SYMS = HAVENS + ["UUP", "SPY", "IEF"]


def make(n_months=10):
    st = {"w": {}, "spy": [], "ief": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["spy"], st["ief"] = {}, [], []   # evaluate() re-simulates
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if px["SPY"][i]:
                st["spy"].append(px["SPY"][i])
            if px["IEF"][i]:
                st["ief"].append(px["IEF"][i])
            s, b = st["spy"], st["ief"]
            ready = len(s) >= n_months and len(b) >= n_months
            bear = ready and s[-1] < sum(s[-n_months:]) / n_months
            rally = ready and b[-1] > sum(b[-n_months:]) / n_months
            if bear and rally and all(px[h][i] for h in HAVENS):
                st["w"] = {h: 1.0 / len(HAVENS) for h in HAVENS}
            elif bear and not rally and px["UUP"][i]:
                st["w"] = {"UUP": 1.0}
            else:
                st["w"] = {}
        return st["w"]
    return weights


weights = make(10)
VARIANTS = {"SMA8": make(8), "SMA9": make(9), "SMA11": make(11), "SMA12": make(12)}

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, SYMS, None, start="2007-03-01", asset_class="fx",
                    trials=52, family="L-fx-safehaven", variants=VARIANTS,
                    notes="SPY < 10-mo SMA: IEF > 10-mo SMA -> FXY+FXF 50/50 (HAVENRATES), else UUP; "
                          "not bear -> T-bills; month-end; varies L-2026-11-08-HAVENRATES (fills its "
                          "rising-yield bear gap with the dollar)")
    print(json.dumps(r, indent=1))
