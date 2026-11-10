"""R-2026-11-10-EMDOLLAR — scripts the queued I-2026-11-09-EMDOLLAR (scored
74, held back by the 5-script cap on 2026-11-09): own dollar EM sovereign
bonds while the dollar is falling.

SOURCES: Hofmann, Shim & Shin, "Bond risk premia and the exchange rate",
BIS WP 775 (https://www.bis.org/publ/work775.pdf), JMCB 52(S2) 2020
(https://econpapers.repec.org/RePEc:wly:jmoncb:v:52:y:2020:i:s2:p:497-520);
follow-up BIS WP 1031 (https://www.bis.org/publ/work1031.pdf). A stronger
dollar widens EM sovereign spreads and lifts EM bond risk premia, because
it tightens the financial conditions of dollar-funded investors. A weaker
dollar loosens them. The papers document the link and do not give a
trading rule, so the rule below is the lab's operationalisation, stated in
the 2026-11-09 ledger row before any run.

RATIONALE (written before any run): the dollar is a global
risk-appetite / funding-cost price. A dollar that has fallen for a quarter
signals easing conditions in which EM credit spreads compress. In a dollar
uptrend EM spreads widen, so we hold Treasuries instead. The signal is a
liquid ETF (UUP) and the holding is a tradeable ETF (EMB), so theme 9
(stale-NAV edges) does not apply.

RULE (fixed before any run; identical to the 2026-11-09 ledger row):
  * On the first trading day of each month, from the PREVIOUS close (the
    month-end): if UUP's return over the last 3 month-ends is < 0, hold EMB
    for the month, else IEF. Bought at that day's close.
  * Warm-up (fewer than 4 UUP month-ends, or the chosen ETF has no price
    yet — EMB starts 2007-12-19): AGG.
Benchmark: AGG buy & hold. Costs 3bp. Start 2007-09-01 so UUP's month-ends
are warm when EMB lists; positions in EMB possible from 2008-01 (includes
2008, 2013 taper, 2015, 2018, 2020, 2022).
Variants: UUP lookback 1, 2, 4, 6 months. trials = 5 (new family).
Follow-ups pre-registered in the ledger: L-2026-11-09-EMDOLTREND (adds the
S&P 10-mo trend), I-2026-11-10-EMLCDOLLAR (local-currency EMLC, the
instrument the BIS papers actually study).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-10-EMDOLLAR"
SIG, RISK, SAFE, BENCH = "UUP", "EMB", "IEF", "AGG"


def make(n=3):
    st = {}

    def reset():
        st.clear()
        st.update(me=[], hold=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        elif dates[i][:7] != dates[i - 1][:7]:          # month-end = close i-1
            c = px[SIG][i - 1]
            if c:
                st["me"].append(c)
            if len(st["me"]) > n:
                st["hold"] = RISK if st["me"][-1] / st["me"][-1 - n] - 1 < 0 else SAFE
        h = st["hold"]
        if h and px[h][i]:
            return {h: 1.0}
        return {BENCH: 1.0} if px[BENCH][i] else {}
    return weights


weights = make(3)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [SIG, RISK, SAFE], BENCH, start="2007-09-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={f"LB{m}": make(m) for m in (1, 2, 4, 6)},
                    notes="month-start, from the prior month-end: UUP 3-month return < 0 -> EMB, "
                          "else IEF; warm-up AGG; bench AGG; 2007-09+; Hofmann-Shim-Shin (BIS WP "
                          "775 / JMCB 2020); scripts I-2026-11-09-EMDOLLAR")
    print(json.dumps(r, indent=1))
