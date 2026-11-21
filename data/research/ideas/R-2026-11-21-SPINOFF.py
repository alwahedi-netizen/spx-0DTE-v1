"""R-2026-11-21-SPINOFF — buy every newly spun-off U.S. subsidiary and hold it
22 months (McConnell, Sibley & Xu 2015), survivorship-free Sharadar data.

New row, new mechanism for the ledger (corporate spin-offs; no earlier row
uses the Sharadar ACTIONS spin-off records, which list delisted parents and
subsidiaries: ~10-40 events a year, 1998+).
SOURCE: McConnell, J., Sibley, S. & Xu, W. (2015), "The Stock Price
Performance of Spin-Off Subsidiaries, Their Parents, and the Spin-Off ETF,
2001-2013", Journal of Portfolio Management 42(1) 143-152
(https://business.purdue.edu/faculty/mcconnell/publications/The%20Stock%20Price...2013%20jpm.2015.42.1.143.pdf).
Headline (read from the paper): 146 U.S. non-REIT spin-off events 2001-2012
(CRSP + Mergent); over the first 22 months an equal-weight portfolio of
subsidiaries earned 1.26%/month raw, +0.72%/month over size/market-to-book
benchmarks (cumulative +17.1%); the all-subsidiary 22-month portfolio
returned +137.0% from 2006-12-18 to 2013-12-31 vs +52.2% for the CRSP
value-weighted market (and +92.9% for the spin-off ETF CSD). Earlier
evidence: Cusatis-Miles-Woolridge (1993) and McConnell-Ovtchinnikov (2004),
1965-2000. The authors' own caveat: "what worked in the past will not
necessarily work in the future" (CSD lagged the market after 2015).
RATIONALE (fixed before any run): parent shareholders receive shares they
did not choose (index funds and mandate-bound holders sell: the subsidiary is
too small, the wrong sector, not in their index), analysts are slow to
cover it, and focused management improves operations -> early selling
pressure, then outperformance as the firm is rediscovered.
Expected failure regime: small/mid-cap and value-hostile stretches (2017-20
mega-cap growth) — the strategy is a concentrated small/mid-cap book.

RULE (fixed before any run):
  * Events: Sharadar ACTIONS rows action="spinoff", ex date 1998-01-01 ->
    vault, `contraticker` = the subsidiary. Keep a subsidiary only if (from
    the Sharadar TICKERS table, stocks rows): category starts "Domestic
    Common Stock"; exchange NYSE / NASDAQ / NYSEMKT / AMEX / BATS / NYSEARCA
    (no OTC); industry does not start "REIT" (the source drops REITs); its
    firstpricedate is no more than 10 days after the ex date and no more
    than 400 days before it (newly independent firms; this drops reverse
    Morris trust mergers into long-listed companies). Several share classes
    of the same subsidiary on the same date count once (the class with the
    longest price history).
  * Entry: the first close on/after the ex date at which the subsidiary has
    a Sharadar price, if that is within 10 calendar days of the ex date.
    Exit: the first close on/after the same day-of-month 22 months later
    (source: "through the same numerical date of the Mth month").
  * Portfolio: equal weight across live subsidiaries, re-equalised whenever
    a name enters or leaves and at each month's first close; weights drift
    in between. A name with no price for 5 straight bars (delisted, e.g.
    acquired) leaves at its last price. No live name -> hold the benchmark.
  * Variants (robustness gate): hold 12, 15, 27, 36 months (the source's
    tabled horizons around 22).
  * Benchmark MDY (S&P MidCap 400 ETF, Yahoo, adj. close): a size-matched,
    tradeable stand-in for the source's size/market-to-book benchmark and the
    equal-weight lesson of theme 29 (SPY would flatter a small/mid book).
    Costs 10bp per unit of turnover (RESEARCH §4: small caps >= 10bp).
    2000-01 -> vault, strict bar + FF5+Mom factor-alpha gate (stocks).
    family "spinoffs" (new): trials = 1 + 4 = 5.
REPLICATION GATE (rule 1, pre-registered, runs BEFORE evaluate): on the
source's own window 2006-12-18 -> 2013-12-31, the 22-month book's cumulative
return minus SPY's (Yahoo adj. close, stand-in for the CRSP VW market) must
be >= +42.4 percentage points (half of the source's 137.0 - 52.2 = 84.8)
and the book's own cumulative return must be positive. If not, the script
prints "harness/data suspect" and does NOT call evaluate. Differences on
record: our event list is Sharadar's (2001-2012: ~177 rows incl. share
classes vs the source's 146 events / 153 subsidiaries), we charge 10bp and
the source charges nothing, and the source's exact daily weighting is not
stated.
PASS CRITERION (written before any run): replication gate met AND harness
verdict PASS vs MDY with every world-class gate (99% confidence, held-out
last 30% win with positive return, DSR >= 0.95 at 5 trials, active t >= 3,
2x costs, >= 70% of holding-period variants beat MDY, FF5+Mom alpha t >= 2).

DATA-TIMING: the ex date is announced months in advance (public before the
entry day); the entry decision at close i reads only dates[i], the ex date
and whether px[sub][i] exists (the stock is trading) — no return on or after
the trade day is read. Exits read dates[i] only. Weights decided at close i
earn close i -> close i+1 (harness), so the first return earned is the
second trading day's.
"""
import json
import sys
import time
import urllib.error
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-21-SPINOFF"
START = "2000-01-01"
EVENTS_FROM = 1998
BENCH = "MDY"
COST = 10.0
HOLD = 22
FAMILY = "spinoffs"
TRIALS = 1 + 4
EXCH = {"NYSE", "NASDAQ", "NYSEMKT", "AMEX", "BATS", "NYSEARCA"}
REPL = ("2006-12-18", "2013-12-31", 0.424)

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
_TK = {}


