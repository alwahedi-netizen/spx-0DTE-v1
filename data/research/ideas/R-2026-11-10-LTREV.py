"""R-2026-11-10-LTREV — long-term reversal (DeBondt-Thaler): buy the 5-year
losers of the point-in-time S&P 500 (survivorship-free).

Promoted from the queue row I-2026-11-09-LTREV (scored 70 on 2026-11-09).
Same mechanism, first test (single-stock form; the deep-dive rotation #4
"long-term reversal / value" is a different, multi-asset test).
Source: De Bondt & Thaler (1985) "Does the Stock Market Overreact?",
J. Finance 40(3) 793-805
(https://econpapers.repec.org/RePEc:bla:jfinan:v:40:y:1985:i:3:p:793-805);
the skip-a-year formation (t-60 .. t-12, so it does not collide with 12-1
momentum) is the Fama-French (1996) LTR factor definition. Newest support:
arXiv 2611.09834 (Wang-Rachev-Fabozzi, Nov 2026) LTR premium t 2.03 in US
stocks 1973-2024.

RATIONALE (fixed before any run): investors over-extrapolate long runs of bad
news, so stocks that lost the most over several years are priced too
pessimistically and rebound as results mean-revert; year-end tax-loss
selling deepens the discount in December, so formation is the last close of
December. Why it could help THIS book: losers rebound hardest right after
crashes (2003, 2009), the exact window in which trend overlays are out
(theme 13) — a different return timing from the shortlist's trend pieces.
Known risks: the effect is mostly small-cap (we test large caps only), value
traps in secular decline, and FF (1996) explain LTR with HML — the factor
gate may call it value.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the decision day, priced that
    day (Sharadar survivorship-free prices).
  * Decision day: the last close of December each year.
  * Signal: LTR = close(on/before day - 12 months) / close(on/before day -
    60 months) - 1, from the ticker's own Sharadar price history (closeadj),
    using ONLY dates <= decision day; each close is the last one on/before
    its target date (at most 10 days old), else the first one after it (at
    most 5 days later — Sharadar starts 1997-12-31); otherwise not scored.
    The price history is read from the same cached Sharadar query
    sharadar_prices() uses, because the harness clips px at START and a
    60-month look-back needs 1995-1999 data.
  * Hold the LOWEST 10% by LTR, equal weight, for 12 months (to the next
    December); weights drift with prices in between.
  * Need >= 20 scored names, else keep the previous book; before the first
    book hold SPY (warm-up). Sharadar prices start 1997, so the 60-month
    book starts Dec 2002 (36-month variant Dec 2000).
  * Variants (robustness gate): 36- and 48-month formation windows (still
    skipping the last 12 months); lowest 5% and 20%.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha
    gate. family "long-term-reversal" (new): trials = 1 + 4 = 5.
Delisted names: a held stock that delists returns 0 from its last price.
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
ag = ni.ag                                         # ASSETGROW helpers (members, all_tickers)

ID = "R-2026-11-10-LTREV"
START = ni.START
BENCH = ni.BENCH
_PX = {}                                           # ticker -> (sorted dates, closes)


def history(t):
    """Full Sharadar closeadj history — the exact query sharadar_prices() runs."""
    if t not in _PX:
        try:
            rows = rb.sharadar("stocks", None, ticker=t, fields="date,closeadj")
        except Exception:  # noqa: BLE001 — a missing ticker is just no data
            rows = []
        pts = sorted((r["date"][:10], r["closeadj"]) for r in rows if r.get("closeadj"))
        _PX[t] = ([d for d, _ in pts], [p for _, p in pts])
    return _PX[t]


def _shift(day, months):
    """The same calendar day `months` earlier (clamped to that month's length)."""
    import calendar
    y, m = int(day[:4]), int(day[5:7]) - months
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}-{min(int(day[8:10]), calendar.monthrange(y, m)[1]):02d}"


def close_near(t, target, day, before_days=10, after_days=5):
    """Close on/before `target` (<= before_days old), else the first close after
    it (<= after_days later); never a close after the decision day."""
    from datetime import date
    ds, ps = history(t)
    k = bisect.bisect_right(ds, min(target, day)) - 1
    if k >= 0 and (date.fromisoformat(target) - date.fromisoformat(ds[k])).days <= before_days:
        return ps[k]
    j = k + 1
    if j < len(ds) and ds[j] <= day and (date.fromisoformat(ds[j]) - date.fromisoformat(target)).days <= after_days:
        return ps[j]
    return None


def ltr(t, day, months):
    old = close_near(t, _shift(day, months), day)
    recent = close_near(t, _shift(day, 12), day)
    if not old or not recent or old <= 0:
        return None
    return recent / old - 1


def make_weights(frac=0.10, months=60):
    def select(day, i, px):
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None:    # only names priced on the decision day
                continue
            x = ltr(t, day, months)
            if x is not None:
                scored.append((x, t))              # biggest losers first
        if len(scored) < 20:
            return None
        scored.sort()
        pick = [t for _, t in scored[:max(1, int(round(len(scored) * frac)))]]
        return {t: 1.0 / len(pick) for t in pick}
    return ni.make_annual(select, month="12")


weights = make_weights()
VARIANTS = {"win36": make_weights(months=36), "win48": make_weights(months=48),
            "low5": make_weights(0.05), "low20": make_weights(0.20)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="long-term-reversal", variants=VARIANTS, source="sharadar",
        notes=("DeBondt-Thaler long-term reversal: lowest 10% of point-in-time S&P 500 by return from "
               "t-60 to t-12 months (Sharadar closeadj, dates <= decision day), equal weight, formed each "
               "December, held 12 months; SPY warm-up (60-month book from Dec 2002); variants 36/48-month "
               "windows, lowest 5/20%; survivorship-free; promoted from I-2026-11-09-LTREV"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
