"""L-2026-11-07-CARRYTREND — high-yield currency carry de-risked by the equity
trend (lab original, RESEARCH.md §2b: carry x a crash signal from another class).

INGREDIENTS:
  * Brunnermeier, Nagel & Pedersen, "Carry Trades and Currency Crashes", NBER
    Macroeconomics Annual 2008
    (https://markus.scholar.princeton.edu/sites/g/files/toruqf2651/files/carry_trades_currency_crashes.pdf):
    carry returns are negatively skewed; crashes come with rising risk
    aversion / equity sell-offs as speculators unwind.
  * DD-2026-11-TREND (shortlist, potential 5): the S&P 500 10-month SMA is the
    lab's most reliable crash filter across asset classes.

RATIONALE (written before any run): the Australian dollar is the classic
risk-on carry currency; its carry is earned slowly in calm markets and lost
in equity crashes (2008: AUD -35% vs USD). If the equity-trend switch is off
during those crashes, the carry is kept and the crash avoided. Differs from
P-FX CARRY-V (veto by the CURRENCY's own 12-month trend): here the veto is a
cross-asset equity signal, which turns earlier in global risk-off episodes.
Expected failure: AUD falls for domestic reasons while US equities rally
(2013-15 commodity bust) and fast V-shaped equity rebounds (2020) whipsaw.

RULE (fixed before any run, trials=1 + 4 neighbours):
  * At each month-end close: if SPY's close is above the average of its last
    10 month-end closes -> hold FXA (AUD, CurrencyShares; deposit-backed, so
    it earns the AUD deposit rate minus a 0.40% fee) at 100% next month;
    else T-bills. Until 10 SPY month-ends exist: hold FXA (= the benchmark).
  * Variants: SMA of 8, 9, 11, 12 month-ends.
Benchmark: FXA buy & hold (the hypothesis is that the filter improves the
carry currency, not that AUD beats cash). asset_class="fx" (2bp), 2006-07+.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYMS = ["FXA", "SPY"]


def make(n_months=10):
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []      # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if px["SPY"][i]:
                st["me"].append(px["SPY"][i])
            me = st["me"]
            on = len(me) < n_months or me[-1] > sum(me[-n_months:]) / n_months
            st["w"] = {"FXA": 1.0} if on else {}
        if st["w"] is None:
            return {"FXA": 1.0}
        return st["w"]
    return weights


weights = make(10)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-07-CARRYTREND", weights, SYMS, "FXA", start="2006-07-01",
                    asset_class="fx", trials=1, family="L-fx-carryguard",
                    variants={"SMA8": make(8), "SMA9": make(9), "SMA11": make(11), "SMA12": make(12)},
                    notes="FXA (AUD) only when SPY > 10-month SMA, else T-bills; monthly; bench FXA B&H; "
                          "2006-07+; lab original (DD-TREND x Brunnermeier-Nagel-Pedersen)")
    print(json.dumps(r, indent=1))