def tickers_meta():
    """Sharadar TICKERS (stocks rows), paged once."""
    if not _TK:
        off = 0
        while True:
            rows = rb._sh_fetch("tickers", {"table": "stocks", "limit": 10000, "offset": off})
            for r in rows:
                _TK.setdefault(r["ticker"], r)
            if len(rows) < 10000:
                break
            off += 10000
    return _TK


def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def add_months(d, m):
    y, mo = int(d[:4]), int(d[5:7]) - 1 + m
    y, mo = y + mo // 12, mo % 12 + 1
    dim = [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30,
           31, 31, 30, 31, 30, 31][mo - 1]
    return f"{y:04d}-{mo:02d}-{min(int(d[8:10]), dim):02d}"


def events(end=rb.VAULT_FROM):
    """[(ex_date, subsidiary)] after the pre-registered filters."""
    rows = []
    for y in range(EVENTS_FROM, int(end[:4]) + 1):
        rows += rb.sharadar("actions", action="spinoff",
                            **{"date.gte": f"{y}-01-01", "date.lte": f"{y}-12-31"})
    meta = tickers_meta()
    keep = {}
    for r in rows:
        ex, c = r["date"][:10], (r.get("contraticker") or "").strip()
        m = meta.get(c)
        if not c or not m or ex >= end:
            continue
        fp = (m.get("firstpricedate") or "")[:10]
        if (not str(m.get("category") or "").startswith("Domestic Common Stock")
                or m.get("exchange") not in EXCH
                or str(m.get("industry") or "").startswith("REIT")
                or not fp or not (-400 <= _days(ex, fp) <= 10)):
            continue
        key = (ex, (r.get("contraname") or c).upper())
        span = _days(fp, (m.get("lastpricedate") or "2099-12-31")[:10])
        if key not in keep or span > keep[key][1]:
            keep[key] = (c, span)
    return sorted({(ex, c) for (ex, _), (c, _) in keep.items()})


EVENTS = []


