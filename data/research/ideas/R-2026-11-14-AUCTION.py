"""R-2026-11-14-AUCTION — Treasury auction cycle: prices dip before each
auction and recover after (Lou, Yan & Zhang, "Anticipated and Repeated
Shocks in Liquid Markets", RFS 26(8) 2013). Scripts I-2026-11-08-AUCTION
(rejected 2026-11-08 only because auction dates were not in the pipeline;
the free FiscalData `auctions_query` API now supplies them, 1979+).

SOURCE: https://econpapers.repec.org/RePEc:oup:rfinst:v:26:y:2013:i:8:p:1891-1912
(working paper: https://www.fmg.ac.uk/sites/default/files/publications/DP684.pdf).
Independent practitioner confirmation: Robeco, "Quant chart: US Treasuries
up for auction" (2025-03; 10-year futures fall ~6bp into the auction and
recover, 1983-2024; Robeco now trades an auction signal).
Published headline (Table II, on-the-run CMT-style yields, 1980-01 to
2008-06): the yield rises during the 5 days BEFORE an auction and falls in
the 5 days AFTER it:   2-year +2.53 / -2.32bp, 5-year +2.67 / -2.73bp,
10-year +1.57 / -2.00bp (Y(0)-Y(-5), Y(0)-Y(+5)). The pattern holds in
1980-90, 1991-2000 and 2001-08 and is stronger in the later decades.

STEP 1 — REPLICATION (no evaluate call; printed, then gates step 2):
  FRED DGS2 / DGS5 / DGS10 (H.15 constant-maturity yields, read off the
  on-the-run curve) around every ORIGINAL-issue (not reopening, not TIPS,
  not FRN) 2-, 5- and 10-year note auction, 1980-01-01 .. 2008-06-30,
  event days = FRED business-day rows. pre = Y(0)-Y(-5), post = Y(0)-Y(+5).
  REPLICATION PASSES (fixed before any run) when the 10-year pre AND post
  means are both > 0 AND at least 2 of the 3 maturities have pre >= half
  and post >= half of the paper's figure. Otherwise the script prints
  "harness/data suspect" and does NOT run step 2 (no trial is spent).
  Caveat logged: CMT yields are an interpolated curve, not the exact note;
  the switch to the new on-the-run note at issue (inside the post window)
  biases the measured post-auction fall DOWN for an upward-sloping curve,
  i.e. against the paper.

STEP 2 — ETF TEST (one evaluate call). HYPOTHESIS: the post-auction
recovery is a liquidity premium paid to whoever takes duration off the
dealers right after an auction; holding IEF only for the K = 5 trading
days after each 10-year note auction (originals AND reopenings, the
monthly cycle since 2008) and T-bills otherwise earns the recovery leg
(paper: -2.00bp of 10-year yield ~ +15bp of IEF per event) at a better
Sharpe than holding IEF always. Long-only by design (no reliance on short
proceeds earning interest; a step-out-of-duration design is tradeable in
any Schwab account). The pre-auction leg is not traded: the auction is
announced only ~4-5 trading days ahead, so the full pre window is not
known in time (see DATA TIMING).
RULE (fixed before any run):
  * Auction calendar: FiscalData auctions_query, security_type Note,
    original_security_term "10-Year", inflation_index_security "No",
    floating_rate not "Yes" (originals and reopenings).
  * At close i: let j be the index of the most recent 10-year auction date
    on or before dates[i]. If 0 <= i - j < K -> IEF 1.0, else {} (T-bills).
    The position is opened at the close of the auction day (the auction
    closes at 13:00 ET, its result is public before the close) and held
    for K bars.
Benchmark: IEF buy & hold. Costs 3bp (bonds). Start 2002-08-01 (IEF
listed 2002-07-30). 10-year auctions: quarterly to 2002, 6-8/yr 2003-07,
monthly from 2008 (~250 events before the vault).
Variants (4): K = 3, 4, 6, 7 trading days.
trials = 5 (new family; I-2026-11-08-AUCTION was never run, and no other
auction-cycle script exists). Family: R-2026-11-14-AUCTION. NOT the
Treasury calendar family L-TSYCAL (month-end + FOMC windows; its vault is
spent): 10-year auctions fall in the 2nd week of the month, so the
holding window (~days 8-17 of the month) is disjoint from the last-3-days
window; the script prints the actual overlap share for the red team.
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% confidence vs IEF, held-out win, DSR >= 0.95,
t >= 3, double costs, >= 70% of the K neighbours beating IEF) — AND fewer
than 25% of held days inside a last-3-trading-days-of-month window
(otherwise it is the spent month-end effect in disguise and is reported
as confounded, whatever the verdict).
DATA TIMING: the signal reads only the auction calendar for dates <=
dates[i] (auction days already past; FiscalData lists announcement and
auction dates — no prices or yields from the trade day or later); the
weight decided at close i earns close i -> close i+1. The trading calendar
itself (bar count) is the exchange calendar, known in advance. FRED yields
are used only in the step-1 event study, never in the trading rule.
Data: FiscalData via urllib, FRED fredgraph.csv with the default Python
user-agent; both cached per day in data/research/cache/ (git-ignored).
"""
import bisect
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-14-AUCTION"
BENCH = "IEF"
K = 5
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
FISCAL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/"
          "auctions_query?filter=security_type:eq:Note&fields=auction_date,announcemt_date,"
          "security_term,original_security_term,reopening,inflation_index_security,floating_rate"
          "&page[size]=10000&sort=auction_date")
