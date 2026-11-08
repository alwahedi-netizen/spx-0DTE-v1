"""R-2026-11-08-GOLDAUTUMN — the autumn effect in gold (September + November).
Source: Dirk G. Baur, "The autumn effect of gold", Research in International
Business and Finance 27(1), 2013, pp. 1-11
(https://econpapers.repec.org/RePEc:eee:riibaf:v:27:y:2013:i:1:p:1-11):
over 1980-2010 September and November were the only months with significantly
positive gold returns (~+2.2% and ~+1.8% on average; CXO summary
https://cxoadvisory.com/calendar-effects/gold-seasonality-drivers), linked to
Indian wedding-season / Diwali jewellery demand and pre-winter hedging.
Later checks are mixed (Potrykus-Augustynowicz 2024, IJME:
https://reference-global.com/download/article/10.2478/ijme-2024-0011.pdf).

VARIES nothing in the ledger (first gold seasonality rule; the commodity
seasonality row I-2026-11-07-CMDSEASDVR is a regression model across 15
futures, not this two-month gold rule). KNOWLEDGE theme 4 (published calendar
effects decay) is the prior — this test is mostly OUT of sample: the paper's
data end in 2010, our development window is 2004-12 .. 2024-10 (about 14 of
20 autumns are post-sample).

RULE (fixed before any run): hold 100% GLD during September and November
(i.e. the weight decided at close i is GLD when the NEXT trading day is in
September or November), T-bills in every other month.
Benchmark: GLD buy & hold. Costs 5bp/unit turnover (4 trades a year).
Variants (neighbouring month sets): {Sep}, {Nov}, {Sep, Oct, Nov},
{Aug, Sep, Nov}, {Sep, Nov, Dec}.
trials = 17: Baur tested all 12 calendar months to find the two (12) + this
rule + 5 variants. Front-month GC=F is NOT used: its unadjusted rolls land
on the window edges and would fake returns.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb


def make(months=("09", "11")):
    months = set(months)
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        on = i + 1 < len(dates) and dates[i + 1][5:7] in months and bool(px["GLD"][i])
        return {"GLD": 1.0} if on else {}
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"sep": make(("09",)), "nov": make(("11",)), "sep-nov": make(("09", "10", "11")),
                "aug-sep-nov": make(("08", "09", "11")), "sep-nov-dec": make(("09", "11", "12"))}
    res = rb.evaluate("R-2026-11-08-GOLDAUTUMN", weights, ["GLD"], "GLD", start="2004-11-18",
                      cost_bps=5.0, asset_class="commodities", trials=17,
                      family="gold-autumn", variants=variants,
                      notes="hold GLD only in September and November (Baur 2013), else T-bills; bench GLD; "
                            "paper sample 1980-2010 -> 2011-2024 is post-publication; trials incl. 12 months searched")
    print(json.dumps(res, indent=1))
