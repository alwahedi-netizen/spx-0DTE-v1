"""R-2026-11-10-GOLDSHOCK — gold as a short-lived safe haven after extreme stock
shocks (Baur & Lucey 2010). PROMOTES ledger row I-2026-11-09-GOLDSHOCK (score 76,
first in line from the 11-09 queue) — update that row's id/phase, do not add a
second row.

Source: Dirk G. Baur & Brian M. Lucey, "Is Gold a Hedge or a Safe Haven? An
Analysis of Stocks, Bonds and Gold", The Financial Review 45(2), 2010, 217-229
(https://econpapers.repec.org/RePEc:bla:finrev:v:45:y:2010:i:2:p:217-229 ; WP:
https://www.tcd.ie/triss/assets/PDFs/iiis/iiisdp198.pdf). Using returns below the
10% / 5% / 1% quantiles as "extreme" stock days (US, UK, German markets
1995-2005), gold is a safe haven for stocks on those days and for roughly 15
trading days after the shock, then it is not (investors who hold gold longer
lose as it gives back the haven bid). Independent replication of the haven
property on more markets: Baur & McDermott, JBF 34(8) 2010.

Rationale (the paper's): in a flight to quality investors buy gold right after
an equity crash; the bid is temporary, so the premium sits in the days after a
shock, not in a long holding. A long-gold sleeve that is ON only in those
windows should earn gold's crisis premium without holding gold through its
long flat/down stretches (1980-2001-style, 2013-15).

RULE (fixed before any run; exactly the ledger row's stated rule):
  at each daily close i:
    r_i = SPY close i / close i-1 - 1
    q   = 5th percentile of SPY's previous 252 daily returns (i-252 .. i-1;
          today's return is NOT in its own threshold)
    if r_i < q: a shock -> hold 100% GLD for the next 15 trading days
                (positions decided at closes i .. i+14); a new shock inside
                a window restarts the 15-day count
    otherwise (no live window): T-bills
  Percentile = the value at rank floor(p * n) of the sorted 252 returns.
Benchmark: buy & hold GLD (single-commodity timing rule: the ledger row fixed
GLD as the yardstick before the run). Because the sleeve is in cash most of the
time, a Sharpe win over GLD needs the in-window Sharpe to be ~2.5x gold's; the
script also prints a NO-VERDICT diagnostic: GLD's mean return and Sharpe inside
vs outside the windows, the share of days in the market, and SPY over the same
windows (does the sleeve pay while stocks are falling?).
Costs 5bp. Start 2004-11-18 (GLD listing); first possible shock ~2005-11 after
the 252-day warm-up. Includes 2008, 2011, 2015-16, 2018 Q4, 2020, 2022.
Execution caveat (red team): the shock is read on the same close the trade is
made (harness convention, as GOLDCRISIS) — live, it needs a ~15:55 ET SPY print
or a next-open fill.
Variants (neighbours): percentile 1% and 10% (the paper's other quantiles);
holding 10 and 20 days. New family "gold-shock" -> trials 5.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

START = "2004-11-18"
LB = 252


def _pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))]


def make(p=0.05, hold=15):
    st = {"left": 0}

    def weights(i, dates, px):
        if i == 0:
            st["left"] = 0
        spy = px["SPY"]
        if i >= LB + 1 and spy[i] and spy[i - 1]:
            past = [spy[k] / spy[k - 1] - 1 for k in range(i - LB, i)
                    if spy[k] and spy[k - 1]]
            if len(past) >= LB * 0.95 and spy[i] / spy[i - 1] - 1 < _pct(past, p):
                st["left"] = hold
        if st["left"] > 0 and px["GLD"][i]:
            st["left"] -= 1
            return {"GLD": 1.0}
        if st["left"] > 0:
            st["left"] -= 1
        return {}
    return weights


weights = make()


def window_report(fn, start=START):
    """Diagnostic only (no verdict, no trial): gold and SPY inside vs outside
    the shock windows, on development data."""
    dates, px = rb.prices(["SPY", "GLD"], start)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rf = rb.tbill(dates)
    on = []                     # state resets at i == 0; replay under the look-ahead guard
    clock = [0]
    view = {s: rb._Past(c, clock) for s, c in px.items()}
    for i in range(len(dates) - 1):
        clock[0] = i
        on.append(bool(fn(i, dates, view)))
    out = {}
    for name, flag in (("in_window", True), ("out_of_window", False)):
        g, s, f = [], [], []
        for i in range(len(dates) - 1):
            if on[i] != flag:
                continue
            a, b = px["GLD"][i], px["GLD"][i + 1]
            c, d = px["SPY"][i], px["SPY"][i + 1]
            if a and b and c and d:
                g.append(b / a - 1)
                s.append(d / c - 1)
                f.append(rf[i + 1])
        out[name] = {"days": len(g),
                     "gld_mean_bp": round(1e4 * sum(g) / max(len(g), 1), 2),
                     "gld_sharpe": round(rb.sharpe(g, f), 3),
                     "spy_mean_bp": round(1e4 * sum(s) / max(len(s), 1), 2)}
    out["share_days_in_gold"] = round(sum(on) / max(len(on), 1), 3)
    return out


if __name__ == "__main__":
    variants = {"p01": make(0.01, 15), "p10": make(0.10, 15),
                "hold10": make(0.05, 10), "hold20": make(0.05, 20)}
    res = rb.evaluate("R-2026-11-10-GOLDSHOCK", weights, ["SPY", "GLD"], "GLD", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="gold-shock", variants=variants,
                      notes="daily: if SPY's return < 5th pct of its previous 252 daily returns, hold GLD "
                            "for the next 15 trading days (restart on a new shock), else T-bills; bench GLD; "
                            "Baur-Lucey FR 2010; promotes I-2026-11-09-GOLDSHOCK")
    res["window_diagnostic"] = window_report(make())
    print(json.dumps(res, indent=1))
