"""L-2026-11-14-HEDGEPRESS — hedging pressure picks single-commodity ETFs, from
the CFTC Commitments of Traders (lab original, RESEARCH.md §2b; DATA UNLOCK:
the CFTC public-reporting API is reachable from the research environment, which
I-2026-11-09-HEDGEPRESS was rejected for lacking). League round 1, commodities
desk. Ledger: new row L-2026-11-14-HEDGEPRESS; I-2026-11-09-HEDGEPRESS stays
rejected (the futures long-short it describes is still not testable) — add a
"data unlocked, lab ETF form tested as L-2026-11-14-HEDGEPRESS" note there.

WHY LAB, NOT A REPLICATION (stated before any run): the premium comes from
Basu & Miffre, "Capturing the risk premium of commodity futures: The role of
hedging pressure", Journal of Banking & Finance 37(7) 2013
https://econpapers.repec.org/RePEc:eee:jbfina:v:37:y:2013:i:7:p:2652-2664
(doi 10.1016/j.jbankfin.2013.02.031; long-short portfolios sorted
on hedgers' and speculators' positions in 27 futures, 1992-2011, earn a
significant premium; the Keynes-Hicks normal-backwardation story) — see also
Kang, Rouwenhorst & Tang, "A Tale of Two Premiums", JF 75(1) 2020 (the
long-horizon hedging premium is the smaller one). Their headline needs
back-adjusted futures, so it CANNOT be reproduced here; this is a lab test of
the long-only ETF form the ledger row proposed. The lead may veto the slot
under quality rule 1 if he reads it as a sourced idea.

HYPOTHESIS (written before any run): where commercial hedgers are most net
short (producers hedging), speculators are paid an insurance premium to take
the long side; the ETF that holds that market's front futures should earn it
(Keynes; Hirshleifer 1988; Basu-Miffre 2013). A 52-week average reads the
persistent hedging demand, not the short-term flow (that is KRT's other,
opposite-signed liquidity premium — I-2026-11-07-CMDSTMOM, rejected).
DESIGN CHANGE BEFORE ANY BACKTEST (recorded honestly): a signal-only check of
the source's LEVEL sort (no returns computed) showed HP levels differ
structurally by market — precious-metal commercials are almost always net
short (52-week HP mid-2015: PALL 0.82, PPLT 0.77, GLD 0.64, SLV 0.61 vs grains
0.43-0.50) — so the level rule held PPLT in 98% of months, GLD 79%, PALL 67%:
a near-static precious-metals basket, which would test "owning platinum and
gold since 2011", not hedging pressure (theme 22: static exposure passing as a
rule). The main rule therefore standardises HP WITHIN each market (how
unusual today's hedging is for that market), which is the time-varying
insurance demand the hypothesis is about. The level sort is NOT run.
PASS CRITERION (pre-registered): research_bt verdict PASS vs buy-and-hold DBC
(all §0 gates; >= 70% of the 4 neighbours beating DBC on Sharpe).

RULE (fixed before any run):
  universe: the 10 single-commodity ETFs of CMDSKEW/CMDBAB, each mapped to the
  CFTC legacy futures-only report of the market it holds:
    GLD gold 088691 | SLV silver 084691 | CPER copper 085692 |
    PALL palladium 075651 | PPLT platinum 076651 | USO WTI crude 067651 |
    CORN corn 002602 | SOYB soybeans 005602 | WEAT SRW wheat 001602 |
    CANE sugar no.11 080732
  per weekly report: HP = commercial short / (commercial short + commercial long)
  at each month-end close i (next bar falls in a new month):
    for each ETF priced at i, over its last L AVAILABLE reports (L = 260,
    ~5 years; needing all L):
      score = (mean HP of the last N of them - mean HP of all L) / sd(HP over L)
      (N = 52: this year's hedging pressure vs the market's own 5-year norm)
    need >= 7 scored ETFs (a real cross-section); hold the K = 3 highest
    scores (hedgers unusually net short), 1/K each; else T-bills. Ties by name.
  held to the next month-end.
DATA TIMING (the COT is side data, read outside prices()): a report is dated
its Tuesday positions date and published the following Friday 15:30 ET; it is
treated as AVAILABLE only from report_date + 7 calendar days (the next
Tuesday — after the Friday release, also covering holiday-delayed Mondays).
Government shutdowns delayed releases by weeks; reports dated inside these
spans are held back until the catch-up was complete:
    2013-10-01 .. 2013-11-05 -> available 2013-11-12
    2018-12-25 .. 2019-03-05 -> available 2019-03-12
    2025-09-30 .. 2026-01-13 -> available 2026-01-27  (vault period only)
A decision at close i reads only reports with available date <= dates[i].
Prices: closes dated <= i (harness guard); month-end test peeks only at
dates[i+1]'s MONTH; weights decided at close i earn close i -> close i+1.
CFTC data caveat: COT rows are occasionally corrected after release; the API
serves the current (corrected) values — a small revision risk, stated.
Benchmark: buy & hold DBC. Costs 5bp. Start 2011-09-01 (CANE/SOYB/WEAT list
2011-09-19, CPER 2011-11; first signal at the 2011-09 month-end with 9 names).
No 2008 (caveat); includes 2014-16, 2020, 2022.
Variants (neighbours): N = 26 weeks; L = 156 weeks (3 years); K = 2 / 4.
NEW FAMILY "cmd-hedging-pressure" -> trials 1 + 4 = 5.
Fetches: https://publicreporting.cftc.gov/resource/6dca-aqww.json (public, no
key), cached in data/research/cache/ (git-ignored). Unlock to note for the
owner: a COT capability on the data hub (cloudflare/data routes.mjs).
"""
import bisect
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

