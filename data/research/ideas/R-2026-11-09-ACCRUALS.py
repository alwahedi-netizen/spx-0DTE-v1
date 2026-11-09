"""R-2026-11-09-ACCRUALS — the accruals anomaly (Sloan 1996), long-only, on
the point-in-time S&P 500 (survivorship-free).

Promoted from the queue row I-2026-11-08-ACCRUALS (scored 71 on 2026-11-08).
Same mechanism, first test.
Sources: Sloan (1996) "Do Stock Prices Fully Reflect Information in Accruals
and Cash Flows about Future Earnings?", The Accounting Review 71(3); risk vs
mispricing: Hirshleifer, Hou & Teoh (2011), Management Science 57(5) 797-816
(https://econpapers.repec.org/RePEc:inm:ormnsc:v:57:y:2011:i:5:p:797-816);
cash-flow-statement accruals: Hribar & Collins (2002). Decay warning: Green,
Hand & Soliman (2011) document the anomaly's demise after ~2000 as hedge
funds crowded it — EXPECT weak results in our 2000+ window.

RATIONALE (fixed before any run): investors fixate on reported earnings and
do not see that the accrual part (earnings not backed by operating cash) is
less persistent than the cash part. Firms whose profits are mostly cash keep
their earnings; high-accrual firms disappoint. Known risk: correlates with
the FF5 profitability (RMW) and investment (CMA) factors.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the decision day, EXCLUDING
    the Financial Services sector (Sharadar tickers table) — see change note;
    Sharadar survivorship-free prices; only names priced on the decision day.
  * Decision day: the last close of June each year.
  * Signal: ACC = (netinc - ncfo) / ((assets + prior-year assets) / 2), from
    the latest ARY row whose public `date` <= decision day (calendardate <=
    18 months old) and the prior fiscal-year ARY row (9-15 months earlier).
  * Hold the LOWEST 20% by ACC (most cash-backed earnings), value-weighted by
    the latest row's `marketcap`, until next June; weights drift with prices.
  * Before the first June decision: hold SPY (warm-up).
  * Variants (robustness gate): lowest 10%, 15%, 25%, 30%.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha.
    family "accruals" (new): trials = 1 + 4 = 5.
CHANGE vs the I- row, made BEFORE any run: financial firms are excluded (the
accruals literature excludes SIC 6000-6999: a bank's operating cash flow
carries loan and trading flows, e.g. Citigroup's ncfo swings -$73bn..+$61bn
against ~$10-20bn of net income, which would rank banks as "most cash-backed"
by accident). No other change.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("netiss", _here.with_name("R-2026-11-09-NETISS.py"))
ni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ni)
ag = ni.ag                                         # ASSETGROW helpers (members, fund, _num)

ID = "R-2026-11-09-ACCRUALS"
START = ni.START
BENCH = ni.BENCH
EXCLUDE = {"Financial Services"}
_SECTOR = {}


def sector(t):
    if not _SECTOR:
        # rb.sharadar() cannot pass the tickers table's `table=` filter — page it
        # directly, exactly as R-2026-11-07-MAGICSF does
        off = 0
        while True:
            rows = rb._sh_fetch("tickers", {"table": "stocks", "limit": 10000, "offset": off})
            for r in rows:
                _SECTOR.setdefault(r["ticker"], r.get("sector"))
            if len(rows) < 10000:
                break
            off += 10000
    return _SECTOR.get(t)


def accruals(t, day):
    pair = ni.two_rows(t, day)
    if not pair:
        return None
    r, prev = pair
    n = ag._num
    ni_, cfo, a1, a0, mc = (n(r.get("netinc")), n(r.get("ncfo")), n(r.get("assets")),
                            n(prev.get("assets")), n(r.get("marketcap")))
    if None in (ni_, cfo) or not a1 or not a0 or a1 <= 0 or a0 <= 0 or not mc or mc <= 0:
        return None
    return (ni_ - cfo) / ((a1 + a0) / 2), mc


def make_weights(frac=0.20):
    def select(day, i, px):
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None or sector(t) in EXCLUDE:
                continue
            x = accruals(t, day)
            if x:
                scored.append((x[0], x[1], t))
        if len(scored) < 20:
            return None
        scored.sort()                              # lowest accruals first
        pick = scored[:max(1, int(round(len(scored) * frac)))]
        tot = sum(mc for _, mc, _ in pick)
        return {t: mc / tot for _, mc, t in pick}
    return ni.make_annual(select)


weights = make_weights(0.20)
VARIANTS = {f"low{int(q * 100)}": make_weights(q) for q in (0.10, 0.15, 0.25, 0.30)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="accruals", variants=VARIANTS, source="sharadar",
        notes=("Sloan accruals: lowest 20% of point-in-time S&P 500 ex Financial Services by "
               "(netinc - ncfo)/avg assets (Sharadar ARY, public date <= decision day), value-weighted, "
               "rebalanced each June; SPY warm-up; variants low 10/15/25/30%; survivorship-free; "
               "promoted from I-2026-11-08-ACCRUALS"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
