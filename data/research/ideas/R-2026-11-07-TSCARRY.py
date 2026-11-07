"""R-2026-11-07-TSCARRY — time-series bond carry (term spread) on long Treasuries.
Source: Koijen, Moskowitz, Pedersen & Vrugt, "Carry", Journal of Financial
Economics 127(2), 2018: https://econpapers.repec.org/RePEc:eee:jfinec:v:127:y:2018:i:2:p:197-225
(bond carry = term spread + roll-down; carry predicts returns in time series
for global bonds and US Treasuries; summary:
https://www.cxoadvisory.com/big-ideas/unified-carry-trade-theory/).

VARIES R-2026-10-31-YCURVE (same observable — 10y minus 3m — but that row used
it to time STOCKS as a recession signal and failed: inversions come 1-2 years
before the crash). Here the economic channel is different: the slope IS the
bond's carry, i.e. the return a long-duration holder earns over cash if the
curve does not move. Negative carry means the long bond must rally just to
match bills. Whether that helps time BONDS (not stocks) is untested.

RULE (fixed before any run; KMPV sign-of-carry time-series form):
  on the first trading day of each month, using the PREVIOUS close's yields:
  if ^TNX - ^IRX > 0 (10-year yield above the 13-week bill), hold long
  Treasuries (VUSTX, Vanguard Long-Term Treasury) for the month; else T-bills.
Benchmark: VUSTX buy & hold (long history 1986+; TLT is 2002+). Costs 3bp.
Variants: threshold -0.50, -0.25, +0.25, +0.50 percentage points. trials = 5.
Expectation stated before the run: the curve was inverted in ~10-15% of
months, so the result may be a near-copy of the benchmark (the 0.10 Sharpe
materiality gate is the honest test of that)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYM = "VUSTX"


def make(th=0.0):
    st = {"w": None}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = None
            return {SYM: 1.0}
        if st["w"] is None or dates[i][:7] != dates[i - 1][:7]:
            tnx, irx = px["^TNX"][i - 1], px["^IRX"][i - 1]
            if tnx is not None and irx is not None:
                st["w"] = {SYM: 1.0} if tnx - irx > th else {}
        return st["w"] if st["w"] is not None else {SYM: 1.0}
    return weights


weights = make(0.0)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-TSCARRY", weights, [SYM, "^TNX", "^IRX"], SYM,
                    start="1986-06-02", asset_class="bonds", trials=5,
                    family="R-2026-11-07-TSCARRY",
                    variants={f"th{t:+.2f}": make(t) for t in (-0.5, -0.25, 0.25, 0.5)},
                    notes="VUSTX when 10y-3m > 0 at the prior close (monthly), else T-bills; "
                          "bench VUSTX; 1986+; varies YCURVE (same signal, bonds not stocks)")
    print(json.dumps(r, indent=1))
