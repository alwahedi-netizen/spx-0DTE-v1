"""I-2026-11-21-CORRMOMSGL — independent-universe confirmation of the commodity
correlation switch (momentum when the market moves together, reversal when it
decouples) on SINGLE-commodity ETFs. League round 2, commodities desk.
Varies R-2026-11-14-CORRMOMREV (PROMISING near-miss, 99.86%, failed only
t >= 3 at 2.99; red team: the published setting is the best of its grid,
honest Sharpe ~0.3-0.45). New ledger row; same family (same hypothesis).

WHY THIS TEST (written before any run): re-running CORRMOMREV with tweaks on
the same four DB sector ETFs would only add trials to a fitted setting. The
legitimate next step is an out-of-universe check: SAME rule, SAME published
parameters, a universe the round-1 result never saw. Nothing is re-fitted.
The universe is NOT chosen by us: it is the 10 single-commodity ETFs of
Quantpedia, "Commodity Portfolio Strategy for a Potential 2026 Inflationary
and Supply Shock Regime" (2026-04-29)
https://quantpedia.com/commodity-portfolio-strategy-for-a-potential-2026-inflationary-and-supply-shock-regime/
(CANE, CPER, CORN, GLD, PALL, PPLT, SLV, SOYB, USO, WEAT — also the lab's
standard 10 of CMDSKEW/CMDBAB/HEDGEPRESS, fixed long before this test).
How independent it is (stated honestly): different instruments and a
within-sector cross-section (gold vs silver vs platinum, corn vs wheat vs
soy) instead of across four sectors, so the long/short pairs are mostly
different bets; but the calendar overlaps (2011-2024 here vs 2008-2024) and
the same macro episodes drive both (2014-16, 2020, 2022). A pass is
corroboration on new instruments, not a new period. A new period would need
pre-2007 data we do not have (GSCI sector indices on Yahoo carry one bar).

Source of the rule: Pauchlyova (with Vojtko), "How to Improve Commodity
Momentum Using Intra-Market Correlation", Quantpedia 2024-09-16
https://quantpedia.com/how-to-improve-commodity-momentum-using-intra-market-correlation/
(SSRN 4964417). Replication on the source's own universe = round 1
(R-2026-11-14-CORRMOMREV vs control R-2026-11-14-CORRMOMCTL: reproduced,
sign only — the source's tables are images). Counter-evidence: Fan & Zhang,
SSRN 6247358 (2026-02): momentum does WORSE in high-comovement regimes.

HYPOTHESIS (written before any run): when commodities suddenly move together
(short-term average pairwise correlation above its long-term level) a common
macro driver is trending and relative momentum persists; when they decouple,
idiosyncratic shocks dominate and overreact, so the 12-month winners lag the
losers next month. If the mechanism is real and not an artefact of four DB
sector funds, it must also show up across single-commodity ETFs.

PASS CRITERION (pre-registered): research_bt verdict PASS vs T-bills (bench
None: market-neutral long-short), all §0 gates with the family's lifetime
trials (5 + 5 = 10), >= 70% of the 4 window neighbours above T-bills.
CONFIRMATION READ-OUT (pre-registered, printed separately; this is the
question the run answers for CORRMOMREV's shortlist entry):
  CONFIRMS      harness confidence >= 0.90 AND the switched book's Sharpe
                beats BOTH unconditional legs on the same universe/dates
                (always-momentum and always-reversal, rb.simulate controls);
  PARTIAL       Sharpe > 0 and beats both legs, confidence < 0.90;
  NOT CONFIRMED anything else (CORRMOMREV's potential should then drop from
                4 to 3 and its vault test should not be spent).
  Also printed (diagnostic, no extra trial): mean monthly return of the
  momentum spread (long top half / short bottom half) in high- vs
  low-correlation months — the switch needs it higher in high-corr months.

RULE (fixed before any run; CORRMOMREV's rule generalised from 4 names):
  at each month-end close i (next bar falls in a new month):
    eligible = the 10 ETFs priced on every bar i-252 .. i (and i-L .. i for
               the long correlation window L); need >= 4 eligible (the
               source's minimum cross-section) else T-bills
    mom_s    = px_s[i] / px_s[i-252] - 1
    c(W)     = mean pairwise correlation of the eligible ETFs' daily returns
               over the last W returns (bars i-W+1 .. i)
    k        = floor(N/2) (N eligible; the middle name sits out when N is odd;
               the source's "2 of 4" = halves)
    if c(20) > c(250): long the k highest mom, short the k lowest
    else:              long the k lowest mom,  short the k highest
    each long +0.5/k, each short -0.5/k (100% long / 100% short, net 0;
    capital and short proceeds earn T-bills — harness fix 2). Ties by name.
  held to the next month-end.
Benchmark: T-bills (bench None). Costs 5bp per unit of turnover. NO borrow
fee modelled: GLD/SLV/USO/PPLT/PALL borrow cheaply, but the small Teucrium
funds (CANE, SOYB, WEAT, CORN) can be hard to borrow — optimistic, stated;
the double-cost gate is the only haircut.
Start 2010-01-04 (PPLT/PALL list 2010-01-08): first signal ~2011-01 with 5
names (GLD, SLV, USO, PPLT, PALL), 6 from mid-2011 (CORN), 10 from late 2012
(WEAT/SOYB/CANE/CPER). 2010 is T-bills. Ends at the vault (2024-10-31).
DATA TIMING: reads closes dated <= i only (harness guard; no FX or side data,
so theme 30 does not apply); the month-end test peeks only at dates[i+1]'s
MONTH; weights decided at close i earn close i -> close i+1.
Variants (the same neighbours as round 1, not re-chosen): short window 10 /
40 days, long window 125 / 500 days (500 starts ~2012).
FAMILY "cmd-corr-momrev" (same hypothesis as CORRMOMREV) -> lifetime trials
5 + 1 + 4 = 10. One evaluate() call; the two controls are rb.simulate()
read-outs (no result file, no trial — the source's own comparison).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

UNIV = ["CANE", "CPER", "CORN", "GLD", "PALL", "PPLT", "SLV", "SOYB", "USO", "WEAT"]
START = "2010-01-04"
MOM = 252
MIN_N = 4


def _rets(col, i, w):
    out = []
    for k in range(i - w + 1, i + 1):
        a, b = col[k - 1], col[k]
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


def avg_corr(px, names, i, w):
    rs = {s: _rets(px[s], i, w) for s in names}
    if any(v is None for v in rs.values()):
        return None
    cs = []
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            c = _corr(rs[names[a]], rs[names[b]])
            if c is None:
                return None
            cs.append(c)
    return sum(cs) / len(cs) if cs else None


def eligible(px, i, need):
    out = []
    for s in UNIV:
        col = px[s]
        if all(col[k] for k in range(i - need, i + 1)):
            out.append(s)
    return out


def mom_order(px, names, i):
    mom = {s: px[s][i] / px[s][i - MOM] - 1 for s in names}
    return sorted(names, key=lambda s: (-mom[s], s))     # best first


def regime(px, names, i, short, long):
    """True = momentum regime (c_short > c_long), False = reversal, None = n/a."""
    cs, cl = avg_corr(px, names, i, short), avg_corr(px, names, i, long)
    return None if (cs is None or cl is None) else cs > cl


def make(short=20, long=250, mode="switch"):
    """mode: 'switch' (the rule), 'mom' (always momentum), 'rev' (always reversal)."""
    need = max(MOM, long + 1, short + 1)
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        w = {}
        if i >= need:
            names = eligible(px, i, need)
            if len(names) >= MIN_N:
                order = mom_order(px, names, i)
                k = len(names) // 2
                reg = regime(px, names, i, short, long) if mode == "switch" else (mode == "mom")
                if reg is not None:
                    best, worst = order[:k], order[-k:]
                    lo, sh = (best, worst) if reg else (worst, best)
                    w = {s: 0.5 / k for s in lo}
                    w.update({s: -0.5 / k for s in sh})
        st["w"] = w
        return w
    return weights


weights = make()


def regime_split(dates, px):
    """Diagnostic: next-month return of the momentum spread by regime (closes <= i
    for the signal; the outcome is the following month, read after the fact)."""
    ends = [i for i in range(len(dates) - 1) if dates[i + 1][:7] != dates[i][:7]]
    need = max(MOM, 251)
    hi, lo = [], []
    for a, b in zip(ends, ends[1:]):
        if a < need:
            continue
        names = eligible(px, a, need)
        if len(names) < MIN_N:
            continue
        reg = regime(px, names, a, 20, 250)
        if reg is None:
            continue
        order = mom_order(px, names, a)
        k = len(names) // 2
        r = {s: px[s][b] / px[s][a] - 1 for s in names}
        spread = sum(r[s] for s in order[:k]) / k - sum(r[s] for s in order[-k:]) / k
        (hi if reg else lo).append(spread)
    m = lambda x: round(sum(x) / len(x), 5) if x else None
    return {"high_corr_months": len(hi), "high_corr_mean_mom_spread": m(hi),
            "low_corr_months": len(lo), "low_corr_mean_mom_spread": m(lo)}


if __name__ == "__main__":
    variants = {"short10": make(10, 250), "short40": make(40, 250),
                "long125": make(20, 125), "long500": make(20, 500)}
    res = rb.evaluate("I-2026-11-21-CORRMOMSGL", weights, UNIV, None, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=10,
                      family="cmd-corr-momrev", variants=variants,
                      notes="month-end: Quantpedia's 10 single-commodity ETFs (point-in-time eligible, >= 4); if mean "
                            "pairwise corr(20d) > corr(250d) long top half / short bottom half by 252-day return, "
                            "else the reverse; +-0.5 per side, net 0, T-bills on capital and short proceeds; bench "
                            "T-bills; 5bp; no borrow fee; out-of-universe confirmation of R-2026-11-14-CORRMOMREV "
                            "(same rule and windows, nothing re-fitted)")
    print(json.dumps(res, indent=1))

    # pre-registered controls on the identical calendar (same cut as evaluate)
    dates, px = rb.prices(UNIV, START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    sh = {}
    for name, fn in (("switch", make()), ("always_mom", make(mode="mom")), ("always_rev", make(mode="rev"))):
        r, _ = rb.simulate(fn, dates, px, rf, 5.0)
        sh[name] = {"sharpe": round(rb.sharpe(r, rf[1:]), 3), "cagr": round(rb.cagr(r), 4),
                    "maxdd": round(rb.max_dd(r), 4)}
    beats = sh["switch"]["sharpe"] > max(sh["always_mom"]["sharpe"], sh["always_rev"]["sharpe"])
    conf = res.get("confidence", 0)
    if conf >= 0.90 and beats:
        read = "CONFIRMS"
    elif sh["switch"]["sharpe"] > 0 and beats:
        read = "PARTIAL"
    else:
        read = "NOT CONFIRMED"
    print(json.dumps({"confirmation_readout": read, "confidence": conf, "controls": sh,
                      "regime_split": regime_split(dates, px),
                      "corrmomrev_round1": {"sharpe": 0.708, "confidence": 0.9986, "active_t": 2.99}}, indent=1))
