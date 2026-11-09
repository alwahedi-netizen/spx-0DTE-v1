"""R-2026-11-09-VIXCORR — scripts the queued I-2026-11-08-VIXCORR (scored 70,
held behind its parent L-2026-11-07-CORRDUR on 2026-11-08).

SOURCES: Connolly, Stivers & Sun, "Stock Market Uncertainty and the
Stock-Bond Return Relation", JFQA 40(1), 2005
(https://ideas.repec.org/a/cup/jfinqa/v40y2005i01p161-194_00.html ; working
paper https://www.atlantafed.org/-/media/documents/research/publications/wp/2002/wp0203a.pdf):
when implied equity volatility (VIX) is high relative to its recent level,
the subsequent stock-bond correlation is lower and bond returns are higher
relative to stocks (flight to quality).

VARIES: L-2026-11-07-CORRDUR (FAIL, potential 3: TLT/IEF by trailing 63-day
realised SPY/TLT correlation; worked before 2018, lost after). Same
hypothesis (the stock-bond hedging regime decides how much duration to own)
with a FORWARD-LOOKING regime signal: implied equity vol instead of
backward-looking realised correlation.

RATIONALE (written before any run): a high VIX marks uncertainty regimes in
which investors flee to Treasuries; long duration (TLT) earns the
flight-to-quality bid and hedges, so extending from IEF to TLT should add
return when it matters most. Honest risk: 2022 — VIX elevated while long
bonds crashed (inflation shock); the paper predicts correlation, not bond
returns, and the duration bet doubles the rate risk.

RULE (fixed before any run; the ledger row's rule):
  * On the first trading day of each month, from the PREVIOUS close: if ^VIX
    > the mean of its last N = 252 closes (up to and incl. that close) ->
    hold TLT for the month, else IEF. Bought at that day's close.
  * Warm-up (fewer than N VIX closes seen): IEF.
Benchmark: IEF buy & hold. Costs 3bp (bonds). 2002-08+ (TLT/IEF inception
2002-07-30); VIX warm-up uses the same window, so positions differ from IEF
from ~2003-08.
Variants (lookback neighbours of the 252-day norm): 126, 189, 378, 504 days.
FAMILY "L-CORRDUR" (same hypothesis; the harness adds this run's 5 to
CORRDUR's lifetime count) -> trials = 10.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-09-VIXCORR"
SIG, LONG, BASE = "^VIX", "TLT", "IEF"


def make(n=252):
    st = {}

    def reset():
        st.clear()
        st.update(vix=[], hold=None)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
            v = px[SIG][0]
            if v:
                st["vix"].append(v)
            return {BASE: 1.0} if px[BASE][0] else {}
        if dates[i][:7] != dates[i - 1][:7]:          # first trading day of month
            hist = st["vix"]                           # closes up to i-1
            if len(hist) >= n:
                st["hold"] = LONG if hist[-1] > sum(hist[-n:]) / n else BASE
        v = px[SIG][i]                                 # today's close joins the
        if v:                                          # history for LATER decisions
            st["vix"].append(v)
        h = st["hold"] or BASE
        return {h: 1.0} if px[h][i] else {}
    return weights


weights = make(252)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [SIG, LONG, BASE], BASE, start="2002-08-01",
                    asset_class="bonds", trials=10, family="L-CORRDUR",
                    variants={f"N{m}": make(m) for m in (126, 189, 378, 504)},
                    notes="month-start, from the prior close: VIX above its 252-day mean -> TLT, "
                          "else IEF; bench IEF; 2002+; scripts I-2026-11-08-VIXCORR; family "
                          "L-CORRDUR (varies CORRDUR's realised-correlation signal)")
    print(json.dumps(r, indent=1))
