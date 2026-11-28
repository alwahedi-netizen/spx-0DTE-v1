"""L-2026-11-28-CURVESPREAD — the oil / natural-gas curve signal traded as a
SPREAD (front ETF vs 12-month-ladder ETF of the same commodity), market-neutral.
League round 3 (2026-11-28), commodities desk. Lab original (RESEARCH.md §2b).
New ledger row; varies L-2026-11-07-CARRYPROXY (potential 4: USO only while
USO's 63-day return beats USL's) and L-2026-11-09-CURVEPAIRS (same signal on
oil AND gas, long-only front: FAIL, -3.2%/yr, the gas front's drift sank it).

WHY THIS TEST (written before any run): every curve test so far held the FRONT
ETF outright, so its result was mostly the commodity's own price drift (oil and
gas fell hard 2014-20) with the curve signal on top. The source mechanism is a
statement about the CURVE: Boons & Porras Prado, "Basis-Momentum", JF 74(1)
2019 (https://ideas.repec.org/a/bla/jfinan/v74y2019i1p239-279.html) define
basis-momentum as momentum in the nearby contract minus momentum in a deferred
contract and find it predicts BOTH the spot premium and the TERM premium
(returns of nearby-minus-deferred spread positions). Our ETF pair is the same
object: USO / UNG hold the front month, USL / UNL hold an equal-weight 12-month
ladder (same sponsor, USCF), so "front 63d return minus ladder 63d return" is a
price-only basis-momentum proxy, and "front minus ladder" next month is the
term-premium (spreading) return. Trading the spread removes the commodity's
drift and asks the question the source actually answers.
NOT A REPLICATION: the paper's headline (futures, 1959-2014, cross-section of
~20 commodities) cannot be reproduced with ETFs that list 2007-2010; this is a
lab test of the mechanism on the only two commodities with a front ETF and a
ladder ETF from the same sponsor. No published ETF headline exists to match.

HYPOTHESIS (written before any run): when the front has out-run the ladder over
the last quarter (curve tightening: falling inventories), it keeps out-running
it next month; when the ladder has out-run the front (contango deepening), the
front keeps lagging. A long-front/short-ladder position in the first state and
long-ladder/short-front in the second earns a positive excess return over
T-bills on both commodities, and the signal earns more than simply always
holding long-ladder/short-front (the static contango harvest).

PASS CRITERION (pre-registered): research_bt verdict PASS vs T-bills (bench
None: dollar-neutral book), all §0 gates with the family's lifetime trials
(20 + 1 + 4 = 25), >= 70% of the 4 window neighbours above T-bills.
SIGNAL READ-OUT (pre-registered, printed separately; rb.simulate on the same
calendar, no result file, no trial):
  CURVE SIGNAL         signal book Sharpe > static book Sharpe AND each pair
                       alone (signal rule) has Sharpe > 0;
  STATIC ROLL PREMIUM  static book Sharpe >= signal book Sharpe (the money is
                       the permanent contango spread, not the signal);
  NO EDGE              signal book Sharpe <= 0;
  MIXED                anything else.
  Also printed: signal book Sharpe before / after 2020-05-01 (USO changed its
  roll method in 2020-04 and now spreads its holdings across months, which
  shrinks the USO-USL gap — CARRYPROXY's learnings flag this).

RULE (fixed before any run):
  at each month-end close i (next bar falls in a new month):
    for each pair (front, ladder) in [(USO, USL), (UNG, UNL)]:
      need front and ladder priced at i and at i-63, else that pair is in
      T-bills this month (its weights stay 0)
      g = front[i]/front[i-63] - ladder[i]/ladder[i-63]
      g > 0: front +0.5, ladder -0.5      (curve tightening: long the front)
      g < 0: front -0.5, ladder +0.5      (contango deepening: long the ladder)
      g = 0: pair in T-bills
  SIZING (checked in code by an assert and printed as an audit): each pair is
  +0.5 on one leg and -0.5 on the other, so with both pairs live the book is
  100% long / 100% short (gross 2.0, net 0.0), equal CAPITAL per pair (not equal
  risk — the gas spread is the more volatile and will carry more of the risk;
  stated before the run). A pair alone (diagnostic) is +-0.5, rest T-bills.
  Held to the next month-end. Capital and short proceeds earn T-bills (harness
  fix 2; a retail account would not earn T-bills on short proceeds — the edge
  must clear that, stated).
Benchmark: T-bills (bench None). Costs 10bp per unit of turnover (USL and UNL
are thin ETFs with wider spreads than the desk's 5bp default). NO borrow fee
modelled: USO/UNG borrow cheaply most of the time; USL/UNL (shorted only in
curve-tightening months) may be hard to borrow — optimistic, stated; the
double-cost gate is the only haircut. Capacity is tiny (UNL AUM ~$10-20m).
Start 2010-01-04 (UNL's first Yahoo bar; both pairs go live together at the
first month-end with 63 bars, ~2010-04). Ends at the vault (2024-10-31).
Includes 2014-16, the 2020 negative-oil episode and the 2021-22 gas spike.
DATA-TIMING: the signal reads only closes dated <= the decision close i (bars
i and i-63; harness look-ahead guard); no FX or side data (theme 30 does not
apply); the month-end test peeks only at dates[i+1]'s MONTH; weights decided at
close i earn close i -> close i+1.
Variants (neighbours of the window, the same set CARRYPROXY / CURVEPAIRS used,
not re-chosen): 21, 42, 126, 189 days.
FAMILY "L-2026-11-07-CARRYPROXY" (same hypothesis: the oil/gas curve signal)
-> lifetime trials 20 + 1 + 4 = 25. One evaluate() call; the read-out books are
rb.simulate() controls (no result file, no trial).
Data checked 2026-11-28 (prices only): USO 2006-04, USL 2007-12, UNG 2007-04,
UNL 2010-01-04 on Yahoo; no split artefacts (all >12% daily moves are real
2018-11 gas / 2020 oil days); UNL has 123 unchanged-close days of 3,733 (thin;
a 63-day return is barely affected).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

PAIRS = [("USO", "USL"), ("UNG", "UNL")]
SYMS = [s for p in PAIRS for s in p]
START = "2010-01-04"
LB = 63
LEG = 0.5            # per leg, per pair: +0.5 / -0.5  (header: 100% long / 100% short with both pairs)
AUDIT = {"max_long": 0.0, "max_short": 0.0, "max_abs_net": 0.0, "months": 0, "months_both_live": 0}


def make(lb=LB, pairs=PAIRS, mode="signal", audit=False):
    """mode 'signal' = the rule; 'static' = always long ladder / short front (control)."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        w = {}
        live = 0
        if i >= lb:
            for f, l in pairs:
                a, b = px[f], px[l]
                if not (a[i] and a[i - lb] and b[i] and b[i - lb]):
                    continue
                if mode == "static":
                    sgn = -1
                else:
                    g = a[i] / a[i - lb] - b[i] / b[i - lb]
                    if g == 0:
                        continue
                    sgn = 1 if g > 0 else -1
                w[f] = w.get(f, 0.0) + sgn * LEG
                w[l] = w.get(l, 0.0) - sgn * LEG
                live += 1
        long_ = sum(x for x in w.values() if x > 0)
        short = -sum(x for x in w.values() if x < 0)
        assert long_ <= 1.0 + 1e-9 and short <= 1.0 + 1e-9 and abs(long_ - short) < 1e-9, w
        if audit:
            AUDIT["months"] += 1
            AUDIT["months_both_live"] += int(live == len(pairs))
            AUDIT["max_long"] = max(AUDIT["max_long"], round(long_, 6))
            AUDIT["max_short"] = max(AUDIT["max_short"], round(short, 6))
            AUDIT["max_abs_net"] = max(AUDIT["max_abs_net"], round(abs(long_ - short), 9))
        st["w"] = w
        return w
    return weights


