"""R-2026-11-09-LOWVOLSF — the low-volatility anomaly, long-only, on the
point-in-time S&P 500 (survivorship-free). RETEST of G-STK-SUITE "LOWVOL".

G-STK-SUITE's LOWVOL rule failed on Yahoo data (today's tickers only:
survivorship-biased, theme 6). Sharadar now lets us test it honestly.
Sources: Blitz & van Vliet (2007) "The Volatility Effect: Lower Risk Without
Lower Return", J. Portfolio Management 34(1) 102-113; Ang, Hodrick, Xing &
Zhang (2006) J. Finance 61(1). Practitioner point-in-time replication on the
same index with the exact rule below: Quanter Lab 2026-08-09 "Two ways to say
calm: low beta and low volatility are not the same trade"
(https://quanterlab.com/research/two-ways-to-say-calm-low-beta-and-low-volatility-are-not-the-same-trade-and-the-)
— 20 lowest-volatility S&P 500 names: 9.2%/yr total return vs RSP 9.9%,
volatility 14.4% vs 20.7%, worst drop -39% vs -62% (2006-25, gross).
EXPECT: a risk reducer (lower drop, similar Sharpe or better), not a return
engine. Its value to the lab is as an ingredient: the first DEFENSIVE stock
block (everything on the stock shortlist so far is value/quality/momentum).

RATIONALE (fixed before any run): leverage-constrained and benchmarked
investors (and lottery-seekers) bid up volatile stocks and neglect boring
ones, so low-volatility stocks earn about the market's return with far less
risk (Frazzini-Pedersen; Baker-Bradley-Wurgler). The FF5+Mom regression has
no low-vol factor, but RMW/CMA loadings usually absorb much of it (theme 8).

RULE (fixed before any run; Quanter Lab's published settings):
  * Universe: point-in-time S&P 500 members on each decision day; Sharadar
    survivorship-free prices; only names priced on the decision day.
  * Decision days: the last close of March, June, September and December.
  * Volatility = sample stdev of daily log returns over the last 252 closes
    (at least 95% of the 252 returns present), annualisation irrelevant.
  * Hold the 20 LOWEST-volatility names, equal weight, to the next quarter
    end; weights drift with prices between decisions.
  * Before the first decision with 252 closes of history: hold SPY.
  * Variants (robustness gate): 15 and 30 names; 126- and 504-day windows.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha.
    family "low-volatility" (new as a family); trials passed 6 = 1 + 4
    variants + the 1 G-STK-SUITE LOWVOL run on Yahoo. R-2026-11-07-CONSERV
    used a low-vol screen inside its own family ("conservative-formula").
Delisted names return 0 from their last price (no delisting return) — noted.
Uses only Sharadar prices (the same per-ticker query as every other Sharadar
script), so it adds no fundamentals calls.
"""
import importlib.util
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("assetgrow", Path(__file__).with_name("R-2026-11-08-ASSETGROW.py"))
ag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ag)

ID = "R-2026-11-09-LOWVOLSF"
START = "2000-01-01"
BENCH = "SPY"
QUARTER_ENDS = {"03", "06", "09", "12"}


def vol(col, i, lb):
    """Stdev of daily log returns over the last `lb` closes up to i, or None."""
    if i < lb:
        return None
    w = col[i - lb:i + 1]
    r = [math.log(b / a) for a, b in zip(w, w[1:]) if a and b]
    if len(r) < 0.95 * lb:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def make_weights(n_hold=20, lb=252):
    st = {}

    def select(day, i, px):
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None:
                continue
            v = vol(px[t], i, lb)
            if v:
                scored.append((v, t))
        if len(scored) < 4 * n_hold:
            return None
        scored.sort()                               # lowest volatility first
        pick = [t for _, t in scored[:n_hold]]
        return {t: 1.0 / len(pick) for t in pick}

    def weights(i, dates, px):
        if i == 0:
            st.clear()                              # fresh state for every simulation
        if (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
                and dates[i][5:7] in QUARTER_ENDS):
            w = select(dates[i], i, px)
            if w:
                st["w"] = w
                st["base"] = {t: px[t][i] for t in w}
                st["last"] = dict(st["base"])
                return dict(w)
        if "w" not in st:
            return {BENCH: 1.0}
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t]
        tot = sum(v.values())
        return {t: x / tot for t, x in v.items()} if tot > 0 else {}
    return weights


weights = make_weights()
VARIANTS = {"n15": make_weights(15), "n30": make_weights(30),
            "lb126": make_weights(lb=126), "lb504": make_weights(lb=504)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=6,
        family="low-volatility", variants=VARIANTS, source="sharadar",
        notes=("Retest of G-STK-SUITE LOWVOL on survivorship-free data: 20 lowest 252-day-volatility "
               "names of the point-in-time S&P 500, equal weight, quarterly, drift between; SPY warm-up; "
               "variants 15/30 names, 126/504-day windows; Blitz-van Vliet 2007; Quanter Lab 2026-08-09"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
