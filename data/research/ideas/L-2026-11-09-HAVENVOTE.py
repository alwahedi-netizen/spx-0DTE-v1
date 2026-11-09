"""L-2026-11-09-HAVENVOTE — yen + franc sized by a 3-switch vote (lab original,
RESEARCH.md §2b: combination of three shortlist switches).

VARIES: L-2026-11-07-SAFEHAVEN, L-2026-11-08-HAVENRATES, L-2026-11-08-HAVENVOL
(all potential 4, all FAIL on DSR/t only). Each used ONE on/off switch and
held FXY+FXF at 100% or 0%. HAVENVOL's learnings row asked to combine the
switches; this sizes the sleeve by how many of the three agree.

INGREDIENTS:
  * Ranaldo & Soderlind, "Safe Haven Currencies", Review of Finance 14(3),
    2010 (https://econpapers.repec.org/RePEc:oup:revfin:v:14:y:2010:i:3:p:385-407):
    JPY and CHF appreciate when equities fall, bond yields fall and FX
    volatility rises — three separate conditions in their regressions.
  * Equity trend switch: DD-2026-11-TREND (Faber 10-month SMA).
  * Falling-yield switch: HAVENRATES's IEF 10-month SMA leg (yen/franc gain
    when the US rate differential narrows).
  * FX-stress switch: Menkhoff, Sarno, Schmeling & Schrimpf, JF 2012 global FX
    volatility (as HAVENVOL).

RATIONALE (written before any run): Ranaldo-Soderlind's haven returns load on
three different state variables. Each single switch fires falsely in its own
kind of month (equity bear with rising yields 2022; bond rallies in calm
years; FX-vol spikes caused by yen weakness itself). An average of three
partly independent noisy signals has less noise than any one of them, steps
exposure in thirds (fewer full round trips), and is fully invested only when
all three crisis conditions agree. No new parameter is introduced: each
switch keeps the lookback it was tested with.

RULE (fixed before any run):
  * At each month-end close (values = last price within 5 bars):
      s1 = SPY  < mean of its last 10 month-end closes   (equity bear)
      s2 = IEF  > mean of its last 10 month-end closes   (falling yields)
      s3 = V_t  > mean(V_{t-12} .. V_{t-1})               (FX stress), where V
           = monthly mean of the daily cross-pair mean |ln return| of the 9
           G10 USD pairs (ignore |r| > 10% as bad ticks), as in HAVENVOL.
  * Next month hold FXY and FXF at (s1+s2+s3)/6 each (total 0, 1/3, 2/3 or
    1); the rest in T-bills. A switch without enough history counts as 0;
    FXY or FXF missing -> T-bills.
  * Variants (all lookbacks scaled together, +-25% / +-50%): (SMA 8, norm 9),
    (SMA 12, norm 15), (SMA 5, norm 6), (SMA 15, norm 18).
Instruments: FXY, FXF (CurrencyShares, deposit-backed: they earn the yen/franc
deposit rate minus the 0.40% fee, so the harness return is the real one;
spot pairs would earn no interest). Signals: SPY, IEF, Yahoo spot pairs.
Benchmark T-bills. asset_class="fx" (2bp). Start 2005-01 (positions from
2007-02 when FXY lists; FXF 2006-06).
FAMILY "L-fx-safehaven" (SAFEHAVEN 5 + HAVENRATES 5 + HAVENVOL 5) -> trials 20.
OVER-FIT NOTE: every ingredient was chosen after seeing its own result; the
shared family charges the attempt and a vault test would be needed.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

HAVENS = ["FXY", "FXF"]
PAIRS = ["EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X", "USDJPY=X",
         "USDCHF=X", "USDCAD=X", "USDSEK=X", "USDNOK=X"]
SYMS = HAVENS + ["SPY", "IEF"] + PAIRS
BAD_TICK = 0.10


def _last(px, sym, i, back=5):
    for k in range(i, max(-1, i - back), -1):
        v = px[sym][k]
        if v:
            return v
    return None


def make(sma=10, norm=12):
    st = {"w": None, "day": [], "months": [], "last": {}, "spy": [], "ief": []}

    def weights(i, dates, px):
        if i == 0:
            st.update(w=None, day=[], months=[], last={}, spy=[], ief=[])
        absr = []
        for p in PAIRS:
            v = px[p][i]
            prev = st["last"].get(p)
            if v and prev:
                r = abs(math.log(v / prev))
                if r <= BAD_TICK:
                    absr.append(r)
            if v:
                st["last"][p] = v
        if len(absr) >= 5:
            st["day"].append(sum(absr) / len(absr))
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"] or {}
        if st["day"]:
            st["months"].append(sum(st["day"]) / len(st["day"]))
        st["day"] = []
        st["spy"].append(_last(px, "SPY", i))
        st["ief"].append(_last(px, "IEF", i))

        def sma_state(series, below):
            xs = series[-sma:]
            if len(xs) < sma or any(x is None for x in xs):
                return 0
            m = sum(xs) / sma
            return int(xs[-1] < m) if below else int(xs[-1] > m)

        s1 = sma_state(st["spy"], below=True)
        s2 = sma_state(st["ief"], below=False)
        m = st["months"]
        s3 = int(len(m) >= norm + 1 and m[-1] > sum(m[-1 - norm:-1]) / norm)
        votes = s1 + s2 + s3
        if votes and all(px[h][i] for h in HAVENS):
            st["w"] = {h: votes / 3.0 / len(HAVENS) for h in HAVENS}
        else:
            st["w"] = {}
        return st["w"]
    return weights


weights = make(10, 12)

if __name__ == "__main__":
    import json
    r = rb.evaluate("L-2026-11-09-HAVENVOTE", weights, SYMS, None, start="2005-01-01",
                    asset_class="fx", trials=20, family="L-fx-safehaven",
                    variants={"S8N9": make(8, 9), "S12N15": make(12, 15),
                              "S5N6": make(5, 6), "S15N18": make(15, 18)},
                    notes="FXY+FXF sized by votes/3 of: SPY<SMA10, IEF>SMA10, global FX vol > 12-mo norm "
                          "(month-end); else T-bills; lab original combining SAFEHAVEN/HAVENRATES/HAVENVOL")
    print(json.dumps(r, indent=1))
