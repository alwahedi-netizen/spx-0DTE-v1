"""R-2026-11-07-OILSPY — lagged oil-price changes predict lower stock returns
(Driesprong, Jacobsen & Maat, "Striking oil: Another puzzle?", Journal of
Financial Economics 89(2), 2008:
https://ideas.repec.org/a/eee/jfinec/v89y2008i2p307-327.html).

Rationale: investors under-react to the information in oil prices about
future earnings (slow diffusion across sectors), so a rise in oil this month
predicts lower equity excess returns next month; the paper shows this in 18
developed and emerging markets and that it is not a time-varying risk premium
(oil rises predict NEGATIVE excess returns). Out-of-sample decay since
publication is likely (KNOWLEDGE.md theme 4) — this test checks exactly that.

RULE (fixed before any run; the paper's economic-significance design —
predict with the regression, hold stocks only when the forecast beats cash):
  at each month-end close m:
    oil_m = CL=F month-end close / previous month-end close - 1
    ex_m  = SPY month return - ^IRX(prev month-end)/100/12   (excess over bills)
    regress ex_{t+1} on oil_t over ALL completed months so far (expanding
    window, needs >= 60 pairs); forecast = a + b x oil_m
    hold SPY next month if forecast > 0, else T-bills
Benchmark: SPY. Costs 5bp/unit turnover. CL=F (front-month continuous; the
roll gaps add noise to oil_m, they are not P&L) from 2000-09, so the first
forecast is ~2005-09; development data 2005-2024 includes 2008 and 2020.
trials = 8: the paper reports several lag/window specifications (we count 3)
plus this run and 4 window variants (36/48/84 months expanding, 120 rolling).
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb


def _last(col, i):
    for k in range(i, max(i - 6, -1), -1):
        if col[k]:
            return col[k]
    return None


def make(min_n=60, rolling=None):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st.update(prev=None, oil=[], ex=[], w={})
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        o, s, b = _last(px["CL=F"], i), _last(px["SPY"], i), _last(px["^IRX"], i)
        prev = st["prev"]
        st["prev"] = (o, s, b)
        if prev is None or None in prev or None in (o, s):
            return st["w"]
        oil = o / prev[0] - 1
        ex = s / prev[1] - 1 - (prev[2] or 0.0) / 100 / 12
        if st["oil"]:
            st["ex"].append(ex)            # pairs (oil_{t-1}, ex_t)
        st["oil"].append(oil)
        xs, ys = st["oil"][:-1], st["ex"]
        if rolling:
            xs, ys = xs[-rolling:], ys[-rolling:]
        if len(ys) < min_n:
            st["w"] = {"SPY": 1.0}         # before the model exists: buy & hold
            return st["w"]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        bb = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
        fc = (my - bb * mx) + bb * oil
        st["w"] = {"SPY": 1.0} if fc > 0 else {}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"min36": make(36), "min48": make(48), "min84": make(84), "roll120": make(60, 120)}
    res = rb.evaluate("R-2026-11-07-OILSPY", weights, ["CL=F", "SPY", "^IRX"], "SPY", start="2000-09-01",
                      cost_bps=5.0, asset_class="futures", trials=8,
                      family="oil-predicts-stocks", variants=variants,
                      notes="SPY next month only if expanding-regression forecast (excess return on lagged "
                            "1-month oil change, >=60 months) > 0, else T-bills; bench SPY; buy & hold until "
                            "the model has 60 months (~2005-09)")
    print(json.dumps(res, indent=1))