MAP = {"GLD": "088691", "SLV": "084691", "CPER": "085692", "PALL": "075651",
       "PPLT": "076651", "USO": "067651", "CORN": "002602", "SOYB": "005602",
       "WEAT": "001602", "CANE": "080732"}
UNIV = sorted(MAP)
BENCH = "DBC"
START = "2011-09-01"
LAG_DAYS = 7
SHUTDOWNS = [("2013-10-01", "2013-11-05", "2013-11-12"),
             ("2018-12-25", "2019-03-05", "2019-03-12"),
             ("2025-09-30", "2026-01-13", "2026-01-27")]
API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
COT = {}


def _available(rd):
    for a, b, av in SHUTDOWNS:
        if a <= rd <= b:
            return av
    return (date.fromisoformat(rd) + timedelta(days=LAG_DAYS)).isoformat()


def _fetch_cot(code):
    f = rb.CACHE / f"cftc_legacy_{code}.json"
    if f.exists() and f.stat().st_size > 1000:
        rows = json.loads(f.read_text())
    else:
        q = urllib.parse.urlencode({
            "$select": "report_date_as_yyyy_mm_dd,comm_positions_long_all,comm_positions_short_all",
            "cftc_contract_market_code": code, "$order": "report_date_as_yyyy_mm_dd ASC",
            "$limit": "50000"})
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "research-bt/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.loads(r.read())
        rb.CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rows))
    out = {}
    for r in rows:
        rd = r["report_date_as_yyyy_mm_dd"][:10]
        lo, sh = float(r.get("comm_positions_long_all") or 0), float(r.get("comm_positions_short_all") or 0)
        if lo + sh > 0:
            out[rd] = sh / (lo + sh)            # one row per report date (last wins)
    pts = sorted((_available(rd), rd, hp) for rd, hp in out.items())
    return [p[0] for p in pts], [p[2] for p in pts]


def _load():
    if not COT:
        for s, code in MAP.items():
            COT[s] = _fetch_cot(code)
    return COT


def score(s, d, n, lw):
    """Within-market z-score: mean HP of the last n reports available on or
    before date d, minus the mean of the last lw, over their sd."""
    av, hp = _load()[s]
    k = bisect.bisect_right(av, d)
    if k < lw or n > lw:
        return None
    win = hp[k - lw:k]
    mu = sum(win) / lw
    sd = (sum((x - mu) ** 2 for x in win) / (lw - 1)) ** 0.5
    if sd <= 0:
        return None
    return (sum(hp[k - n:k]) / n - mu) / sd


def make(n=52, lw=260, k=3, min_n=7):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        sc = {}
        for s in UNIV:
            if px[s][i]:
                x = score(s, dates[i], n, lw)
                if x is not None:
                    sc[s] = x
        w = {}
        if len(sc) >= max(min_n, k):
            picks = sorted(sc, key=lambda s: (-sc[s], s))[:k]
            w = {s: 1.0 / k for s in picks}
        st["w"] = w
        return w
    return weights


weights = make()

if __name__ == "__main__":
    _load()
    variants = {"n26": make(26), "l156": make(52, 156), "k2": make(52, 260, 2), "k4": make(52, 260, 4)}
    res = rb.evaluate("L-2026-11-14-HEDGEPRESS", weights, UNIV + [BENCH], BENCH, start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="cmd-hedging-pressure", variants=variants,
                      notes="month-end: hold the 3 of 10 single-commodity ETFs whose markets' commercial hedgers are most "
                            "UNUSUALLY net short (CFTC legacy COT, HP = comm short/(short+long); z = (mean HP last 52 "
                            "reports - mean last 260) / sd last 260, reports available >= 7 days after the positions "
                            "date; shutdown spans held back), "
                            "1/3 each, else T-bills; bench DBC; 5bp; lab long-only ETF form of Basu-Miffre JBF 2013 "
                            "(futures headline not reproducible here)")
    print(json.dumps(res, indent=1))
