"""R-2026-11-10-BTCSLEEVE10H — a 10% Bitcoin sleeve inside a 60/40 portfolio,
switched ON only while Bitcoin is at a 10-day closing high (Quantpedia 2025).

Source: D. Belobrad (Quantpedia), "Bitcoin ETFs in Conventional Multi-Asset
Portfolios", 2025-09-02,
https://quantpedia.com/bitcoin-etfs-in-conventional-multi-asset-portfolios/
Rule (iteration 1): risk-on when BITO's daily close is a new 10-day high ->
54% SPY / 36% IEF / 10% BITO; else 60% SPY / 40% IEF; switch whenever the
state changes. Published (2018-01 -> 2025-05, cash at 0%, no costs):
CAR 10.54% / vol 12.50% / Sharpe 0.84 vs 60/40 8.54% / 11.96% / 0.71 — BUT
the same article reports the ALWAYS-on 10% sleeve at Sharpe 0.93, above the
switching version: the signal itself did not help in iterations 1-2.
(Iteration 3, SPY/GLD/BITO, was tuned in-sample; the author says so — not used.)
Signal canon: Padysak-Vojtko MAX10 (R-2026-11-08-BTCMAXMIN, FAIL on BTC alone).

Varies: R-2026-11-08-BTCMAXMIN (same 10-day-high signal, but there it timed
100% BTC daily and died on ~124 trades/yr) and I-2026-11-07-BTCSLEEVE
(static 1-5% BTC in 60/40, rejected 11-07 only for the calendar defect fixed
2026-11-09). Why the difference matters (theme 16): the signal is judged
where the lead says crypto belongs — as a small sleeve inside a portfolio —
and the sleeve's turnover is 10% of the book, so costs are ~1/10th.

Rationale (written before any run): BTC adds return and some diversification
to a 60/40 but brings fat-tailed crashes; holding it only while it trends
(new 10-day high) should keep the up-legs and step aside in sustained
declines, so the book captures BTC's positive skew with a smaller drawdown.
Counter-hypothesis (the source's own table): always-on beats switching,
because BTC's best days cluster right after crashes when the gate is off.

IMPLEMENTATION (fixed before any run):
  * The 60/40 leg is VBINX (Vanguard Balanced Index: 60% US total market /
    40% US aggregate bonds, 1992->), so risk-on = 90% VBINX + 10% BTC-USD
    and risk-off = 100% VBINX. This equals the source's 54/36/10 vs 60/40
    and isolates the sleeve exactly: the active return is 10% x (BTC -
    VBINX) on risk-on days. Benchmark = buy & hold VBINX (the risk-off
    book). NOT BTC-USD: a 90%-traditional portfolio judged against BTC would
    be meaningless (same reasoning as R-2026-11-09-BTCQQQGATE's QQQ bench).
    Source legs differ (SPY/IEF vs total market/Agg) — stated.
  * Decisions only on US trading days (VBINX prices) at the close, using
    BTC-USD bars dated STRICTLY BEFORE today: bar D closes at 00:00 UTC
    D+1, after the US close on D (look-ahead guard as in BTCQQQGATE).
    ON if BTC's last known close >= max of the last 10 BTC daily closes
    (incl. itself). The source uses BITO's 10 trading days; we use 10 BTC
    calendar days (the Padysak MAX10 convention it cites).
  * Switch to the regime's target weights when the state changes; weights
    drift in between (no other rebalancing).
  * Warm-up (fewer than 10 BTC closes): risk-off = the benchmark (neutral).
  * Calendar: BTC-USD makes it 7-day; VBINX's price is carried over
    weekends (harness fix 2026-11-09), so it earns 0 then and the whole
    Friday->Monday move on Monday — no lost weekend.
Costs: 25bp per unit turnover on every leg (crypto floor; a switch moves
0.2 of the book -> 5bp). Factor gate forced (ff5mom): it is 90% equity/bond
beta, so the active part must not be a known factor in disguise.
Variants: 5-day / 20-day high; sleeve 5% / 20%.
trials: 1 + 4 + the source's 3 iterations (same question, same sample) = 8;
new family btc-sleeve-6040 (shared with L-2026-11-10-SLEEVETREND).
Tradeable at Schwab: VBINX (or AOR / SPY+IEF) + IBIT from 2024-01; before
2024 the BTC leg is spot (GBTC/BITO proxies differ)."""
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


def make(n=10, sleeve=0.10):
    st = {}
    off = {CORE: 1.0}
    on = {CORE: 1.0 - sleeve, BTC: sleeve}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["on"] = dict(off), False   # warm-up = benchmark
        else:
            st["w"] = drift(st["w"], i, px)
        if dates[i] in us_days() and i >= n:
            # BTC bars dated strictly before today: indices i-n .. i-1
            xs = [px[BTC][k] for k in range(i - n, i)]
            if None not in xs:
                state = xs[-1] >= max(xs)
                if state != st["on"]:
                    st["on"] = state
                    st["w"] = dict(on if state else off)
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "high5": make(n=5),
    "high20": make(n=20),
    "sleeve5": make(sleeve=0.05),
    "sleeve20": make(sleeve=0.20),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "R-2026-11-10-BTCSLEEVE10H", weights, [CORE, BTC], bench=CORE, start="2014-09-17",
        asset_class="crypto", trials=8, family="btc-sleeve-6040", variants=VARIANTS,
        factors="ff5mom",
        notes="Quantpedia 2025 (Belobrad) iteration 1 as 90% VBINX + 10% BTC when BTC's last close "
              "(bar dated < today) is a 10-day high, else 100% VBINX; US days only; switch on state "
              "change, drift between; bench VBINX (not BTC: 90% traditional book); 25bp; "
              "vault sealed from 2024-11"),
        indent=1))