def make_weights(hold=HOLD):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st.update(entry={}, dead=set(), miss={}, w=None, base=None, last=None, live=(), m=None)
        d = dates[i]
        for ex, c in EVENTS:                      # entries: on/after ex date, first priced close
            key = (ex, c)
            if key in st["entry"] or ex > d or _days(ex, d) > 10:
                continue
            if c in px and px[c][i] is not None:
                st["entry"][key] = add_months(ex, hold)
        live = []
        for (ex, c), exit_day in st["entry"].items():
            if d >= exit_day or (ex, c) in st["dead"]:
                continue
            if px[c][i] is None:
                st["miss"][(ex, c)] = st["miss"].get((ex, c), 0) + 1
                if st["miss"][(ex, c)] >= 5:
                    st["dead"].add((ex, c))
                    continue
            else:
                st["miss"][(ex, c)] = 0
            live.append(c)
        live = tuple(sorted(set(live)))
        if not live:
            st["w"], st["live"] = None, ()
            return {BENCH: 1.0}
        if live != st["live"] or d[:7] != st["m"]:
            priced = [c for c in live if px[c][i] is not None]
            if priced:
                st["w"] = {c: 1.0 / len(priced) for c in priced}
                st["base"] = {c: px[c][i] for c in priced}
                st["last"] = dict(st["base"])
                st["live"], st["m"] = live, d[:7]
                return dict(st["w"])
        if not st["w"]:
            return {BENCH: 1.0}
        v = {}
        for c, w0 in st["w"].items():
            p = px[c][i]
            if p is not None:
                st["last"][c] = p
            v[c] = w0 * st["last"][c] / st["base"][c]
        tot = sum(v.values())
        return {c: x / tot for c, x in v.items()} if tot > 0 else {BENCH: 1.0}
    return weights


weights = make_weights()
VARIANTS = {f"hold{h}": make_weights(h) for h in (12, 15, 27, 36)}


def panel(subs, extra):
    """Sharadar subsidiaries + Yahoo ETFs aligned on the stock calendar (as evaluate)."""
    dates, px = rb.sharadar_prices(subs, START)
    for e in extra:
        bd, bp = rb.prices([e], START)
        bmap = dict(zip(bd, bp[e]))
        px[e] = [bmap.get(d) for d in dates]
    return dates, px


def replication(subs):
    dates, px = panel(subs, [BENCH, "SPY"])
    keep = sum(1 for d in dates if d <= REPL[1])
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    rb.PPY = rb.periods_per_year(dates)
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(make_weights(), dates, px, rf, COST)
    k0 = next(k for k, d in enumerate(dates) if d >= REPL[0])
    cum = 1.0
    for r in rets[k0:]:
        cum *= 1 + r
    spy = px["SPY"][-1] / px["SPY"][k0]
    live = sum(1 for ex, _ in EVENTS if REPL[0] <= ex <= REPL[1])
    out = {"window": [dates[k0], dates[-1]], "book_cum": round(cum - 1, 4),
           "spy_cum": round(spy - 1, 4), "excess_pp": round(cum - spy, 4),
           "required_excess": REPL[2], "events_in_window": live,
           "source": {"book_cum": 1.370, "market_cum": 0.522}}
    out["replicated"] = out["excess_pp"] >= REPL[2] and out["book_cum"] > 0
    return out


if __name__ == "__main__":
    EVENTS[:] = events()
    subs = sorted({c for _, c in EVENTS})
    print("EVENTS", len(EVENTS), "subsidiaries", len(subs),
          "2001-2012:", sum(1 for ex, _ in EVENTS if "2001" <= ex[:4] <= "2012"))
    rep = replication(subs)
    print("REPLICATION", json.dumps(rep))
    if not rep["replicated"]:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "harness/data suspect: replication gate failed", "replication": rep}))
        sys.exit(0)
    out = rb.evaluate(
        ID, weights, subs, BENCH, start=START, asset_class="stocks", cost_bps=COST, trials=TRIALS,
        family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=(f"McConnell-Sibley-Xu spin-offs: every filtered Sharadar spin-off subsidiary ({len(EVENTS)} "
               "events 1998-vault) bought at its first close on/after the ex date, held 22 months, equal "
               "weight re-equalised on entry/exit and monthly; bench MDY; 10bp; variants hold 12/15/27/36m; "
               f"replication 2006-12-18..2013-12-31 excess vs SPY {rep['excess_pp']} (source +0.848, gate "
               ">= +0.424)"))
    out["replication"] = rep
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
