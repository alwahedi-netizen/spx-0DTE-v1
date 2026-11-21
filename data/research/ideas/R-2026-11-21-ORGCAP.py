"""R-2026-11-21-ORGCAP — organization capital (Eisfeldt & Papanikolaou 2013),
the source's own long/short construction, on the point-in-time S&P 500.

Promotes the ledger row I-2026-11-11-ORGCAP (scored 67 on 2026-11-11, "next
stock slot candidate"); same mechanism, first test. New family.
SOURCE: Eisfeldt, A. & Papanikolaou, D. (2013), "Organization Capital and the
Cross-Section of Expected Returns", Journal of Finance 68(4) 1365-1406
(https://www.kellogg.northwestern.edu/academics-research/research/detail/2013/organization-capital-and-the-cross-section-of-expected-returns ;
internet appendix https://dimitris-papanikolaou.github.io/website/assets/papers/OrganizationCapital_APP.pdf).
Headline: firms with more organization capital than their INDUSTRY peers
out-earn firms with less by ~4.7%/yr (JF version; 1970-2008, all Compustat
firms); FF3 alpha ~6%, Carhart alpha ~4.3% (appendix); the spread is not
explained by CAPM/FF3/Carhart. Internet appendix: depreciation 15%, portfolios
re-formed every June, quintiles within industries.
RATIONALE (fixed before any run): organization capital (key talent, processes,
brands built through SG&A spending) is expensed, never booked, and its owners
(key employees) can walk away with part of its cash flows -> shareholders bear
a displacement risk and are paid a premium for it. Lab context, disclosed:
in OUR honest-data tests the only stock signals with factor alpha are the
R&D/intangible-investment ones (RND aT 2.7, RNDREV 2.2, RNDSECT 2.4, RDINC
2.1, RNDQUAL 3.4) — FF5's RMW counts expensed intangible investment as low
profitability. Organization capital is the published SG&A version of that
channel (Compustat XSGA includes R&D), so it is a fair out-of-family test of
whether the channel is real or an R&D accident. Expected failure regime:
2000-02 (high-SG&A tech/pharma fell) and periods when low-OC heavy industry
rallies (2021-22 energy) — within-sector ranking limits the second.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the signal day, priced that
    day, EXCLUDING Sharadar sectors "Financial Services" and "Utilities"
    (the source drops financials and regulated utilities; assumption noted).
  * Organization capital by perpetual inventory on every ARY row public on or
    before the signal day (one row per fiscal period, later restatements win):
        O_0 = SGA_1 / (g + delta),  O_t = (1 - delta) O_{t-1} + SGA_t,
    delta = 15%, g = 10% (source), SGA = sgna + rnd (Sharadar sgna excludes
    R&D; Compustat XSGA, the source's input, includes it). NOT CPI-deflated
    (deviation: nominal flows; with 2-3% inflation this acts like a slightly
    higher delta; a ranking within one date is nearly unaffected).
    Signal = O / assets of the latest ARY row (calendardate <= 18 months old).
  * Each June (last close), within each Sharadar sector with >= 10 ranked
    names: LONG the top 20% by O/assets, SHORT the bottom 20%; equal weight
    inside each leg, long leg +1.0, short leg -1.0 of capital (cash 1.0 earns
    T-bills, short proceeds included — harness fix 2, theme 28). Positions
    drift with prices until next June (dollar positions are not re-hedged).
  * Before the first June book: all T-bills (no position).
  * Variants (robustness gate): delta 10% and 20%; quintile cut 10% and 30%.
  * Benchmark T-bills (market-neutral book), 5bp/side, 2000-01 -> vault,
    strict bar + FF5+Mom factor-alpha gate (asset_class "stocks").
    family "organization-capital" (new): trials = 1 + 4 = 5. Honesty note:
    the CHANNEL was picked after the R&D results (above); if the lead counts
    it inside rnd-intensity instead, trials would be 30.
REPLICATION GATE (rule 1, pre-registered, runs BEFORE evaluate): on the
source's last years that our data covers, 2000-06-30 -> 2008-12-31, the same
book's annualised mean excess return (L/S spread) must be POSITIVE and at
least +2.35%/yr (half of the source's 4.7%/yr = "rough size"). If not, the
script prints "harness/data suspect" and does NOT call evaluate (no test is
spent). Caveat on record: the source's universe is all Compustat firms; ours
is the S&P 500 (large caps; spreads are usually smaller there), and Sharadar
ARY history starts ~1998 so early O stocks lean on the O_0 initialisation.
PASS CRITERION (written before any run): replication gate met AND harness
verdict PASS with every world-class gate (99% confidence Sharpe > T-bills,
held-out last 30% positive and beating T-bills, DSR >= 0.95 at 5 trials,
active t >= 3, 2x costs, >= 70% of variants beat T-bills, FF5+Mom alpha
t >= 2). Learning criterion (shortlist): alpha t >= 2 with |corr| to the
book <= 0.3 (portfolio.marginal, lead).

DATA-TIMING: the trade day is dates[i] (last close of June); the signal reads
dates[i-1]: ARY rows with public `date` <= dates[i-1], S&P 500 membership and
"priced" status on dates[i-1]. px[.][i] is only used to set the drift base.
Weights decided at close i earn close i -> close i+1 (harness). A held name
with no price carries its last price (returns 0, e.g. after delisting).
Runtime: ~1,100 ARY + price queries (shared per-day cache with the other
stock scripts); a 429 back-off wrapper retries Sharadar calls.
"""
import importlib.util
import json
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("accruals_core", _here.with_name("R-2026-11-09-ACCRUALS.py"))
acc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acc)
ag = acc.ag                                       # members(), all_tickers(), fund(), _num()

