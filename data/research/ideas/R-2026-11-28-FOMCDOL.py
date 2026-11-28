"""R-2026-11-28-FOMCDOL — REPLICATION, then the tradeable test: short the dollar
(long a basket of G10 currencies) on scheduled FOMC decision days only, done
with CurrencyShares ETFs at the 16:00 ET close (the source's own sampling).

SOURCE: Mueller, Tahbaz-Salehi & Vedolin, "Exchange Rates and Monetary Policy
Uncertainty", Journal of Finance 72(3), 2017, 1213-1252
(https://researchonline.lse.ac.uk/id/eprint/77256 ; working paper FMG DP-54,
https://www.fmg.ac.uk/sites/default/files/publications/dp-54.pdf).
Numbers read from the paper before any run of ours (1994-01-01 .. 2010-12-31,
136 scheduled announcement days, 9 G10 currencies vs USD, returns sampled
16:00 ET to 16:00 ET):
  * DOL (equal-weight long the 9 currencies vs USD): 12.45bp on announcement
    days (t 2.43) vs ~0.35bp on other days; difference 12.10bp (t 2.34)
    (Table 2, Panels B/C);
  * high-rate portfolio pf3 16.83bp vs 1.67bp (t 2.43); low-rate pf1 5.71bp
    (not significant);
  * "almost the entire return is attributable to the exchange rate change"
    (Table 1, line fx) -> spot returns are enough for the replication;
  * sampled at 14:15 ET or at the 16:00 London fix the effect is NOT
    significant: it needs a close AFTER the 14:00 ET statement.
Independent replication: QuantSeeker, "The FOMC-day puzzle: why every G10
currency..." (2025-12-11, https://www.quantseeker.com/p/the-fomc-day-puzzle-why-every-g10):
1992-2025 daily spot, every G10 currency appreciates vs USD on average on
FOMC days; weak before 2000, larger after (numbers paywalled; not used).

WHY THIS, WHY NOW (theme 31, theme 11, theme 21): G10 FX style premia cannot
clear t >= 3, so the FX budget goes to diversifiers. An 8-days-a-year event
trade in the dollar is about as uncorrelated to the book as anything we can
build. And this hypothesis has NEVER been tested with correct dates:
  * R-2026-11-07-FOMCUSD (family fx-fomc-dollar) was withdrawn 2026-11-10 for
    the start-of-day `=X` error; its 2026-11-11 re-run (Sharpe 0.126) kept the
    script's own `true_day()` +1-day UK-summer shift ON TOP of harness fix 1
    (+3h), which already labels summer bars with the right London date. In
    that re-run 87 of the 165 events (2004-01 .. 2024-10) were measured on the
    day BEFORE the decision (checked from the date logic only, no returns).
    Harness dating verified here on known jumps: USDCHF=X 2015-01-15 (SNB),
    GBPUSD=X 2016-06-24 (Brexit, UK summer), EURUSD=X 2025-04-03 (tariffs,
    summer) all move on the labelled day; FXF/FXB move on the same US dates.
  * L-2026-11-09-FOMCMOVE (same family) imported the same dates: same error.
  This run uses the US-close ETFs, so no `=X` relabelling is involved in the
  P&L at all. Same hypothesis -> same family (fx-fomc-dollar, 10 trials so
  far; this run adds 5 -> the deflated Sharpe sees 15).

HYPOTHESIS (written before any run): (A) a G10-vs-USD basket earns about the
source's FOMC-day premium on the part of the source's sample our data covers;
(B) the premium survives out of the source's sample (2011+) on Schwab-
tradeable ETFs at an honest 3bp per unit of turnover; (C) it is a small,
uncorrelated building block, not a few crisis days.

RULE (fixed before any run):
  * Calendar: the scheduled FOMC decision dates in R-2026-11-07-PREFOMC.py
    (federalreserve.gov; scheduled meetings only, emergency moves excluded;
    the decision day of a 2-day meeting).
  * At the close (16:00 ET) of the trading day BEFORE each decision day: long
    an equal-weight basket of the CurrencyShares trusts FXE (EUR), FXB (GBP),
    FXA (AUD), FXC (CAD), FXF (CHF), FXY (JPY) — whichever have a price on that
    day and the day before — gross 1.0, held for the decision day's bar only
    (close T-1 -> close T, spanning the 14:00 ET statement); otherwise T-bills.
    NZD, SEK and NOK have no listed US ETF (FXS closed); the basket is 6 of
    the source's 9.
  * Benchmark T-bills; asset_class "fx" with cost_bps = 3.0 (the harness's
    ETF rate, above the 2bp spot default; CurrencyShares spreads are 1-5bp);
    2006-07-01 -> VAULT_FROM (FXY joins 2007-02); vault never opened here.
  * Variants (neighbouring windows / instrument): PRE (T-1 and T), POST (T and
    T+1), WIDE (T-1..T+1), UDN (UDN 100% on T only; DXY-weighted short dollar).

PASS CRITERION (pre-registered, three separate questions):
  A. REPLICATION (decides whether evaluate() runs): Yahoo `=X` spot, the
     source's 9 currencies, equal weight long vs USD, every scheduled
     decision day 2004-01-01 .. 2010-12-31 (the overlap of the source's
     1994-2010 sample with our data): at least 40 events AND mean basket
     return >= +6.2bp per event (half the source's 12.45bp; sign and rough
     size, theme 33). Fail -> "HARNESS/DATA SUSPECT", the script prints that
     and STOPS WITHOUT calling evaluate (no trial spent). The ETF basket on
     2006-07 .. 2010-12 is printed alongside for information only.
  B. STRATEGY: the research_bt verdict vs T-bills (§4 + world-class gates:
     99% confidence, held-out win, deflated Sharpe at 15 family trials,
     t >= 3, double costs, >= 70% of variants). Honest expectation: t >= 3
     needs the full source premium to persist (~12bp/event over ~145 events);
     a decayed premium FAILS B.
  C. BUILDING BLOCK (descriptive, development data only, ETF basket, per
     event, net of the 6bp round trip): post-source events (2011-01 ..
     2024-10) mean > 0 with t >= 1.5, AND the 5 best events < 50% of the
     total net P&L of all development events (theme 34: not a few crisis
     days). C holds -> shortlist candidate for the lead's portfolio.marginal;
     C fails -> the FOMC dollar premium is gone or lumpy; family stops here.

DATA-TIMING: the only signal is the scheduled FOMC calendar (published months
ahead). At close i (16:00 ET NYSE bar) the rule reads whether dates[i+1] is a
scheduled decision day (calendar, not prices) and whether each ETF has a
price at i and i-1; weights decided at close i earn close i -> close i+1
(16:00 ET -> 16:00 ET, the source's Panel C sampling, which spans the 14:00 ET
statement). No `=X` bar is read for any trade. The `=X` bars are used ONLY in
the replication measurement (FX on FX, label T = the true ~19:00 ET close of
London day T after harness fixes 1+2, also after the statement), with two
data guards from theme 37: a leg-event is dropped if its prior bar is stale
(the 2008-07-31..08-26 EUR/JPY/NOK hole: price unchanged from the bar
before) or missing on T, or if T or T-1 is a spike-and-revert print (|move|
>= 4% and the next bar reverses >= half of it; a genuine 4% FOMC-day move that
half-reverses would be dropped too, which biases A DOWN, never up). Dropped
leg-events are counted and printed.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-28-FOMCDOL"
FAMILY = "fx-fomc-dollar"
START = "2006-07-01"
COST = 3.0
SOURCE_BP = 12.45                      # MTV 2017 Table 2 Panel B, DOL
REP_FROM, REP_TO = "2004-01-01", "2010-12-31"
POST_FROM = "2011-01-01"

_spec = importlib.util.spec_from_file_location(
    "prefomc", Path(__file__).resolve().parent / "R-2026-11-07-PREFOMC.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FOMC = sorted(_mod.FOMC)
FOMC_SET = set(FOMC)

ETFS = ["FXE", "FXB", "FXA", "FXC", "FXF", "FXY"]
SYMS = ETFS + ["UDN"]
# replication legs: yahoo symbol -> True if quoted as XXXUSD (long currency = long pair)
SPOT = {"EURUSD=X": True, "GBPUSD=X": True, "AUDUSD=X": True, "NZDUSD=X": True,
        "USDJPY=X": False, "USDCHF=X": False, "USDCAD=X": False,
        "USDSEK=X": False, "USDNOK=X": False}


def make(offsets, legs=ETFS):
    """Hold `legs` equal-weight over bar k when bar k is an FOMC decision day
    + o trading days, o in offsets (offsets on the NYSE calendar)."""
    cache = {}

    def hold_set(dates):
        key = (len(dates), dates[0], dates[-1])
        if key not in cache:
            pos = {d: k for k, d in enumerate(dates)}
            hs = set()
            for f in FOMC:
                k = pos.get(f)
                if k is None:
                    continue
                for o in offsets:
                    if 0 <= k + o < len(dates):
                        hs.add(dates[k + o])
            cache.clear()
            cache[key] = hs
        return cache[key]

    def weights(i, dates, px):
        if i < 1 or i + 1 >= len(dates) or dates[i + 1] not in hold_set(dates):
            return {}
        live = [s for s in legs if px[s][i] and px[s][i - 1]]
        return {s: 1.0 / len(live) for s in live} if live else {}
    return weights


weights = make([0])
VARIANTS = {"PRE": make([-1, 0]), "POST": make([0, 1]), "WIDE": make([-1, 0, 1]),
            "UDN": make([0], ["UDN"])}


def _stats(xs):
    n = len(xs)
    if n < 2:
        return {"n": n}
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return {"n": n, "mean_bp": round(m * 1e4, 2), "sd_bp": round(sd * 1e4, 2),
            "t": round(m / sd * math.sqrt(n), 2) if sd else None,
            "hit": round(sum(1 for x in xs if x > 0) / n, 3)}


def _spike(a, b, c):
    """a -> b moves >= 4% and b -> c reverses >= half of it (theme 37)."""
    if not (a and b and c):
        return False
    m1, m2 = b / a - 1, c / b - 1
    return abs(m1) >= 0.04 and m1 * m2 < 0 and abs(m2) >= 0.5 * abs(m1)


# ── A. replication on the source's period (=X spot, 9 currencies) ────────────
def replication():
    syms = sorted(SPOT)
    dates, px = rb.prices(syms, "2003-09-01")
    pos = {d: k for k, d in enumerate(dates)}
    events, dropped, legs_used = [], {"missing_or_stale": 0, "spike": 0}, []
    for f in FOMC:
        if not (REP_FROM <= f <= REP_TO) or f not in pos:
            continue
        k = pos[f]
        if k < 2 or k + 1 >= len(dates):
            continue
        rs = []
        for s, xxxusd in SPOT.items():
            p0, p1, pm, p2 = px[s][k - 1], px[s][k], px[s][k - 2], px[s][k + 1]
            if not (p0 and p1 and pm):
                continue                                   # leg not trading yet
            if p0 == pm or p1 == p0:                       # stale input / missing T (ffilled)
                dropped["missing_or_stale"] += 1
                continue
            r = p1 / p0 - 1 if xxxusd else p0 / p1 - 1     # long the currency vs USD
            if _spike(p0, p1, p2) or _spike(pm, p0, p1):   # bad print on T, or on T-1
                dropped["spike"] += 1                      # theme 37 spike-and-revert
                continue
            rs.append(r)
        if rs:
            events.append(sum(rs) / len(rs))
            legs_used.append(len(rs))
    st = _stats(events)
    ok = st.get("n", 0) >= 40 and st.get("mean_bp", -1e9) >= SOURCE_BP / 2
    out = {"window": [REP_FROM, REP_TO], "source_dol_bp": SOURCE_BP,
           "gate_bp": SOURCE_BP / 2, "spot_basket": st,
           "avg_legs": round(sum(legs_used) / len(legs_used), 2) if legs_used else None,
           "dropped_leg_events": dropped,
           "etf_basket_info_only": _stats(etf_events("2006-07-01", REP_TO)[0]),
           "replicated": bool(ok)}
    out["verdict_replication"] = "REPLICATED" if ok else "HARNESS/DATA SUSPECT"
    return out


# ── per-event ETF basket returns on development data (for A-info and C) ──────
def etf_events(frm, to, legs=ETFS):
    to = min(to, rb.VAULT_FROM)
    dates, px = rb.prices(legs + ["SPY"], START)
    pos = {d: k for k, d in enumerate(dates)}
    ev, spy, when = [], [], []
    for f in FOMC:
        if not (frm <= f <= to) or f >= rb.VAULT_FROM or f not in pos:
            continue
        k = pos[f]
        if k < 2:
            continue
        live = [s for s in legs if px[s][k - 1] and px[s][k - 2] and px[s][k]]
        if not live:
            continue
        ev.append(sum(px[s][k] / px[s][k - 1] - 1 for s in live) / len(live))
        spy.append(px["SPY"][k] / px["SPY"][k - 1] - 1 if px["SPY"][k - 1] else 0.0)
        when.append(f)
    return ev, spy, when


def _corr(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb), 3) if va and vb else None


# ── C. building-block check (net of the 6bp round trip, development only) ────
def block_check():
    rt = 2 * COST / 1e4
    ev, spy, when = etf_events(START, "2099-12-31")
    net = [x - rt for x in ev]
    post = [x for x, d in zip(net, when) if d >= POST_FROM]
    tot = sum(net)
    top5 = sum(sorted(net, reverse=True)[:5])
    st_post = _stats(post)
    out = {"all_events_net": _stats(net),
           "source_overlap_2006_2010_net": _stats([x for x, d in zip(net, when) if d < POST_FROM]),
           "post_source_2011_net": st_post,
           "2011_2017_net": _stats([x for x, d in zip(net, when) if POST_FROM <= d < "2018-01-01"]),
           "2018_dev_end_net": _stats([x for x, d in zip(net, when) if d >= "2018-01-01"]),
           "total_net_pct": round(tot * 100, 2),
           "top5_share": round(top5 / tot, 3) if tot > 0 else None,
           "best5": sorted(zip(when, [round(x * 1e4, 1) for x in net]), key=lambda t: -t[1])[:5],
           "worst5": sorted(zip(when, [round(x * 1e4, 1) for x in net]), key=lambda t: t[1])[:5],
           "corr_spy_same_day": _corr(ev, spy),
           "udn_gross_info_only": _stats(etf_events(START, "2099-12-31", ["UDN"])[0])}
    out["building_block_C"] = bool(st_post.get("n", 0) >= 20 and st_post.get("mean_bp", -1) > 0
                                   and (st_post.get("t") or 0) >= 1.5
                                   and tot > 0 and top5 / tot < 0.50)
    return out


if __name__ == "__main__":
    rep = replication()
    print(json.dumps({"id": ID, "replication": rep}, indent=1))
    if not rep.get("replicated"):
        print(json.dumps({"id": ID, "verdict": "NOT RUN",
                          "reason": "replication failed -> harness/data suspect; evaluate() not "
                                    "called, no trial spent"}))
        sys.exit(0)
    r = rb.evaluate(ID, weights, SYMS, None, start=START, asset_class="fx",
                    cost_bps=COST, trials=1, family=FAMILY, variants=VARIANTS,
                    notes="REPLICATION of Mueller-Tahbaz-Salehi-Vedolin (JF 2017) FOMC-day "
                          "short-dollar premium (DOL 12.45bp/event 1994-2010); tradeable form: "
                          "equal-weight FXE/FXB/FXA/FXC/FXF/FXY held close T-1 -> close T on "
                          "scheduled FOMC decision days (16:00 ET, the source's sampling), else "
                          "T-bills; 3bp; 2006-07 -> vault; variants PRE/POST/WIDE windows + UDN; "
                          "re-test of fx-fomc-dollar after the FOMCUSD summer double-shift "
                          "(87/165 events on the wrong day)")
    r["replication"] = rep
    try:
        r["building_block"] = block_check()
    except Exception as e:                 # noqa: BLE001 — report, never hide
        r["building_block"] = {"error": repr(e)}
    print(json.dumps(r, indent=1))
