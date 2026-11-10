"""R-2026-11-10-RND — the R&D-intensity premium (Chan-Lakonishok-Sougiannis),
long-only, on the point-in-time S&P 500 (survivorship-free).

Promoted from the queue row I-2026-11-09-RND (scored 71 on 2026-11-09, held
back by that night's 5-script cap). Same mechanism, first test.
Source: Chan, Lakonishok & Sougiannis (2001) "The Stock Market Valuation of
Research and Development Expenditures", J. Finance 56(6) 2431-2456
(https://econpapers.repec.org/RePEc:bla:jfinan:v:56:y:2001:i:6:p:2431-2456).
Their headline: firms with high R&D relative to market value earn large
excess returns (and R&D-intensive firms with poor past returns most of all).
Independent support: Eberhart-Maxwell-Siddique (2004, JF) long-run returns
after R&D increases; Lev-Sougiannis (1996).

RATIONALE (fixed before any run): accounting expenses R&D immediately, so
book value and earnings understate the intangible capital of R&D-heavy
firms. When R&D is large relative to market value, the market is pricing
those firms as if the spending creates nothing; investors under-react to
intangible investment, and the premium is earned as the R&D pays off.
This is "value with intangibles" — a signal that book-to-market (HML) misses
by construction, so it has a chance to show alpha beyond FF5 (theme 8: the
gate that sank every honest-data stock anomaly so far).
Known risks: R&D-heavy sector crashes (2000-02 tech, 2022 biotech); high
RD/ME firms are also low-price firms (HML/long-term reversal overlap).

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the decision day
    (rb.sp500_members on rb.sp500_history), Sharadar survivorship-free prices;
    only names with a price on the decision day.
  * Decision day: the last close of June each year.
  * Eligible: the latest ARY row whose public `date` <= decision day (and
    calendardate <= 18 months old) shows rnd > 0. Non-R&D firms are not
    eligible (the paper sorts R&D firms only).
  * Signal: RD/ME = rnd (that ARY row) / market value ON THE DECISION DAY
    (Sharadar DAILY `marketcap`, millions -> x1e6; same table MAGICSF reads).
    If the DAILY table has no rows for that day, the whole decision falls
    back to the ARY row's own `marketcap` (consistent units within a date).
  * Hold the HIGHEST 20% by RD/ME, equal weight, until next June; weights
    drift with prices between rebalances (buy and hold the book).
  * Need >= 20 eligible names, else keep the previous book. Before the first
    June decision: hold SPY (warm-up, equals benchmark).
  * Variants (robustness gate): top 10%, 15%, 25%, 30%.
  * Benchmark SPY, 5bp/side (stocks), 2000-01 -> vault, strict bar + FF5+Mom
    alpha gate. family "rnd-intensity" (new): trials = 1 + 4 = 5.
Delisted names: a held stock that delists returns 0 from its last price (the
harness has no delisting return) — noted.
Data sharing: fundamentals ARY per ticker + prices per ticker are exactly the
queries ASSETGROW/NETISS/ACCRUALS use (run on the same UTC day as CBOP to
share the cache); adds ~25 DAILY calls (one per June), the same DAILY query
shape MAGICSF uses.
"""
import bisect
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

ID = "R-2026-11-10-RND"
START = ni.START
BENCH = ni.BENCH
_MC = {}


def mcap_on(day):
    """{ticker: market value in USD} on the decision day from Sharadar DAILY."""
    if day not in _MC:
        try:
            rows = rb.sharadar("daily", None, date=day)
        except Exception:  # noqa: BLE001 — falls back to the ARY marketcap
            rows = []
        _MC[day] = {r["ticker"]: float(r["marketcap"]) * 1e6 for r in rows
                    if r.get("marketcap") not in (None, "") and float(r["marketcap"]) > 0}
    return _MC[day]


def rnd_row(t, day, max_age_m=18):
    """(rnd, ARY marketcap) from the latest ARY row public on/before day, or None."""
    ds, rows = ag.fund(t)
    k = bisect.bisect_right(ds, day) - 1
    if k < 0:
        return None
    r = rows[k]
    cd = (r.get("calendardate") or r["date"])[:10]
    if ag._months_between(cd, day) > max_age_m:
        return None
    rd, mc = ag._num(r.get("rnd")), ag._num(r.get("marketcap"))
    if not rd or rd <= 0:
        return None
    return rd, mc


def make_weights(frac=0.20):
    def select(day, i, px):
        daily = mcap_on(day)
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None:    # only names priced on the decision day
                continue
            x = rnd_row(t, day)
            if not x:
                continue
            me = daily.get(t) if daily else x[1]
            if not me or me <= 0:
                continue
            scored.append((-x[0] / me, t))         # highest RD/ME first
        if len(scored) < 20:
            return None
        scored.sort()
        pick = [t for _, t in scored[:max(1, int(round(len(scored) * frac)))]]
        return {t: 1.0 / len(pick) for t in pick}
    return ni.make_annual(select)


weights = make_weights(0.20)
VARIANTS = {f"top{int(q * 100)}": make_weights(q) for q in (0.10, 0.15, 0.25, 0.30)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="rnd-intensity", variants=VARIANTS, source="sharadar",
        notes=("Chan-Lakonishok-Sougiannis R&D intensity: highest 20% of point-in-time S&P 500 R&D "
               "spenders by rnd (latest ARY, public date <= decision day) / decision-day market value "
               "(Sharadar DAILY), equal weight, rebalanced each June; SPY warm-up; variants top "
               "10/15/25/30%; survivorship-free; promoted from I-2026-11-09-RND"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
