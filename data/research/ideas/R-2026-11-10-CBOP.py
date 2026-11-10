"""R-2026-11-10-CBOP — cash-based operating profitability (Ball, Gerakos,
Linnainmaa & Nikolaev 2016), long-only, on the point-in-time S&P 500
ex financials (survivorship-free).

Promoted from the queue row I-2026-11-09-CBOP (scored 69 on 2026-11-09).
Same mechanism, first test.
Source: Ball, Gerakos, Linnainmaa & Nikolaev (2016) "Accruals, cash flows,
and operating profitability in the cross section of stock returns",
J. Financial Economics 121(1) 28-45
(https://econpapers.repec.org/RePEc:eee:jfinec:v:121:y:2016:i:1:p:28-45).
Their result: cash-based operating profitability subsumes the accrual
anomaly and beats gross/operating profitability as a return predictor;
the accrual effect is the accrual part of profitability.

RATIONALE (fixed before any run): profits earned in cash are more
persistent than profits booked as accruals (receivables, inventory build),
and investors fixate on headline earnings, so firms whose operating profit
is backed by cash are under-priced. Last night's ACCRUALS (Sloan) was +8.6%
vs SPY +7.6% with alpha t 1.5 and potential 3; GPROF (gross profitability)
+10.4% with no alpha. CbOP is the published fix that combines the two: if
cash profitability carries anything beyond FF5 RMW, this is where it shows.
Known risk: it IS a profitability signal, so RMW may absorb it (theme 20).

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the decision day, priced that
    day, excluding Sharadar sector "Financial Services" (as ACCRUALS; BGLN
    exclude financials — bank revenue/COGS lines are not comparable).
  * Decision day: the last close of June each year.
  * Rows: the latest ARY row with public `date` <= decision day (calendardate
    <= 18 months old) and the prior fiscal-year ARY row (9-15 months
    earlier) — exactly NETISS's two_rows().
  * Signal: CbOP = (revenue - cor - sgna
                    - d(receivables) - d(inventory)
                    + d(deferredrev) + d(payables)) / assets(latest),
    d(x) = latest - prior. Missing cor/sgna count as 0; a missing balance
    item in either year makes its change 0; revenue and assets required.
  * Hold the HIGHEST 20% by CbOP, value-weighted by the latest row's
    `marketcap`, until next June; weights drift with prices in between.
  * Need >= 20 scored names; before the first June decision hold SPY.
  * Variants (robustness gate): top 10%, 15%, 25%, 30%.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha
    gate. family "cash-profitability" (new): trials = 1 + 4 = 5.
CHANGE vs the I- row, made BEFORE any run (data check, not a result): the
I- row wrote "- sgna + rnd" (Compustat's XSGA includes R&D, so BGLN add R&D
back). Sharadar reports `sgna` and `rnd` as SEPARATE lines (checked on the
cached ARY rows: sgna + rnd <= opex in 1,785 of 1,873 R&D-firm rows, equal
when there are no other operating lines, e.g. JNJ FY1993 6,953 = 5,771 +
1,182),
so Sharadar's sgna already excludes R&D and "+ rnd" would add it twice.
CbOP here therefore omits the rnd term (R&D is not subtracted = added back).
BGLN also adjust for prepaid expenses and accrued expenses; Sharadar has no
separate lines for them (they sit inside assetsc/liabilitiesc), so those two
changes are omitted — noted as an approximation.
Delisted names: a held stock that delists returns 0 from its last price.
Data sharing: same ARY / price / tickers queries as ACCRUALS and NETISS.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("accruals", _here.with_name("R-2026-11-09-ACCRUALS.py"))
acc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acc)
ni = acc.ni                                        # NETISS helpers (two_rows, make_annual)
ag = acc.ag                                        # ASSETGROW helpers (members, fund, _num)

ID = "R-2026-11-10-CBOP"
START = ni.START
BENCH = ni.BENCH
EXCLUDE = {"Financial Services"}


def sector(t):
    return acc.sector(t)                           # tickers table paged once (shared)


def _d(r, prev, k):
    a, b = ag._num(r.get(k)), ag._num(prev.get(k))
    return (a - b) if a is not None and b is not None else 0.0


def cbop(t, day):
    pair = ni.two_rows(t, day)
    if not pair:
        return None
    r, prev = pair
    n = ag._num
    rev, assets, mc = n(r.get("revenue")), n(r.get("assets")), n(r.get("marketcap"))
    if rev is None or not assets or assets <= 0 or not mc or mc <= 0:
        return None
    op = rev - (n(r.get("cor")) or 0.0) - (n(r.get("sgna")) or 0.0)
    cash_op = (op - _d(r, prev, "receivables") - _d(r, prev, "inventory")
               + _d(r, prev, "deferredrev") + _d(r, prev, "payables"))
    return cash_op / assets, mc


def make_weights(frac=0.20):
    def select(day, i, px):
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None or sector(t) in EXCLUDE:
                continue
            x = cbop(t, day)
            if x:
                scored.append((-x[0], x[1], t))    # highest CbOP first
        if len(scored) < 20:
            return None
        scored.sort()
        pick = scored[:max(1, int(round(len(scored) * frac)))]
        tot = sum(mc for _, mc, _ in pick)
        return {t: mc / tot for _, mc, t in pick}
    return ni.make_annual(select)


weights = make_weights(0.20)
VARIANTS = {f"top{int(q * 100)}": make_weights(q) for q in (0.10, 0.15, 0.25, 0.30)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="cash-profitability", variants=VARIANTS, source="sharadar",
        notes=("Ball-Gerakos-Linnainmaa-Nikolaev cash-based operating profitability: highest 20% of "
               "point-in-time S&P 500 ex Financial Services by (revenue - cor - sgna - d receivables - "
               "d inventory + d deferredrev + d payables) / assets (Sharadar ARY, public date <= "
               "decision day; sgna already excludes R&D), value-weighted, rebalanced each June; SPY "
               "warm-up; variants top 10/15/25/30%; survivorship-free; promoted from I-2026-11-09-CBOP"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
