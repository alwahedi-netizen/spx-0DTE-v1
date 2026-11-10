"""L-2026-11-09-HEDGEUUP — trend-timed dollar hedge done with UUP (lab original,
RESEARCH.md §2b; queued 2026-11-09, scripted 2026-11-10; id kept).

VARIES: I-2026-11-08-HEDGEMOM (score 74, untested) — same 12-month rule, applied
at basket level and implemented with a LONG futures-based ETF instead of
shorting CurrencyShares trusts (the harness charges rf on gross > 1 and never
credits short proceeds, so HEDGEMOM's short hedge could not be measured).

INGREDIENTS:
  * Castro, Hamill, Harber, Harvey & Van Hemert, "Strategic currency hedging",
    Journal of Portfolio Management 2025 (summary:
    https://cxoadvisory.com/currency-trading/dynamic-exchange-rate-hedging-for-cross-currency-equity-holdings):
    leaving a currency unhedged only when it beat the home currency over the
    last 12 months beats static hedged/unhedged in 12 of 14 developed markets,
    1973-2024.
  * I-2026-11-08-HEDGEMOM (the ledger row this varies).

RATIONALE (written before any run): a US investor holding foreign equities is
short the dollar. Currency trends persist at the 12-month horizon (TSMOM,
Moskowitz-Ooi-Pedersen 2012), so the hedge (long USD vs the foreign basket)
should be on while the dollar trends up and off while it trends down. The
value of that decision is exactly the return of the hedge position in the
months it is on — measured here as a standalone UUP position. UUP holds long
USD-index futures plus T-bill collateral, so it earns the US-minus-basket rate
gap inside its price and its collateral yield replaces the T-bill cash it
displaces (no short-funding gap). Benchmark T-bills = "never hedge".

RULE (fixed before any run):
  * At each month-end close (last trading date of the month on the union
    calendar): hedge_on = DX-Y.NYB(t) > DX-Y.NYB at the month-end 12 months
    earlier (the 12th previous month-end close).
  * Next month: UUP 100% if hedge_on, else T-bills. Fewer than 12 prior
    month-ends, or no UUP price yet (UUP lists 2007-03-01) -> T-bills.
  * Variants (lookback +-25% / +-50%): 6, 9, 15, 18 months.
Benchmark: T-bills (None). asset_class="fx" (2bp). Start 2006-02-01 so the
12-month warm-up ends before UUP lists; positions from 2007-03.
Interpretation: active return vs T-bills = hedged-minus-unhedged for the
DXY-weighted part of a foreign-equity holder's currency exposure. MISMATCH on
the record: DXY is ~58% EUR / 14% JPY / 12% GBP / 9% CAD / 4% SEK / 4% CHF;
EAFE's currency mix is ~30% EUR / 22% JPY / 14% GBP / 10% CHF / 7% AUD.
FAMILY "fx-dollar-trend" (new) -> trials 5. Related but separate family: the
FX legs of DD-2026-11-TREND (per-pair 10-mo SMA / 12-1) — expect correlation.
EXPECTED WEAKNESS: ~1 decision a month on one series; 2008-2024 holds only a
few dollar cycles (2008, 2014-15, 2018, 2021-22), so t >= 3 is unlikely; judge
it by portfolio.marginal and by its drawdown profile as an overlay.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

DXY, UUP = "DX-Y.NYB", "UUP"
SYMS = [DXY, UUP]


def make(lookback_months=12):
    st = {"me": [], "w": {}}

    def weights(i, dates, px):
        if i == 0:
            st.update(me=[], w={})                 # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        v = px[DXY][i]
        if v:
            st["me"].append(v)
        me = st["me"]
        on = len(me) > lookback_months and me[-1] > me[-1 - lookback_months]
        st["w"] = {UUP: 1.0} if (on and px[UUP][i]) else {}
        return st["w"]
    return weights


weights = make(12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-09-HEDGEUUP", weights, SYMS, None, start="2006-02-01",
                    asset_class="fx", trials=5, family="fx-dollar-trend",
                    variants={"L6": make(6), "L9": make(9), "L15": make(15), "L18": make(18)},
                    notes="UUP 100% next month when DX-Y.NYB is above its level 12 month-ends earlier "
                          "(dollar hedge on for a foreign-equity holder), else T-bills; HEDGEMOM done "
                          "harness-correct with a long futures ETF")
    print(json.dumps(r, indent=1))
