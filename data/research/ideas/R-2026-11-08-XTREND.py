"""R-2026-11-08-XTREND — time-series trend on the 36 non-USD G10 crosses, netted
into USD legs (scripts the queued ledger row I-2026-11-07-XTREND).

SOURCE: Fulcrum Asset Management, "Beyond the dollar: diversifying FX exposure
in trend following" (2026,
https://fulcrumasset.com/insights/investment-insights/beyond-the-dollar-diversifying-fx-exposure-in-trend-following/):
USD-pair trend books are dominated by one common dollar factor (effective
breadth ~3.4 independent bets); running the same trend rule on the crosses
(x vs y, neither USD) raises effective breadth to ~7.6. Canon for the rule:
Moskowitz-Ooi-Pedersen (JFE 2012) 12-1 time-series momentum, inverse-vol sized.

VARIES: P-FX TSMOM and the FX legs of DD-2026-11-TREND (same 12-1 sign rule,
but on USD pairs, which carry the dollar factor; DD-TREND's FX legs were flat).
Here the dollar factor is stripped by construction: each cross is long one
foreign currency and short another, so the net USD exposure is whatever the
netting leaves, not a directional dollar bet.

RATIONALE (written before any run): currency trends are driven by persistent
relative macro/policy divergence (e.g. EUR vs CHF, AUD vs JPY). When the dollar
whipsaws, every USD-pair signal flips together; the crosses keep trending.

RULE (fixed before any run):
  * Currencies: EUR, GBP, AUD, NZD, JPY, CHF, CAD, SEK, NOK (Yahoo USD pairs).
  * Track each currency's USD price at every month-end close.
  * At each month-end, for each of the 36 crosses (x, y), x before y:
      cross = usdprice(x) / usdprice(y);
      s = sign( ln(cross at month-end t-1 / cross at month-end t-12) )   [12-1]
      vol = stdev of the cross's daily log returns over the last 63 bars;
      raw = s / vol  (inverse-vol risk budget).
    Net into currency legs: w[x] += raw, w[y] -= raw.
  * Scale so the sum of |w| over the 9 currencies = 1 (gross 1); map each
    currency weight onto its USD pair (USD-quoted pairs take the opposite
    sign). Hold one month. Crosses lacking 13 month-ends or 40 daily returns
    are skipped; fewer than 10 usable crosses -> flat (T-bills).
  * Variants (neighbouring lookbacks, same skip-1): 6, 9, 15, 18 months.
Benchmark: T-bills. asset_class="fx" (2bp). Spot pairs from 2003-12 (AUD
2006-05); signals from ~2005.
HONEST TRIALS: 6 DD-TREND FX runs (3 pairs x 2 rules) + this + 4 variants = 11.
HARNESS CAVEATS (on record before the run): (1) spot pairs earn no interest and
a long/short book is treated as funded, so the Sharpe vs T-bills is
conservative by ~rf/vol and the legs' net carry is missing (theme 12);
(2) Yahoo FX bars are stamped a day early in UK summer time — harmless for a
monthly rule, noted for the red team.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

LEGS = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "AUD": ("AUDUSD=X", 1),
        "NZD": ("NZDUSD=X", 1), "JPY": ("USDJPY=X", -1), "CHF": ("USDCHF=X", -1),
        "CAD": ("USDCAD=X", -1), "SEK": ("USDSEK=X", -1), "NOK": ("USDNOK=X", -1)}
CCYS = list(LEGS)
SYMS = [s for s, _ in LEGS.values()]
CROSSES = [(CCYS[a], CCYS[b]) for a in range(len(CCYS)) for b in range(a + 1, len(CCYS))]
VOL_BARS = 63


def usd_price(px, ccy, k):
    sym, sg = LEGS[ccy]
    v = px[sym][k]
    return None if not v else (v if sg > 0 else 1.0 / v)


def make(lookback_months=12):
    st = {"w": None, "me": []}          # me: list of {ccy: usd price} at month-ends

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["me"] = None, []      # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"] or {}
        st["me"].append({c: usd_price(px, c, i) for c in CCYS})
        me = st["me"]
        if len(me) < lookback_months + 1:
            st["w"] = {}
            return {}
        recent, old = me[-2], me[-1 - lookback_months]          # t-1 and t-L
        lo = max(0, i - VOL_BARS)
        w = {c: 0.0 for c in CCYS}
        used = 0
        for x, y in CROSSES:
            if not (recent[x] and recent[y] and old[x] and old[y]):
                continue
            s = math.log((recent[x] / recent[y]) / (old[x] / old[y]))
            if s == 0:
                continue
            rets, prev = [], None
            for k in range(lo, i + 1):
                px_x, px_y = usd_price(px, x, k), usd_price(px, y, k)
                cur = px_x / px_y if (px_x and px_y) else None
                if cur and prev:
                    rets.append(math.log(cur / prev))
                if cur:
                    prev = cur
            if len(rets) < 40:
                continue
            m = sum(rets) / len(rets)
            vol = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
            if vol <= 0:
                continue
            raw = (1.0 if s > 0 else -1.0) / vol
            w[x] += raw
            w[y] -= raw
            used += 1
        gross = sum(abs(v) for v in w.values())
        if used < 10 or gross == 0:
            st["w"] = {}
        else:
            st["w"] = {LEGS[c][0]: LEGS[c][1] * v / gross for c, v in w.items() if v}
        return st["w"]
    return weights


weights = make(12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-08-XTREND", weights, SYMS, None, start="2003-12-01",
                    asset_class="fx", trials=11, family="fx-xtrend",
                    variants={"L6": make(6), "L9": make(9), "L15": make(15), "L18": make(18)},
                    notes="12-1 sign trend on the 36 non-USD G10 crosses, inverse-63d-vol, netted to 9 USD "
                          "legs, gross 1, monthly; spot pairs (no interest: conservative ~rf/vol); "
                          "T-bills bench; trials 11 = 6 DD-TREND FX runs + 5 (Fulcrum 2026 x MOP 2012)")
    print(json.dumps(r, indent=1))
