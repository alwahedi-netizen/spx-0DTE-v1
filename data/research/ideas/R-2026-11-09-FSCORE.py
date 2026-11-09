"""R-2026-11-09-FSCORE — Piotroski F-score inside the cheapest fifth of the
point-in-time S&P 500 (survivorship-free), long-only.

Promoted from the queue row I-2026-11-08-FSCORE (scored 65 on 2026-11-08).
Same mechanism, first test.
Source: Piotroski (2000) "Value Investing: The Use of Historical Financial
Statement Information to Separate Winners from Losers", J. Accounting
Research 38 (supplement) 1-41
(https://econpapers.repec.org/RePEc:bla:joares:v:38:y:2000:i::p:1-41).
Independent large-cap check BEFORE our run: Quanter Lab 2026-09-12 ("Does the
Piotroski F-score have anything to find among large caps?", point-in-time
S&P 500, July anchors 2000-2026): the high-score (8-9) book trailed every
scored member (10.9% vs 12.1%/window), and within the cheapest fifth high
scorers trailed their own fifth (9.2% vs 9.9%). EXPECTATIONS ARE LOW: the
paper's edge lives in small, neglected value stocks, and the S&P 500 is the
opposite. Tested because it was queued and to measure, not to hope.

RATIONALE (fixed before any run): cheap stocks are cheap for a reason; most
are value traps. Simple accounting signals of improving health (profits,
cash, falling leverage, better margins, no dilution) pick the cheap firms
whose fundamentals are turning, which the market prices slowly.

RULE (fixed before any run; exactly the I- row's rule):
  * Universe: point-in-time S&P 500 members on the decision day, Sharadar
    survivorship-free prices; only names priced on the decision day.
  * Decision day: the last close of June each year.
  * Data: the latest ARY row whose public `date` <= decision day (calendardate
    <= 18 months old) and the prior fiscal-year ARY row (9-15 months
    earlier); netinc, ncfo, assets must exist in both or the name is skipped.
  * Value screen: B/M = equity / marketcap of the latest row (equity > 0);
    keep the top 20% by B/M of the names that pass the data check.
  * F-score (one point each; a signal with a missing input scores 0):
      ROA = netinc/assets > 0; CFO = ncfo/assets > 0; ROA up on the prior
      year; ncfo > netinc; debtnc/assets down; currentratio up; sharesbas not
      up (no dilution); gross margin gp/revenue up; turnover revenue/assets up.
  * Hold the cheap names with F >= 8, equal weight; if fewer than 5 qualify,
    add F = 7 names (best B/M first) up to 5. Hold to next June; weights drift.
  * Before the first June decision: hold SPY (warm-up).
  * Variants (robustness gate): cheapest 15%, 25%, 30% with F >= 8; cheapest
    20% with F >= 7.
  * Benchmark SPY, 5bp/side, 2000-01 -> vault, strict bar + FF5+Mom alpha.
    family "fscore" (new): trials = 1 + 4 = 5. (Quanter Lab's prior search on
    the same index is an external trial we cannot count — noted.)
Banks mostly drop out on their own (no current ratio / gross margin -> they
cannot reach 8). Zero long-term debt in both years scores 0 on leverage (no
decrease) — strict reading of the rule, noted.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("netiss", Path(__file__).with_name("R-2026-11-09-NETISS.py"))
ni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ni)
ag = ni.ag

ID = "R-2026-11-09-FSCORE"
START = ni.START
BENCH = ni.BENCH


def _ratio(a, b):
    return a / b if a is not None and b else None


def _up(x1, x0):
    return 1 if x1 is not None and x0 is not None and x1 > x0 else 0


def fscore_row(t, day):
    """(B/M, F-score) or None."""
    pair = ni.two_rows(t, day)
    if not pair:
        return None
    r, p = pair
    n = ag._num
    ni1, ni0, cf1, a1, a0 = n(r.get("netinc")), n(p.get("netinc")), n(r.get("ncfo")), n(r.get("assets")), n(p.get("assets"))
    eq, mc = n(r.get("equity")), n(r.get("marketcap"))
    if None in (ni1, ni0, cf1) or n(p.get("ncfo")) is None or not a1 or not a0 or a1 <= 0 or a0 <= 0:
        return None
    if not eq or eq <= 0 or not mc or mc <= 0:
        return None
    roa1, roa0 = ni1 / a1, ni0 / a0
    f = (roa1 > 0) + (cf1 / a1 > 0) + (roa1 > roa0) + (cf1 > ni1)
    l1, l0 = _ratio(n(r.get("debtnc")), a1), _ratio(n(p.get("debtnc")), a0)
    f += 1 if l1 is not None and l0 is not None and l1 < l0 else 0
    f += _up(n(r.get("currentratio")), n(p.get("currentratio")))
    s1, s0 = n(r.get("sharesbas")), n(p.get("sharesbas"))
    f += 1 if s1 and s0 and s1 <= s0 else 0
    f += _up(_ratio(n(r.get("gp")), n(r.get("revenue"))), _ratio(n(p.get("gp")), n(p.get("revenue"))))
    f += _up(_ratio(n(r.get("revenue")), a1), _ratio(n(p.get("revenue")), a0))
    return eq / mc, int(f)


def make_weights(frac=0.20, fmin=8, nmin=5):
    def select(day, i, px):
        scored = []
        for t in ag.members(day):
            if t not in px or px[t][i] is None:
                continue
            x = fscore_row(t, day)
            if x:
                scored.append((-x[0], t, x[1]))      # cheapest (highest B/M) first
        if len(scored) < 50:
            return None
        scored.sort()
        cheap = scored[:max(1, int(round(len(scored) * frac)))]
        pick = [t for _, t, f in cheap if f >= fmin]
        if len(pick) < nmin:
            pick += [t for _, t, f in cheap if f == fmin - 1][:nmin - len(pick)]
        if not pick:
            return None
        return {t: 1.0 / len(pick) for t in pick}
    return ni.make_annual(select)


weights = make_weights()
VARIANTS = {"cheap15": make_weights(0.15), "cheap25": make_weights(0.25),
            "cheap30": make_weights(0.30), "f7": make_weights(0.20, 7)}


if __name__ == "__main__":
    import json
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=5,
        family="fscore", variants=VARIANTS, source="sharadar",
        notes=("Piotroski F-score >= 8 within the cheapest 20% (equity/marketcap) of the point-in-time "
               "S&P 500 (Sharadar ARY, public date <= decision day), equal weight, rebalanced each June; "
               "SPY warm-up; variants cheapest 15/25/30%, F>=7; survivorship-free; promoted from "
               "I-2026-11-08-FSCORE; Quanter Lab's PIT test found no large-cap edge"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
