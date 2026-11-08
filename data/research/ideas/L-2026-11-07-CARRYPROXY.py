"""L-2026-11-07-CARRYPROXY — lab original (RESEARCH.md §2b), queued 2026-11-07,
scripted 2026-11-08: oil curve-slope momentum from two ETFs.

Ingredients / sources:
  * Boons & Porras Prado, "Basis-Momentum", Journal of Finance 74(1), 2019
    (https://ideas.repec.org/a/bla/jfinan/v74y2019i1p239-279.html): momentum
    in the futures BASIS (front minus deferred return) predicts commodity
    returns better than basis or price momentum.
  * WisdomTree, "Please mind the slope" (Jan 2026,
    https://www.wisdomtree.com/gb/insights/blog/please-mind-the-slope-why-futures-curves-matter):
    time-series slope momentum 3.8%/yr (t 2.0) on futures curves 2001-2025
    (ledger row I-2026-11-07-CMDSLOPE, untestable: no curve data).
Rationale: USO holds the front WTI contract; USL holds 12 consecutive monthly
contracts equally. USO's return minus USL's over a window is (approximately)
the change in the curve's front-vs-deferred spread plus the roll-yield gap,
i.e. a free price-only proxy for basis-momentum. When the front outruns the
ladder, the curve is tightening (toward backwardation: low inventories, a
positive spot/term premium per Gorton-Hayashi-Rouwenhorst); hold front oil.
When the ladder outruns the front (curve loosening into contango, e.g. 2008 H2,
2014-15, early 2020), stay in T-bills.

RULE (fixed before any run; exactly the ledger row's stated rule):
  at each month-end close i:
    if USO 63-day return > USL 63-day return: hold 100% USO next month
    else: T-bills
Benchmark: buy & hold USO. Costs 5bp/unit turnover. USL starts 2007-12, so the
first signal is ~2008-03 (includes the 2008 crash, 2014-16, 2020).
Variants (neighbours of the 63-day window): 21, 42, 126, 189 days.
trials = 5 (this rule + 4 variants; new family, nothing run before).

USO ROLL CHANGE (April 2020): during the negative-WTI episode USO stopped
holding only the front month and spread across the curve (later front-two /
longer-dated mix), which shrinks the USO-USL gap after 2020-04. The verdict is
one run over the whole development period; the script ALSO prints the same
rule's Sharpe vs USO before and after 2020-04-01 as a diagnostic (no extra
verdict, no extra trial). If the edge lives only pre-2020 the proxy is broken
today and the idea waits for real curve data (CL1/CL2/CL12).
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SPLIT = "2020-04-01"


def make(lb=63):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        u, l = px["USO"], px["USL"]
        on = (i >= lb and u[i] and u[i - lb] and l[i] and l[i - lb]
              and u[i] / u[i - lb] > l[i] / l[i - lb])
        st["w"] = {"USO": 1.0} if on else {}
        return st["w"]
    return weights


weights = make()


def split_report(fn, start="2007-12-01"):
    """Diagnostic only: Sharpe/CAGR of the rule and of USO before/after SPLIT."""
    dates, px = rb.prices(["USO", "USL"], start)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(fn, dates, px, rf, 5.0)
    bret = rb.bench_returns("USO", dates, px, rf)
    out = {}
    for name, sel in (("pre", lambda d: d < SPLIT), ("post", lambda d: d >= SPLIT)):
        idx = [k for k in range(len(rets)) if sel(dates[k + 1])]
        r, b, f = [rets[k] for k in idx], [bret[k] for k in idx], [rf[k + 1] for k in idx]
        out[name] = {"days": len(idx), "idea_sharpe": round(rb.sharpe(r, f), 3),
                     "uso_sharpe": round(rb.sharpe(b, f), 3),
                     "idea_cagr": round(rb.cagr(r), 4), "uso_cagr": round(rb.cagr(b), 4)}
    return out


if __name__ == "__main__":
    variants = {f"lb{k}": make(k) for k in (21, 42, 126, 189)}
    res = rb.evaluate("L-2026-11-07-CARRYPROXY", weights, ["USO", "USL"], "USO", start="2007-12-01",
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="L-2026-11-07-CARRYPROXY", variants=variants,
                      notes="month-end: USO next month if USO 63d return > USL 63d return (curve tightening), "
                            "else T-bills; bench USO; lab original (basis-momentum ETF proxy); "
                            "USO roll method changed 2020-04 - see split diagnostic; vault sealed")
    res["split_diagnostic_2020_04"] = split_report(weights)
    print(json.dumps(res, indent=1))