PAPER = {2: (2.53, 2.32), 5: (2.67, 2.73), 10: (1.57, 2.00)}   # (pre rise, post fall), bp


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fred(sid):
    """FRED series as {date: float}, cached per day (default urllib agent)."""
    f = rb.CACHE / f"fred_{sid}.json"
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == _today():
            return j["v"]
    rows = urllib.request.urlopen(FRED + sid, timeout=60).read().decode().strip().splitlines()[1:]
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": _today(), "v": v}))
    return v


def note_auctions():
    """Every Treasury NOTE auction (FiscalData), cached per day."""
    f = rb.CACHE / "fiscal_note_auctions.json"
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == _today():
            return j["v"]
    j = json.loads(urllib.request.urlopen(FISCAL, timeout=90).read().decode())
    rows = j["data"]
    if len(rows) < int(j["meta"]["total-count"]):
        raise RuntimeError("FiscalData page truncated")
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": _today(), "v": rows}))
    return rows


def auction_dates(term, originals_only):
    out = set()
    for r in note_auctions():
        if r.get("original_security_term") != f"{term}-Year":
            continue
        if r.get("inflation_index_security") == "Yes" or r.get("floating_rate") == "Yes":
            continue
        if originals_only and r.get("reopening") == "Yes":
            continue
        out.add(r["auction_date"])
    return sorted(out)


def _mt(x):
    n = len(x)
    if n < 3:
        return None, None, n
    m = sum(x) / n
    sd = (sum((a - m) ** 2 for a in x) / (n - 1)) ** 0.5
    return round(m, 3), round(m / (sd / n ** 0.5), 2) if sd else None, n


def event_study(lo, hi):
    out = {}
    for term, sid in ((2, "DGS2"), (5, "DGS5"), (10, "DGS10")):
        y = fred(sid)
        ds = sorted(y)
        pos = {d: k for k, d in enumerate(ds)}
        pre, post = [], []
        for a in auction_dates(term, True):
            if not (lo <= a <= hi) or a not in pos:
                continue
            k = pos[a]
            if k - 5 < 0 or k + 5 >= len(ds):
                continue
            pre.append(100 * (y[ds[k]] - y[ds[k - 5]]))      # bp rise into the auction
            post.append(100 * (y[ds[k]] - y[ds[k + 5]]))     # bp fall after it
        out[term] = {"pre_rise_bp": _mt(pre), "post_fall_bp": _mt(post)}
    return out


def replication():
    es = event_study("1980-01-01", "2008-06-30")
    ok10 = (es[10]["pre_rise_bp"][0] or 0) > 0 and (es[10]["post_fall_bp"][0] or 0) > 0
    half = sum(1 for t, (p, q) in PAPER.items()
               if (es[t]["pre_rise_bp"][0] or -9) >= p / 2 and (es[t]["post_fall_bp"][0] or -9) >= q / 2)
    return {"period": "1980-01..2008-06", "paper_bp": PAPER, "ours": es,
            "ten_year_signs_ok": ok10, "maturities_at_half_size": half,
            "passes": bool(ok10 and half >= 2)}


def make(k=K):
    cache = {}

    def weights(i, dates, px):
        if "idx" not in cache or cache.get("n") != len(dates):
            # map each 10-year auction date onto the trading calendar (first bar >= it)
            idx = sorted({bisect.bisect_left(dates, a) for a in auction_dates(10, False)})
            cache.update(idx=idx, n=len(dates))
        idx = cache["idx"]
        p = bisect.bisect_right(idx, i) - 1      # most recent auction bar <= i
        if p < 0:
            return {}
        j = idx[p]
        if j < len(dates) and dates[j] <= dates[i] and 0 <= i - j < k and px[BENCH][i]:
            return {BENCH: 1.0}
        return {}
    return weights


def month_end_overlap(fn, start="2002-08-01"):
    """Share of held bars whose next bar is one of the last 3 trading days
    of its month (the spent L-TSYCAL month-end window)."""
    dates, px = rb.prices([BENCH], start)
    dates = [d for d in dates if d < rb.VAULT_FROM]
    px = {BENCH: px[BENCH][:len(dates)]}
    last3 = set()
    for k in range(len(dates)):
        nxt = [d for d in dates[k:k + 4] if d[:7] == dates[k][:7]]
        if len(nxt) <= 3:
            last3.add(dates[k])
    held = [i for i in range(len(dates) - 1) if fn(i, dates, px)]
    inside = sum(1 for i in held if dates[i + 1] in last3)
    return {"held_bars": len(held), "in_month_end_window": inside,
            "share": round(inside / max(len(held), 1), 3)}


weights = make()

if __name__ == "__main__":
    rep = replication()
    rep["etf_era_2002_2024"] = event_study("2002-08-01", "2024-10-31")
    print(json.dumps({"replication": rep}, indent=1))
    if not rep["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "harness/data suspect: the LYZ yield pattern did not replicate "
                                    "on FRED CMT yields 1980-2008 (pre-registered gate)"}, indent=1))
        sys.exit(0)
    ov = month_end_overlap(weights)
    print(json.dumps({"month_end_overlap": ov}, indent=1))
    r = rb.evaluate(ID, weights, [BENCH], BENCH, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={f"K{k}": make(k) for k in (3, 4, 6, 7)},
                    notes="IEF only for the 5 trading days after each 10-year note auction "
                          "(FiscalData, originals + reopenings), T-bills otherwise; bench IEF; "
                          "Lou-Yan-Zhang RFS 2013 post-auction recovery; replication on FRED CMT "
                          f"1980-2008 passed; month-end overlap share {ov['share']}")
    r["replication"] = rep
    r["month_end_overlap"] = ov
    print(json.dumps(r, indent=1))
