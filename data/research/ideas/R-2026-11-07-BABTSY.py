"""R-2026-11-07-BABTSY — betting against beta in Treasuries (lever the short end).
Sources: Frazzini & Pedersen, "Betting Against Beta", JFE 2014 (Treasury BAB:
long levered short maturities, short de-levered long maturities; Sharpe falls
almost monotonically with maturity): https://conference.nber.org/confer/2010/BEf10/Frazzini.pdf
and the independent Treasury replication by Durham, NY Fed Staff Report 708
(BAB in Treasuries survives hedging equity covariance):
https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr708.pdf

Rationale: leverage-constrained investors who want more return buy long
maturities instead of levering short ones, bidding up long bonds; short
maturities therefore earn more per unit of risk. An investor who CAN lever
(cheaply, e.g. 2-year Treasury futures, financing ~ T-bill) should own the
short end at the long end's risk instead.

RULE (fixed before any run; long-only, Schwab-implementable form of the BAB
long leg vs the intermediate benchmark):
  on the first trading day of each month, using daily returns through the
  previous close: L = vol252(VFITX) / vol252(VFISX), capped at 4x; hold
  L x VFISX (Vanguard Short-Term Treasury) for the month, financed at the
  T-bill rate by the harness (gross exposure above 1 pays T-bills).
  Warm-up (first 252 days): hold the benchmark.
Benchmark: VFITX (Vanguard Intermediate-Term Treasury; IEF proxy, 1991+).
Costs 3bp/unit turnover. The question: same risk, more return (higher Sharpe)?
Variants: vol window 126 / 189 / 378 / 504 days. trials = 5.
Caveat (stated now): T-bill financing is the futures-implementation cost; a
margin loan at Schwab costs far more and would kill it — report both ways in
the ledger. The held weight is re-set daily to L (tiny drift turnover)."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SHORT, BENCH, CAP = "VFISX", "VFITX", 4.0


def _vol(col, i, n):
    c = col[i - n - 1:i]                     # closes i-n-1 .. i-1
    r = [b / a - 1 for a, b in zip(c, c[1:]) if a and b]
    if len(r) < int(0.9 * n):
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def make(n=252):
    st = {"w": None}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = None
        if i > n + 1 and (st["w"] is None or dates[i][:7] != dates[i - 1][:7]):
            vs, vf = _vol(px[SHORT], i, n), _vol(px[BENCH], i, n)
            if vs and vf:
                st["w"] = {SHORT: min(CAP, vf / vs)}
        return st["w"] if st["w"] is not None else {BENCH: 1.0}
    return weights


weights = make(252)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-BABTSY", weights, [SHORT, BENCH], BENCH, start="1991-11-01",
                    asset_class="bonds", trials=5, family="R-2026-11-07-BABTSY",
                    variants={f"vol{n}": make(n) for n in (126, 189, 378, 504)},
                    notes="VFISX levered to VFITX's 252-day vol (cap 4x, T-bill financing), "
                          "monthly; bench VFITX; 1991+")
    print(json.dumps(r, indent=1))
