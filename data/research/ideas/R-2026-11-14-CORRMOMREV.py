"""R-2026-11-14-CORRMOMREV — commodity sector momentum switched to reversal by
intra-market correlation (replication of the source's long-short form on its
own universe). PROMOTES ledger row I-2026-11-11-CORRMOMREV (update that row's
id/phase; no second row). Its control, plain 12-month momentum on the same
universe, is R-2026-11-14-CORRMOMCTL (run both; the replication is judged on
the pair). League round 1, commodities desk.

Source: Margareta Pauchlyova (with R. Vojtko), "How to Improve Commodity
Momentum Using Intra-Market Correlation", Quantpedia 2024-09-16
https://quantpedia.com/how-to-improve-commodity-momentum-using-intra-market-correlation/
(SSRN 4964417). DBA/DBB/DBE/DBP from 2007, monthly; 12-month ranking; long the
2 best / short the 2 worst when short-term (20-day) average correlation of the
ETFs' daily returns is above long-term (250-day), else the reversal: long the
2 worst / short the 2 best. Published claim: the switched strategy
"outperforms the momentum strategy across all performance metrics" (return,
volatility, max drawdown, Sharpe, Calmar). The tables are images: NO
published numbers are readable, so only the SIGN can be replicated (stated).
Counter-evidence: Fan & Zhang, "Correlation and Commodity Risk Premia", SSRN
6247358 (2026-02) find momentum does WORSE in high-comovement regimes in
futures — the opposite conditioning. This test referees the two on ETFs.
Theme 28: short legs now earn T-bills, so the long-short form is fairly priced.

HYPOTHESIS (written before any run): when the four sectors suddenly move
together (short-term correlation above its long-term level) a common macro
driver is trending and relative momentum persists; when they decouple,
sector-specific shocks dominate and overreact, so relative performance
reverses over the next month.
REPLICATION CHECK (pre-registered): reproduced if this script's full-period
Sharpe AND worst drop are both better than R-2026-11-14-CORRMOMCTL's (the
source's "all metrics"), sign only.
PASS CRITERION (pre-registered): research_bt verdict PASS vs T-bills (bench
None: a market-neutral long-short book), all §0 gates, >= 70% of the 4
window variants with Sharpe above T-bills.

RULE (fixed before any run):
  at each month-end close i (next bar falls in a new month), need all four
  ETFs priced on every bar of the last 251 bars:
    mom_s   = px_s[i] / px_s[i-252] - 1     (12-month ranking, daily bars)
    c(W)    = mean of the 6 pairwise correlations of the four ETFs' daily
              returns over the last W returns (bars i-W+1 .. i)
    if c(20) > c(250): long the 2 highest mom, short the 2 lowest
    else:              long the 2 lowest mom,  short the 2 highest
    each long +0.5, each short -0.5 (100% long / 100% short, net 0; the
    capital sits in T-bills and short proceeds earn T-bills — harness fix 2)
  held to the next month-end. Ties by name.
Benchmark: T-bills (bench None). Costs 5bp per unit of turnover (no borrow
fee modelled on the ETF shorts — DBA/DBB/DBE/DBP are easy to borrow at
Schwab most of the time; optimistic by the borrow fee, stated).
Start 2007-01-01 (ETFs list 2007-01-05; first signal at the 2008-01 month-end;
2007 is T-bills). Includes 2008, 2014-16, 2020, 2022.
DATA TIMING: reads closes dated <= i only (harness guard); month-end test
peeks only at dates[i+1]'s MONTH; weights decided at close i earn
close i -> close i+1.
Variants (neighbours of the two correlation windows): short 10 / 40 days,
long 125 / 500 days (500 needs 501 bars: the 500-day variant starts ~2009).
NEW FAMILY "cmd-corr-momrev" -> trials 1 + 4 = 5.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

UNIV = ["DBA", "DBB", "DBE", "DBP"]
START = "2007-01-01"
MOM = 252


def _rets(px, s, i, w):
    out = []
    for k in range(i - w + 1, i + 1):
        a, b = px[s][k - 1], px[s][k]
        if not (a and b):
            return None
        out.append(b / a - 1)
    return out


def _corr(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx <= 0 or vy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(vx * vy)


def avg_corr(px, i, w):
    rs = {s: _rets(px, s, i, w) for s in UNIV}
    if any(v is None for v in rs.values()):
        return None
    cs = []
    for a in range(len(UNIV)):
        for b in range(a + 1, len(UNIV)):
            c = _corr(rs[UNIV[a]], rs[UNIV[b]])
            if c is None:
                return None
            cs.append(c)
    return sum(cs) / len(cs)


def momentum_ranks(px, i):
    mom = {}
    for s in UNIV:
        a, b = px[s][i - MOM], px[s][i]
        if not (a and b):
            return None
        mom[s] = b / a - 1
    return sorted(UNIV, key=lambda s: (-mom[s], s))     # best first


def make(short=20, long=250, switch=True):
    need = max(MOM, long + 1, short + 1)
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        w = {}
        if i >= need:
            order = momentum_ranks(px, i)
            regime_mom = True
            if order and switch:
                cs, cl = avg_corr(px, i, short), avg_corr(px, i, long)
                regime_mom = None if (cs is None or cl is None) else cs > cl
            if order and regime_mom is not None:
                best, worst = order[:2], order[2:]
                lo, sh = (best, worst) if regime_mom else (worst, best)
                w = {s: 0.5 for s in lo}
                w.update({s: -0.5 for s in sh})
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    variants = {"short10": make(10, 250), "short40": make(40, 250),
                "long125": make(20, 125), "long500": make(20, 500)}
    res = rb.evaluate("R-2026-11-14-CORRMOMREV", weights, UNIV, None, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="cmd-corr-momrev", variants=variants,
                      notes="month-end: DBA/DBB/DBE/DBP; if mean pairwise corr(20d) > corr(250d) long 2 best / short "
                            "2 worst by 252-day return, else long 2 worst / short 2 best; +-0.5 each, net 0, T-bills "
                            "on capital and short proceeds; bench T-bills; 5bp; replication (sign only) of "
                            "Pauchlyova/Quantpedia 2024 vs control R-2026-11-14-CORRMOMCTL; promotes "
                            "I-2026-11-11-CORRMOMREV")
    print(json.dumps(res, indent=1))
    ctl = rb.RESULTS / "R-2026-11-14-CORRMOMCTL.json"
    if ctl.exists():
        c = json.loads(ctl.read_text())
        rep = res["idea_sharpe"] > c["idea_sharpe"] and res["idea_maxdd"] > c["idea_maxdd"]
        print(json.dumps({"replication_check": "REPRODUCED (sign)" if rep else "NOT REPRODUCED",
                          "switched": {"sharpe": res["idea_sharpe"], "maxdd": res["idea_maxdd"]},
                          "control": {"sharpe": c["idea_sharpe"], "maxdd": c["idea_maxdd"]}}, indent=1))
    else:
        print("replication_check: run R-2026-11-14-CORRMOMCTL first (control result not found)")
