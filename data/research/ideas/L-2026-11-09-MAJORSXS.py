"""L-2026-11-09-MAJORSXS — original (RESEARCH.md §2b): long-only short-horizon
cross-sectional momentum among the coins that were the largest by market cap
on a FIXED past date (a point-in-time universe), with an absolute-momentum
filter that sends empty slots to T-bills.

Evidence for the ingredients (all peer-reviewed):
  * Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency", JF 2022,
    https://papers.ssrn.com/abstract=3379131 — 1- to 4-week cross-sectional
    momentum in crypto (weekly rebalancing).
  * Tzouvanas, Kizys & Tsend-Ayush, "Momentum trading in cryptocurrencies:
    short-term returns and diversification benefits", Economics Letters 2020,
    https://ideas.repec.org/a/eee/ecolet/v191y2020ics0165176519303647.html —
    J/K momentum on the 12 largest coins: strong at short horizons, gone at long.
  * Zaremba, Bilgin, Long, Mercik & Szczygielski, IRFA 2021,
    https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html —
    the largest, most tradeable coins show MOMENTUM (small coins reverse).
  * Antonacci-style absolute filter = DD-2026-11-TREND's lesson (theme 10/16:
    the time-series filter is what cuts crypto crashes).
Universe: CoinMarketCap top 12 on 2018-01-07,
https://coinmarketcap.com/historical/20180107/ — BTC, XRP, ETH, BCH, ADA, XEM,
LTC, TRX, XLM, MIOTA, DASH, EOS. MIOTA is DROPPED: Yahoo has IOTA only from
2023-09 (ticker change). That removes a big loser (survivorship in our
favour — stated). The other 11 are kept whatever happened to them (XEM, EOS,
DASH, BCH all collapsed), so the universe is point-in-time, not today's
winners; the snapshot date (the 2018 peak) is our choice and is HARSH on alts.

Varies I-2026-10-28-CRYPTOXS (rejected: today's coin list, alt shorting) and
L-2026-11-07-ETHBTCROT (FAIL: 2-coin relative trend): long-only, 11 coins
fixed in the past, short (4-week) formation as the literature says, plus an
absolute filter. Theme 16 says crypto rules add crash protection, not return;
this is the desk's first test of whether cross-sectional selection among
majors can ADD return.

Rationale (written before any run): attention and flows rotate between large
coins in waves of weeks (alt seasons, ETH/DeFi 2020-21); the leaders keep
leading for a few weeks (LTW, Zaremba). Requiring a positive own return
keeps the book out of joint crashes, when every major falls together
(Mallela-Leonelli 2026: lower-tail dependence is near-complete).
Counter-hypothesis: post-2018 alts bled against BTC, so any rule that can
leave BTC loses to it; momentum among majors is the BTC-dominance cycle.

RULE (fixed before any run):
  * Universe U = the 11 coins above (BTC-USD ... EOS-USD), daily UTC closes.
  * Each Sunday close i on or after 2018-01-07 (the universe date): score_s =
    close_i / close_{i-28} - 1 for coins with both prices.
  * Hold the top 3 by score, 1/3 each, but only coins with score > 0; empty
    slots in T-bills. Weights drift between Sundays (no daily rebalancing).
  * Before the first rebalance (data start 2017-12-01): hold 100% BTC, the
    benchmark — neutral; the universe is not used before its own date.
Benchmark = buy & hold BTC-USD; 25bp per unit turnover (asset_class crypto;
alt spreads are wider — the 50bp double-cost gate is the realistic check).
Variants: lookback 14 / 56 days; top 2 / top 5.
trials: 1 + 4 variants + the 5 runs of L-2026-11-07-ETHBTCROT (relative
strength among majors, same question) = 10; family crypto-majors-xsmom.
Tradeability: only BTC/ETH (and, from 2025, some alts via new US spot ETFs)
are Schwab-tradeable; most of the test period is not. Survivorship and
tradeability cap this at PROMISING (RESEARCH §0.5 spirit)."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BENCH = "BTC-USD"
UNIVERSE = ["BTC-USD", "XRP-USD", "ETH-USD", "BCH-USD", "ADA-USD", "XEM-USD",
            "LTC-USD", "TRX-USD", "XLM-USD", "DASH-USD", "EOS-USD"]
UNIVERSE_DATE = "2018-01-07"


def make(lookback=28, top=3, weekday=6):
    st = {}

    def weights(i, dates, px):
        if i == 0:                      # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"] = {BENCH: 1.0}      # warm-up = benchmark (neutral)
        else:                           # drift yesterday's holdings to today's close
            w, grow = st["w"], {}
            for s, x in w.items():
                a, b = px[s][i - 1], px[s][i]
                grow[s] = x * (b / a) if (a and b) else x
            port = sum(grow.values()) + (1 - sum(w.values()))
            st["w"] = {s: g / port for s, g in grow.items()} if port > 0 else {}
        d = dates[i]
        if d >= UNIVERSE_DATE and i >= lookback and date.fromisoformat(d).weekday() == weekday:
            scores = []
            for s in UNIVERSE:
                a, b = px[s][i - lookback], px[s][i]
                if a and b:
                    scores.append((b / a - 1, s))
            scores.sort(reverse=True)
            pick = [s for sc, s in scores[:top] if sc > 0]
            st["w"] = {s: 1.0 / top for s in pick}
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "lb14": make(lookback=14),
    "lb56": make(lookback=56),
    "top2": make(top=2),
    "top5": make(top=5),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-09-MAJORSXS", weights, UNIVERSE, bench=BENCH, start="2017-12-01",
        asset_class="crypto", trials=10, family="crypto-majors-xsmom", variants=VARIANTS,
        notes="lab original: 11 of CoinMarketCap's top-12 on 2018-01-07 (MIOTA missing on Yahoo), Sunday, "
              "top 3 by 28-day return with return > 0, 1/3 each, T-bills for empty slots, weights drift; "
              "warm-up holds BTC; 25bp; coin survivorship partly controlled (fixed past universe) but "
              "MIOTA dropped; vault sealed from 2024-11"),
        indent=1))
