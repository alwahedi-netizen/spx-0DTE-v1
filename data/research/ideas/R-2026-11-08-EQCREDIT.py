"""R-2026-11-08-EQCREDIT — scripts the queued I-2026-11-07-EQTRENDCREDIT
(scored 71, held by the 5-script cap on 2026-11-07), ON TRADEABLE ETFs.

SOURCES: Systematic Investor, "High Yield Bond Timing"
(https://systematicinvestor.github.io/High-Yield-Bond-Timing): time high
yield with the S&P 500's 10-month SMA; mechanism from Gebhardt, Hvidkjaer &
Swaminathan, "Stock and bond market interaction: does momentum spill over?"
JFE 75 (2005) (https://econbiz.de/Record/stock-and-bond-market-interaction-does-momentum-spill-over-gebhardt-william/10002637961):
past equity returns predict bond returns because default risk is repriced in
stocks first.

RATIONALE: equity prices update a firm's default risk faster than slowly
re-marked high-yield bonds; an equity downtrend is an early, LIQUID read of
a credit bear market. Different signal source from R-2026-11-07-HYTREND (the
HY fund's own 200-day trend), whose PASS the red team traced to stale
mutual-fund NAVs (KNOWLEDGE theme 9). Per theme 9 this test uses ETFs ONLY:
the signal is the S&P 500 index (liquid), the holdings are HYG / IEI.
Baseline to beat (red team, HYG/IEI 200-day own trend 2007+): Sharpe 0.61 vs
AGG 0.33, worst drop -14% vs -18%.

RULE (fixed before any run):
  * On the first trading day of each month, from the PREVIOUS close (the
    month-end): if ^GSPC's last month-end close > the mean of its last 10
    month-end closes (incl. that one), hold HYG for the month; else IEI.
    Bought at that day's close (one-day execution lag, no same-close trade).
  * Warm-up (first partial month): AGG.
Benchmark: AGG buy & hold (class benchmark for a credit/Treasury mix).
Costs 3bp. 2007-05+ (HYG inception 2007-04-11; IEI 2007-01).
Variants: SMA 6, 8, 12, 14 month-ends. trials = 5 (new family; the HYTREND
family's runs used a different signal).
History-only (NOT the verdict): the same rule on VWEHX/VFITX 1992+ can be
run by the red team for context; stale HY NAVs inflate it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-08-EQCREDIT"
SIG, RISK, SAFE, BENCH = "^GSPC", "HYG", "IEI", "AGG"


def make(n=10):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], hold=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
            return {BENCH: 1.0} if px[BENCH][0] else {}
        if dates[i][:7] != dates[i - 1][:7]:
            c = px[SIG][i - 1]
            if c:
                st["me"].append(c)
            if len(st["me"]) >= n:
                up = st["me"][-1] > sum(st["me"][-n:]) / n
                st["hold"] = RISK if up else SAFE
        h = st["hold"]
        if h and px[h][i]:
            return {h: 1.0}
        return {BENCH: 1.0} if px[BENCH][i] else {}
    return weights


weights = make(10)

if __name__ == "__main__":
    import json
    # ^GSPC from 2006-06 so the 10-month SMA is warm when HYG starts trading
    r = rb.evaluate(ID, weights, [SIG, RISK, SAFE], BENCH, start="2006-06-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={f"SMA{m}": make(m) for m in (6, 8, 12, 14)},
                    notes="month-start, from the prior month-end: S&P 500 above its 10-month SMA "
                          "-> HYG, else IEI; bench AGG; ETFs only (theme 9); scripts "
                          "I-2026-11-07-EQTRENDCREDIT")
    print(json.dumps(r, indent=1))
