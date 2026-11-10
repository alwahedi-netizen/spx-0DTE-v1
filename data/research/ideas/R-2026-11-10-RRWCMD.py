"""R-2026-11-10-RRWCMD — commodity-exporter currencies vs finished-goods
exporters (Ready, Roussanov & Ward 2017), the unconditional "trade-based carry".

SOURCE: Robert Ready, Nikolai Roussanov & Colin Ward, "Commodity Trade and the
Carry Trade: A Tale of Two Countries", Journal of Finance 72(6) 2017,
2629-2684 (NBER w19371, https://www.nber.org/papers/w19371): countries that
export basic commodities and import finished goods (Australia, New Zealand,
Canada, Norway) have high rates and risky currencies; exporters of finished
goods (Japan, Switzerland, Germany/euro, Sweden) have low rates and safe
currencies. Sorting on trade composition "generates a substantial spread in
average excess returns, which subsumes the unconditional (but not conditional)
carry trade". G10 table (1988-2012, futures, USD investor, % a year): JPY
-1.97, CHF -0.32, EUR 0.11, SEK 0.80, GBP 0.92, CAD 1.66, NOK 1.99, AUD 4.02,
NZD 4.06; a long-bottom-4 / short-top-4 portfolio is significant (their
Table A-1).

RATIONALE (written before any run): the premium is compensation for bearing
global productivity shocks that commodity producers pass to finished-goods
producers; it is structural (trade composition barely changes), so a static
holding needs no rate data and no timing.

LAB FORM (harness-correct, every leg a funded long):
  * Long leg: FXA (AUD) + FXC (CAD) CurrencyShares trusts, 25% each (deposit-
    backed: each earns its deposit rate minus 0.40%). NZD and NOK have no US
    ETF: dropped.
  * Short leg: UUP 50% — long USD-index futures (with T-bill collateral) = SHORT
    the DXY basket (EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF
    3.6%), which is dominated by the paper's finished-goods currencies (EUR,
    JPY, SEK, CHF). The futures price carries the US-minus-basket rate gap.
  * Net exposure ~ 0.5 x (AUD+CAD) - 0.5 x DXY basket, with USD ~ hedged out;
    gross 1, no cash (the harness neither charges nor credits rf), so the
    harness total return equals the economic total return.
  * Target weights are re-set daily (harness convention: returned weights are
    targets, so daily drift is traded back and charged at 2bp).
  * Variants (leg mixes, the only parameters): A50 = FXA 50% + UUP 50%; C50 =
    FXC 50% + UUP 50%; L60 = FXA/FXC 30% each + UUP 40%; L40 = 20% each + UUP
    60%.
Benchmark: T-bills. asset_class="fx" (2bp). Start 2007-03-01 (UUP lists
2007-03-01; FXA/FXC 2006-06).
MISMATCH on the record: CAD is in both legs (9.1% of DXY); GBP sits in the
short leg though the paper ranks it mid-table; NZD/NOK missing; sample
2007-24 is mostly after the paper's 1988-2012 window and includes the
2008 and 2014-15 commodity busts.
FAMILY "fx-cmdccy" (new) -> trials 5. Shares instruments with
L-2026-11-10-CMDDXY (the commodity-trend-timed version, family
L-fx-carryguard).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SYMS = ["FXA", "FXC", "UUP"]


def make(w_fxa=0.25, w_fxc=0.25, w_uup=0.50):
    target = {s: w for s, w in (("FXA", w_fxa), ("FXC", w_fxc), ("UUP", w_uup)) if w}
    st = {"w": {}}

    def weights(i, dates, px):
        if i == 0:
            st["w"] = {}                              # evaluate() re-simulates: start clean
        if not st["w"]:
            st["w"] = dict(target) if all(px[s][i] for s in target) else {}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-10-RRWCMD", weights, SYMS, None, start="2007-03-01",
                    asset_class="fx", trials=5, family="fx-cmdccy",
                    variants={"A50": make(0.5, 0, 0.5), "C50": make(0, 0.5, 0.5),
                              "L60": make(0.3, 0.3, 0.4), "L40": make(0.2, 0.2, 0.6)},
                    notes="Ready-Roussanov-Ward JF 2017 static trade-based carry: FXA 25% + FXC 25% "
                          "(commodity exporters, deposit-backed) + UUP 50% (short the DXY basket of "
                          "finished-goods exporters); constant target weights; bench T-bills")
    print(json.dumps(r, indent=1))