ID = "R-2026-11-21-ORGCAP"
START = "2000-01-01"
FAMILY = "organization-capital"
TRIALS = 1 + 4
EXCLUDE = {"Financial Services", "Utilities"}
REPL = ("2000-06-30", "2008-12-31", 0.0235)       # window, minimum annual spread

_raw_fetch = rb._sh_fetch


def _patient_fetch(table, params):
    """Sharadar call with back-off on HTTP 429 (shared key, busy Saturdays)."""
    for k in range(20):
        try:
            return _raw_fetch(table, params)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(min(15 * (k + 1), 120))
    return _raw_fetch(table, params)


rb._sh_fetch = _patient_fetch


def org_capital(t, sd, delta=0.15, g=0.10, max_age_m=18):
    """O / assets from ARY rows public <= sd (perpetual inventory), or None."""
    import bisect
    ds, rows = ag.fund(t)
    k = bisect.bisect_right(ds, sd)
    by_fy = {}
    for r in rows[:k]:                            # later public rows win per fiscal period
        fy = (r.get("reportperiod") or r.get("calendardate") or "")[:10]
        if fy:
            by_fy[fy] = r
    if not by_fy:
        return None
    fys = sorted(by_fy)
    last = by_fy[fys[-1]]
    cd = (last.get("calendardate") or last["date"])[:10]
    if ag._months_between(cd, sd) > max_age_m:
        return None
    assets = ag._num(last.get("assets"))
    if not assets or assets <= 0:
        return None
    O, prev = None, None
    for fy in fys:
        r = by_fy[fy]
        sga = max(ag._num(r.get("sgna")) or 0.0, 0.0) + max(ag._num(r.get("rnd")) or 0.0, 0.0)
        if O is None:
            O = sga / (g + delta)
        else:
            n = max(1, round(ag._months_between(prev, fy) / 12))
            O = O * (1 - delta) ** n + sga
        prev = fy
    if O is None or O <= 0:
        return None
    return O / assets


def book(sd, i, px, q=0.20, delta=0.15):
    """{ticker: signed weight}: within-sector top q long (+1 total), bottom q short (-1)."""
    by_sec = {}
    for t in ag.members(sd):
        sec = acc.sector(t)
        if not sec or sec in EXCLUDE or t not in px or px[t][i - 1] is None or px[t][i] is None:
            continue
        x = org_capital(t, sd, delta=delta)
        if x is not None:
            by_sec.setdefault(sec, []).append((x, t))
    longs, shorts = [], []
    for sec, xs in by_sec.items():
        if len(xs) < 10:
            continue
        xs.sort()
        n = max(1, int(round(len(xs) * q)))
        shorts += [t for _, t in xs[:n]]
        longs += [t for _, t in xs[-n:]]
    if len(longs) < 10 or len(shorts) < 10:
        return None
    w = {t: 1.0 / len(longs) for t in longs}
    for t in shorts:
        w[t] = w.get(t, 0.0) - 1.0 / len(shorts)
    return w


def make_weights(q=0.20, delta=0.15):
    """June-rebalanced signed book; dollar positions drift with prices."""
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if (i > 0 and i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
                and dates[i][5:7] == "06"):
            w = book(dates[i - 1], i, px, q, delta)
            if w:
                st["w"], st["base"] = w, {t: px[t][i] for t in w}
                st["last"] = dict(st["base"])
                return dict(w)
        if "w" not in st:
            return {}
        pos = {}
        for t, w0 in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            pos[t] = w0 * st["last"][t] / st["base"][t]
        nav = 1.0 + sum(pos[t] - st["w"][t] for t in pos)   # cash fixed at rebalance
        return {t: v / nav for t, v in pos.items()} if nav > 0 else {}
    return weights


weights = make_weights()
VARIANTS = {"delta10": make_weights(delta=0.10), "delta20": make_weights(delta=0.20),
            "q10": make_weights(q=0.10), "q30": make_weights(q=0.30)}


def universe():
    return ag.all_tickers(START)


def replication(tickers):
    """Source-overlap check: annualised mean L/S excess return 2000-06 -> 2008-12."""
    dates, px = rb.sharadar_prices(tickers, START)
    keep = sum(1 for d in dates if d <= REPL[1])
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(make_weights(), dates, px, rf, rb.COST_BPS["stocks"])
    k0 = next(k for k, d in enumerate(dates[1:]) if d > REPL[0])
    ex = [r - f for r, f in zip(rets[k0:], rf[1 + k0:])]
    ann = sum(ex) / len(ex) * rb.PPY
    t = rb.t_stat(ex)
    return {"window": [dates[1 + k0], dates[-1]], "spread_ann": round(ann, 4),
            "t": round(t, 2), "required": REPL[2], "replicated": ann >= REPL[2]}


if __name__ == "__main__":
    tick = universe()
    rep = replication(tick)
    print("REPLICATION", json.dumps(rep))
    if not rep["replicated"]:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "harness/data suspect: replication gate failed", "replication": rep}))
        sys.exit(0)
    out = rb.evaluate(
        ID, weights, tick, None, start=START, asset_class="stocks", trials=TRIALS,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Eisfeldt-Papanikolaou organization capital: O = perpetual inventory of (sgna + rnd), "
               "delta 15%, g 10%, nominal; O/assets ranked within Sharadar sector (ex Financial Services, "
               "Utilities); June; long top 20% / short bottom 20%, equal weight, +1/-1, drifting; "
               "signal day = day before trade; bench T-bills; variants delta 10/20%, cut 10/30%; "
               f"replication 2000-06..2008-12 spread {rep['spread_ann']} (t {rep['t']}) vs >= 0.0235"))
    out["replication"] = rep
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