weights = make()


def _sh(r, rf):
    return round(rb.sharpe(r, rf), 3) if len(r) > 20 else None


if __name__ == "__main__":
    variants = {f"lb{k}": make(k) for k in (21, 42, 126, 189)}
    res = rb.evaluate("L-2026-11-28-CURVESPREAD", weights, SYMS, None, start=START,
                      cost_bps=10.0, asset_class="commodities", trials=25,
                      family="L-2026-11-07-CARRYPROXY", variants=variants,
                      notes="month-end: for (USO,USL) and (UNG,UNL): if front 63d return > ladder 63d return "
                            "front +0.5 / ladder -0.5, else front -0.5 / ladder +0.5 (100% long / 100% short "
                            "with both pairs, net 0, T-bills on capital and short proceeds); bench T-bills; 10bp; "
                            "no borrow fee; basis-momentum spreading form of L-2026-11-07-CARRYPROXY (lab)")
    print(json.dumps(res, indent=1))

    # pre-registered read-out on the identical calendar (same vault cut as evaluate)
    dates, px = rb.prices(SYMS, START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    rf1 = rf[1:]
    books = {"signal": make(audit=True), "static": make(mode="static"),
             "oil_pair_signal": make(pairs=[PAIRS[0]]), "gas_pair_signal": make(pairs=[PAIRS[1]])}
    out, rets = {}, {}
    for name, fn in books.items():
        r, _ = rb.simulate(fn, dates, px, rf, 10.0)
        rets[name] = r
        out[name] = {"sharpe": _sh(r, rf1), "cagr": round(rb.cagr(r), 4), "maxdd": round(rb.max_dd(r), 4)}
    cut = sum(1 for d in dates[1:] if d < "2020-05-01")
    r = rets["signal"]
    out["signal_pre_2020_05"] = _sh(r[:cut], rf1[:cut])
    out["signal_post_2020_05"] = _sh(r[cut:], rf1[cut:])
    s_sig, s_sta = out["signal"]["sharpe"], out["static"]["sharpe"]
    pairs_pos = all((out[k]["sharpe"] or 0) > 0 for k in ("oil_pair_signal", "gas_pair_signal"))
    if s_sig is None or s_sig <= 0:
        read = "NO EDGE"
    elif s_sta is not None and s_sta >= s_sig:
        read = "STATIC ROLL PREMIUM"
    elif pairs_pos:
        read = "CURVE SIGNAL"
    else:
        read = "MIXED"
    print(json.dumps({"signal_readout": read, "controls": out,
                      "sizing_audit (header: max_long 0.5 per pair, 1.0 book; max_short 1.0; net 0)": AUDIT,
                      "carryproxy_reference": {"cagr": 0.0553, "sharpe": 0.317, "confidence": 0.9774},
                      "curvepairs_reference": {"cagr": -0.0325, "sharpe": -0.174}}, indent=1))
