"""L-2026-11-10-BOLDTREND — original (RESEARCH.md §2b): the ByteTree BOLD
bitcoin/gold inverse-volatility mix, with Bitcoin's slice moved to T-bills
while Bitcoin is below its 10-month average.

Ingredients:
  * R-2026-11-10-BOLD (Vinter ByteTree BOLD1 methodology, BTC/gold inverse
    360-day vol, monthly):
    https://cdn.21shares.com/uploads/current-documents/21SharesVinter%20ByteTree%20BOLD%20Indexes.pdf
  * DD-2026-11-TREND (shortlist potential 5): 10-month SMA gate; on BTC it
    cut the worst drop -83% -> -72% at < 1 trade/yr.
Varies R-2026-11-10-BOLD (adds a crash gate on the BTC leg only) and
L-2026-11-07-BTCTRENDVOL (trend x size on BTC alone: -46% worst drop, lost
return): here the "size" comes from relative risk vs gold, and gold — not
cash — is the permanent partner.

Rationale (written before any run): BOLD's drawdowns are BTC's bears seen
through a 25-35% weight (2018: BTC -84%, 2022: -77%; gold flat both years),
and the inverse-vol weight is HIGHEST right after calm bull years — i.e. at
the top (late 2021). A slow trend gate removes exactly those episodes and
nothing else (DD-TREND's BTC gate is out ~1/3 of months, mostly in bears).
Gold keeps its own weight (no re-scaling), so the off state is a low-risk
gold + T-bill book. Expected: BOLD's return minus little, worst drop roughly
halved, correlation to equities lower than BTC's (gold leg). Judge as a
sleeve: Sharpe, worst drop, corr to SPY, portfolio.marginal vs the book.
Counter-hypothesis: BOLD's monthly rebalancing already buys BTC after
crashes (its return source); the gate stops exactly those purchases and
re-enters late, so it may cut the rebalancing premium more than the losses
(theme 13's lesson for value, applied to a rebalancing premium).

RULE (fixed before any run):
  * BOLD exactly as R-2026-11-10-BOLD: last GLD business day of each month,
    BTC weight wB = (1/sB)/(1/sB + 1/sG) from 360-day vols measured 5
    business days earlier; GLD weight 1 - wB; quantities fixed between
    rebalances.
  * Gate, at the same rebalance: closes = BTC month-end closes (bars dated
    the last calendar day) of the previous 9 months + BTC's bar dated the
    day before the rebalance day (strictly before today: bar D closes at
    00:00 UTC D+1, after GLD's US close on D). ON if the newest > their mean
    (10 points = DD-TREND SMA10). OFF -> BTC weight goes to T-bills
    (weights: GLD 1-wB, cash wB).
  * Warm-up (no BOLD weight yet): 100% BTC = the benchmark (neutral), as BOLD.
Benchmark = buy & hold BTC-USD (lead's crypto rule; also read vs BOLD and
GLD). 25bp per unit turnover on both legs (asset_class crypto).
Variants: SMA 8 / 12 months; BTC slice to GLD instead of T-bills when OFF;
vol window 180 days.
trials: BOLD's 5 + this run's 5 = 10; family btc-gold-mix (shared with BOLD).
Tradeable at Schwab as IBIT + GLD/IAU (2024->); spot BTC before."""
import importlib.util
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "bold_base", str(Path(__file__).resolve().parent / "R-2026-11-10-BOLD.py"))
bold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bold)          # the BOLD rule itself, unchanged

BTC, GOLD = bold.BTC, bold.GOLD


def make(months=10, to_gold=False, window=360):
    st = {}

    def weights(i, dates, px):
        if i == 0:                        # evaluate() re-runs simulate: reset state
            st.clear()
            st["w"], st["ends"] = {BTC: 1.0}, []   # warm-up = benchmark (neutral)
        else:
            st["w"] = bold.drift(st["w"], i, px)
            if dates[i][:7] != dates[i - 1][:7] and px[BTC][i - 1]:
                st["ends"].append((dates[i - 1], px[BTC][i - 1]))
        if bold.is_rebalance(i, dates):
            wb = bold.btc_weight(i, dates, px, window)
            if wb is not None:
                # month-ends strictly before today, excluding a bar dated today
                prior = [c for d, c in st["ends"] if d < dates[i]][-(months - 1):]
                last = px[BTC][i - 1] if i >= 1 else None
                on = True
                if len(prior) == months - 1 and last:
                    pts = prior + [last]
                    on = last > sum(pts) / months
                if on:
                    st["w"] = {BTC: wb, GOLD: 1 - wb}
                elif to_gold:
                    st["w"] = {GOLD: 1.0}
                else:
                    st["w"] = {GOLD: 1 - wb}   # BTC slice in T-bills
        return dict(st["w"])
    return weights


weights = make()

VARIANTS = {
    "sma8": make(months=8),
    "sma12": make(months=12),
    "slice_to_gold": make(to_gold=True),
    "vol180": make(window=180),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "L-2026-11-10-BOLDTREND", weights, [BTC, GOLD], bench=BTC, start="2014-09-17",
        asset_class="crypto", trials=10, family="btc-gold-mix", variants=VARIANTS,
        notes="lab original: BOLD (BTC/GLD inverse 360-day vol, monthly) with the BTC slice in T-bills "
              "while BTC (bar dated < rebalance day) is below its 10-month SMA; warm-up holds BTC "
              "(neutral); 25bp both legs; vault sealed from 2024-11"),
        indent=1))
