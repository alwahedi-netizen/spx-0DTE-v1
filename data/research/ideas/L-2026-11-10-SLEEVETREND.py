"""L-2026-11-10-SLEEVETREND — original (RESEARCH.md §2b): a 10% Bitcoin sleeve
inside a 60/40 portfolio, held only while Bitcoin is above its 10-month
average (DD-2026-11-TREND's BTC gate); otherwise the sleeve sits in the 60/40.

Ingredients:
  * R-2026-11-10-BTCSLEEVE10H (Quantpedia 2025, Belobrad): the gated 10%
    BTC sleeve in 60/40, https://quantpedia.com/bitcoin-etfs-in-conventional-multi-asset-portfolios/
  * DD-2026-11-TREND (shortlist potential 5): the 10-month SMA gate. On BTC
    alone it cut the worst drop (-72% vs -83%) at ~0.8 trades/yr; slow
    anchors (BTC52WH -58%, BTCTRENDVOL -46%) cut more but none beat BTC
    on return (theme 16).
  * I-2026-11-07-BTCSLEEVE (Bitwise/WisdomTree static sleeve) and
    L-2026-11-07-RPCRYPTO (risk parity + trend-gated BTC; both rejected 11-07
    only for the calendar defect fixed 2026-11-09).
Varies R-2026-11-10-BTCSLEEVE10H: fixes its stated weakness — the 10-day-high
gate flips dozens of times a year and its own source found always-on beat
it (BTC's best days cluster right after crashes, when a fast gate is out).
A slow gate stays in through bull-market corrections and leaves only in
multi-month bears (2014-15, 2018, 2022).

Rationale (written before any run): theme 16 says crypto rules cut crashes
but cannot beat holding BTC; the owner-level question is different — does a
crash-cut BTC sleeve improve a traditional book? Inside 60/40 the sleeve's
return is the BTC premium and its cost is BTC's crash risk; a slow trend
gate removes most of the 2018/2022 sleeve losses (-80%+ each) while keeping
the long up-legs, so the book's Sharpe should rise vs both 60/40 and the
static sleeve, with low correlation of the active part to equities.
Counter-hypothesis: monthly signals miss the fast part of crashes (Mar 2020,
May 2021) and the 10% sleeve is too small to move a 60/40's Sharpe past
the 0.10 materiality bar; post-2020 BTC-equity coupling (CONTAGION) means
its crashes arrive with equity crashes anyway.

RULE (fixed before any run):
  * Universe VBINX (Vanguard Balanced Index = 60/40 US stocks/bonds) and
    BTC-USD. Risk-on = 90% VBINX + 10% BTC; risk-off = 100% VBINX.
    Benchmark = buy & hold VBINX (the risk-off book).
  * Decision on the FIRST US trading day (VBINX date) of each month, at the
    close, using BTC month-end closes (bars dated the last calendar day of
    each month) strictly before today: ON if the latest month-end close >
    the mean of the last 10 month-end closes (incl. it) — DD-TREND SMA10.
  * Switch only when the state changes; weights drift in between; the
    month's first trading day also rebalances back to the regime's target
    weights (one monthly rebalance, as a real sleeve would).
  * Warm-up (< 10 month-ends): risk-off = the benchmark (neutral).
  * Calendar: 7-day union; VBINX carried over weekends (harness fix
    2026-11-09) — it earns 0 on Sat/Sun and the Fri->Mon move on Monday.
Costs 25bp per unit turnover on every leg. Factor gate forced (ff5mom).
Variants: SMA 8 / 12 months; sleeve 5% / 20%.
trials: this run's 5 + BTCSLEEVE10H's 8 (same family, same question) = 13;
family btc-sleeve-6040 (the harness adds the lifetime count anyway).
If it passes development gates: ONE vault test for the family (its best
form chosen BEFORE opening the vault, with portfolio.marginal vs the book)."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

CORE, BTC = "VBINX", "BTC-USD"
_CAL = {}


def us_days():
    """Real VBINX pricing dates (a public calendar)."""
    if CORE not in _CAL:
        d, _ = rb.prices([CORE], "1990-01-01")
        _CAL[CORE] = set(d)
    return _CAL[CORE]


def set_us_days(ds):                     # smoke tests inject a calendar
    _CAL[CORE] = set(ds)


def drift(w, i, px):
    grow = {}
    for s, x in w.items():
        a, b = px[s][i - 1], px[s][i]
        grow[s] = x * (b / a) if (a and b) else x
    port = sum(grow.values()) + (1 - sum(w.values()))
    return {s: g / port for s, g in grow.items()} if port > 0 else {}


def make(months=10, sleeve=0.10):
    st = {}
    off = {CORE: 1.0}
    on = {CORE: 1.0 - sleeve, BTC: sleeve}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["on"], st["ends"], st["month"] = dict(off), False, [], None
        else:
            st["w"] = drift(st["w"], i, px)
            # bar i-1 is a month-end bar when bar i starts a new month
            if dates[i][:7] != dates[i - 1][:7] and px[BTC][i - 1]:
                st["ends"].append(px[BTC][i - 1])
        d = dates[i]
        if d in us_days() and d[:7] != st["month"]:
            st["month"] = d[:7]           # first US trading day of the month
            ends = st["ends"][-months:]
            if len(ends) == months:
                st["on"] = ends[-1] > sum(ends) / months
            st["w"] = dict(on if st["on"] else off)
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "sma8": make(months=8),
    "sma12": make(months=12),
    "sleeve5": make(sleeve=0.05),
    "sleeve20": make(sleeve=0.20),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-10-SLEEVETREND", weights, [CORE, BTC], bench=CORE, start="2014-09-17",
        asset_class="crypto", trials=13, family="btc-sleeve-6040", variants=VARIANTS,
        factors="ff5mom",
        notes="lab original: 90% VBINX + 10% BTC while BTC's last month-end close > its 10-month SMA "
              "(DD-TREND gate), else 100% VBINX; first US trading day of each month, BTC bars dated "
              "< today; monthly rebalance to target; bench VBINX; 25bp; factor regression uses "
              "weekdays only (weekend sleeve returns excluded there); vault sealed from 2024-11"),
        indent=1))
