"""R-2026-11-09-UEP — uncovered equity parity: fade the currencies of stock
markets that just beat the US (promotes ledger row I-2026-11-08-UEP).

SOURCES:
  * Hau & Rey, "Exchange Rates, Equity Prices, and Capital Flows", Review of
    Financial Studies 19(1), 2006 (NBER w9398, https://www.nber.org/papers/w9398):
    17 OECD countries; when a foreign equity market outperforms the US, its
    currency tends to DEPRECIATE vs USD (investors rebalance / re-hedge back to
    target weights, selling the foreign currency).
  * Curcuru, Thomas, Warnock & Wongswan, "Uncovered Equity Parity and
    Rebalancing in International Portfolios", JIMF 2014 (Fed IFDP,
    https://www.federalreserve.gov/econres/ifdp/uncovered-equity-parity-and-rebalancing-in-international-portfolios.htm):
    US investors' flows leave foreign markets that have just outperformed.
  * Counter-evidence on the record BEFORE the run: Cenedese et al. (BoE 2015)
    find no UEP relation in a longer sample; Phylaktis & Yamani (JEF 2025,
    doi:10.1016/j.jempfin.2025.101641) find the equity-differential signal
    tradeable only in EM currencies, "nothing tradable" in developed ones.

RATIONALE (written before any run): global portfolios are rebalanced toward
fixed country weights and hedge ratios. After a foreign market outperforms,
its weight is too high; selling it (and its currency) is a predictable flow
that should weigh on that currency over the following month. The FX book holds
no equity-flow driver yet (carry, value, momentum, FOMC are rate/price based).

RULE (fixed before any run; the ledger row's lab operationalisation, the
sources test a relation, not a trading rule):
  * Universe (currency: pair, local PRICE index): EUR: EURUSD=X, ^STOXX50E
    (2007-03+); GBP: GBPUSD=X, ^FTSE; AUD: AUDUSD=X, ^AXJO; JPY: USDJPY=X,
    ^N225; CHF: USDCHF=X, ^SSMI; CAD: USDCAD=X, ^GSPTSE; SEK: USDSEK=X, ^OMX
    (2008-11+). US: ^GSPC. NZD dropped (^NZ50 is a GROSS total-return index:
    a ~0.3%/month dividend bias would always rank it as an outperformer); NOK
    dropped (no Yahoo index history); ^GDAXI not used for EUR for the same
    total-return reason.
  * At each month-end close: rel_c = ln(index_c(t)/index_c(t-F)) -
    ln(GSPC(t)/GSPC(t-F)) on month-end levels (last value within 5 bars), F = 1.
  * Short (vs USD) the N = 3 currencies with the highest rel_c, long the N = 3
    with the lowest, 1/(2N) each (gross 1); hold one month. USD-quoted pairs
    take the opposite sign. Fewer than 2N+1 currencies with both an index and
    a pair -> T-bills.
  * Variants: formation F = 2, 3 months; N = 1, 2 (with 7 currencies N = 4 is
    impossible).
Benchmark: T-bills. asset_class="fx" (2bp). Spot pairs from 2003-12; the
primary (N = 3) needs all 7 currencies, so its positions start 2008-12 (^OMX
lists 2008-11) and include the 2008-09 crash tail only from December; the N = 1
/ N = 2 variants need 3 / 5 names and start 2004-01 / 2006-06.
FAMILY "fx-uep" (new; I-2026-11-07-MEHEDGE shares the channel but was never
run) -> trials 5.
HARNESS CAVEAT: spot pairs earn no interest; the long/short book is roughly
dollar-neutral and treated as funded, so it misses the legs' net carry and is
conservative by ~rf/vol. Spot is what the sources measure (exchange-rate
returns, not excess returns), so spot is the right instrument for the claim.
DATA NOTES: index closes are local (Tokyo/Sydney before London/NY); monthly
returns make the few-hour mismatch immaterial. Yahoo FX UK-summer-time label
shift only moves which bar is the month's last by one day.
"""
import sys
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

LEGS = {"EUR": ("EURUSD=X", 1, "^STOXX50E"), "GBP": ("GBPUSD=X", 1, "^FTSE"),
        "AUD": ("AUDUSD=X", 1, "^AXJO"), "JPY": ("USDJPY=X", -1, "^N225"),
        "CHF": ("USDCHF=X", -1, "^SSMI"), "CAD": ("USDCAD=X", -1, "^GSPTSE"),
        "SEK": ("USDSEK=X", -1, "^OMX")}
US = "^GSPC"
SYMS = [p for p, _, _ in LEGS.values()] + [x for _, _, x in LEGS.values()] + [US]


def _last(px, sym, i, back=5):
    for k in range(i, max(-1, i - back), -1):
        v = px[sym][k]
        if v:
            return v
    return None


def make(formation=1, per_side=3):
    st = {"w": None, "me": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []        # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"] or {}
        snap = {s: _last(px, s, i) for s in [x for _, _, x in LEGS.values()] + [US]}
        st["me"].append(snap)
        me = st["me"]
        if len(me) < formation + 1:
            st["w"] = {}
            return {}
        now, then = me[-1], me[-1 - formation]
        if not (now[US] and then[US]):
            st["w"] = {}
            return {}
        us_r = math.log(now[US] / then[US])
        rel = {}
        for c, (pair, sg, idx) in LEGS.items():
            if now[idx] and then[idx] and px[pair][i]:
                rel[c] = math.log(now[idx] / then[idx]) - us_r
        if len(rel) < 2 * per_side + 1:
            st["w"] = {}
            return {}
        ranked = sorted(rel, key=lambda c: rel[c])          # low (underperformer) first
        longs, shorts = ranked[:per_side], ranked[-per_side:]
        w = {}
        for c in longs:
            w[LEGS[c][0]] = LEGS[c][1] / (2 * per_side)       # long the currency vs USD
        for c in shorts:
            w[LEGS[c][0]] = -LEGS[c][1] / (2 * per_side)      # short the currency vs USD
        st["w"] = w
        return w
    return weights


weights = make(1, 3)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-09-UEP", weights, SYMS, None, start="2003-12-01",
                    asset_class="fx", trials=5, family="fx-uep",
                    variants={"F2": make(2, 3), "F3": make(3, 3), "N1": make(1, 1), "N2": make(1, 2)},
                    notes="Hau-Rey UEP: month-end, short the 3 currencies whose local price index beat the "
                          "S&P 500 most over 1 month, long the 3 that lagged most (7 G10 currencies, 1/6 each); "
                          "spot pairs; T-bills bench; family fx-uep")
    print(json.dumps(r, indent=1))
