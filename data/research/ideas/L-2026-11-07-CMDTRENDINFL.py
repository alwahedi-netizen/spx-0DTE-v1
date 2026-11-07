"""L-2026-11-07-CMDTRENDINFL — lab original (RESEARCH.md §2b): broad
commodities held only when (a) their own trend is up AND (b) market inflation
expectations are rising.

Ingredients (shortlist first):
  * DD-2026-11-TREND (potential 5, risk-reducer): the 10-month SMA cut the
    worst drop on almost every asset — but on DBC it did not add return.
  * Neville, Draaisma, Funnell, Harvey & Van Hemert, "The Best Strategies for
    Inflationary Times", JPM 2021 (https://www.man.com/insights/best-strategies-for-inflationary-times):
    commodities earned positive real returns in every US inflation surge and
    are poor holdings otherwise; Levine-Ooi-Richardson-Sasseville, FAJ 2018
    ("Commodities for the Long Run"): commodity returns across inflation
    states are driven by the spot component.
Rationale: the commodity premium is concentrated in rising-inflation states;
trend alone whipsaws in disinflationary chop (2011-2020). Requiring the
market's own inflation signal (TIPS beating nominal Treasuries = breakevens
widening) to agree should keep the trend filter's crash protection while
skipping the long disinflationary stretches when commodities bleed roll yield.

RULE (fixed before any run):
  at each month-end close:
    trend_on = DBC close > average of DBC's last 10 month-end closes
    infl_on  = TIP 126-day total return - IEF 126-day total return > 0
  hold 100% DBC next month if trend_on AND infl_on, else T-bills.
Benchmark: buy & hold DBC. Costs 5bp/unit turnover. Data: TIP 2004-01, IEF
2002, DBC 2006-02 -> first signal ~2006-12; development 2006-2024 includes
2008, 2014-16 and 2021-22 (vault from 2024-11 sealed).
trials = 7: this rule + 5 neighbour variants + the DBC SMA10 run already in
DD-2026-11-TREND. Variants: SMA 8/12 months; inflation lookback 63/189/252 days.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb


def make(sma=10, infl_lb=126):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["me"] = []
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        d = px["DBC"][i]
        if d:
            st["me"].append(d)
        me = st["me"]
        trend_on = bool(d) and len(me) >= sma and d > sum(me[-sma:]) / sma
        t, f = px["TIP"], px["IEF"]
        infl_on = (i >= infl_lb and t[i] and t[i - infl_lb] and f[i] and f[i - infl_lb]
                   and (t[i] / t[i - infl_lb]) - (f[i] / f[i - infl_lb]) > 0)
        st["w"] = {"DBC": 1.0} if (trend_on and infl_on) else {}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"sma8": make(8), "sma12": make(12), "infl63": make(10, 63),
                "infl189": make(10, 189), "infl252": make(10, 252)}
    res = rb.evaluate("L-2026-11-07-CMDTRENDINFL", weights, ["DBC", "TIP", "IEF"], "DBC", start="2004-01-01",
                      cost_bps=5.0, asset_class="commodities", trials=7,
                      family="L-2026-11-07-CMDTRENDINFL", variants=variants,
                      notes="DBC only when DBC > 10-month SMA AND TIP beat IEF over 126 days, else T-bills; "
                            "bench DBC; lab original (trend x inflation regime); development run, vault sealed")
    print(json.dumps(res, indent=1))
