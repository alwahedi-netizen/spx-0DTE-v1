"""L-2026-11-10-CCYVOLTGT — the commodity-currency signal with volatility
targeting (lab original, RESEARCH.md §2b; designed 2026-11-10, rule as
written in its ledger row that night; scripted 2026-11-11 from the queue).
VARIES: R-2026-11-09-CCYCMD (potential 4; DBC while the AUD/CAD/CLP/NZD/ZAR
basket rose vs USD over 3 months: +4.7%/yr vs DBC +0.6%, worst drop -35% vs
-76%, confidence 90%, held-out Sharpe 0.33 vs 0.36). Changes only the SIZE of
the position, never the on/off decision.

INGREDIENTS / SOURCES:
  * Chen, Rogoff & Rossi, QJE 125(3) 2010 — commodity currencies forecast
    commodity prices (the on/off signal; code IMPORTED from
    R-2026-11-09-CCYCMD.py, unchanged).
  * Kang & Kwon, "Volatility-managed commodity futures portfolios", Journal
    of Futures Markets 41(2) 2021
    (https://ideas.repec.org/a/wly/jfutmk/v41y2021i2p159-178.html; ledger row
    I-2026-11-08-VOLMGDCMD): scaling commodity exposure by inverse realised
    variance/volatility raises Sharpe because commodity volatility is
    persistent while returns do not rise with it.
  * Theme 2 (KNOWLEDGE.md): vol-managed leverage passed on equities
    (R-2026-10-28-VTSPYL); this is its first commodity test.

RATIONALE (written before any run): CCYCMD's months in the market include
calm demand-led uptrends and violent ones (2008 H2, 2020 Q1-Q2, 2022); a
fixed 100% weight makes the violent months dominate the risk. Sizing to a
volatility target spends the risk budget evenly: more DBC when commodity vol
is low (when the currency signal has been most reliable), less when it
spikes. If returns do not scale with volatility (Kang-Kwon), Sharpe rises.

RULE (fixed before any run; = the ledger row):
  at each month-end close i:
    on = CCYCMD's rule says hold DBC (mean 3-month log change vs USD of the
         five commodity currencies > 0; FX bars dated STRICTLY BEFORE the
         decision day; >= 3 currencies)
    sigma = stdev of DBC's last 63 daily returns x sqrt(252) (all 63 priced,
            else T-bills)
    weight(DBC) = min(1.5, 0.15 / sigma) if on, else 0 (T-bills)
  held to the next month-end. Above 1x the harness charges the T-bill rate
  on the excess (no financing spread — optimistic, stated).
Benchmark: buy & hold DBC. Costs 5bp. Start 2006-03-01 (DBC 2006-02;
signals ~2006-06). Includes 2008, 2014-16, 2020, 2022.
DATA TIMING: DBC closes <= i (harness guard); FX side data strictly before
the decision day on its own calendar (never enters the simulated universe —
theme 12; =X bars are start-of-day prices, so strictly-before can never see a
value from after the close, theme 21); month-end test peeks dates[i+1]'s
MONTH only.
Variants (neighbours): target 10% / 20% (cap 1.5); vol window 42 / 126 days.
FAMILY "ccy-predicts-cmd": lifetime 11 (CCYCMD 6 + DEMANDVOTE 5) ->
11 + 1 + 4 = 16 (DEMANDVOTE has already run; this run adds its own 5).
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("ccycmd", HERE / "R-2026-11-09-CCYCMD.py")
CCY = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CCY)

START = "2006-03-01"


def _ann_vol(col, i, n):
    if i < n + 1:
        return None
    r = []
    for k in range(i - n + 1, i + 1):
        a, b = col[k - 1], col[k]
        if not (a and b):
            return None
        r.append(b / a - 1)
    m = sum(r) / n
    v = sum((x - m) ** 2 for x in r) / (n - 1)
    return math.sqrt(v * 252) if v > 0 else None


def make(target=0.15, n=63, cap=1.5):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st["sig"] = CCY.make()          # fresh signal state every run
            st["w"] = {}
        on = st["sig"](i, dates, px)         # called every day: CCYCMD's own state stays exact
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st["w"]
        w = {}
        if on.get("DBC"):
            sd = _ann_vol(px["DBC"], i, n)
            if sd:
                w = {"DBC": min(cap, target / sd)}
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"tgt10": make(0.10), "tgt20": make(0.20), "vol42": make(0.15, 42),
                "vol126": make(0.15, 126)}
    res = rb.evaluate("L-2026-11-10-CCYVOLTGT", weights, ["DBC"], "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=16,
                      family="ccy-predicts-cmd", variants=variants,
                      notes="month-end: when CCYCMD is on (commodity-currency basket up over 3 months, FX "
                            "strictly before the decision day), hold DBC at min(1.5, 15% / 63-day realised "
                            "vol), else T-bills; bench DBC; varies R-2026-11-09-CCYCMD (vol-target sizing, "
                            "Kang-Kwon 2021); lab original; vault sealed")
    print(json.dumps(res, indent=1))
