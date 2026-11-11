"""L-2026-11-11-RNDSECT — lab original: the R&D-intensity book ranked WITHIN
the research-intensive sectors (Technology, Healthcare) instead of across the
whole index.

INGREDIENTS (shortlist first, RESEARCH.md §2b):
  * R-2026-11-10-RND (potential 3): top 20% of S&P 500 R&D firms by RD/ME,
    +12.8%/yr vs SPY +7.6%, alpha t 2.7, but -63% worst drop (2000-02 tech)
    and failed DSR / t >= 3. It ranks a drug maker's RD/ME against a
    chemical company's: much of its book is a SECTOR bet on whichever R&D
    sector is cheapest that year.
  * Intra-industry evidence: Novy-Marx (2011, Review of Finance 15(1)
    103-134) and Eisfeldt-Papanikolaou (2013, J. Finance 68(4) 1365-1406)
    both find their accounting premia are intra-industry phenomena — sorting
    within industries is what isolates firm-level mispricing from industry
    valuation swings. Chan-Lakonishok-Sougiannis (2001) document that R&D
    is concentrated in a few industries (drugs, computers/software,
    electronics, instruments).
RATIONALE (fixed before any run): the CLS mispricing is that the market
treats expensed R&D as if it built nothing. Comparing firms that live in the
same research economy (a semiconductor against semiconductors and software;
a drug maker against drug and device makers) asks the cleaner question —
"which R&D spender is cheapest for the R&D it does?" — and removes the
sector timing (all-tech in 2000, all-pharma in 2016) that drives RND's
drawdowns. Restricting to Technology and Healthcare also drops firms whose
small R&D lines are noise (industrials with tiny rnd). Expected failure
regime: a whole-sector crash (2000-02 tech, 2022 biotech) — the book is 100%
in two sectors, so it is NOT a lower-beta book; the hoped-for gain is a
steadier active return, not crash protection.

RULE (fixed before any run):
  * Universe: point-in-time S&P 500 members on the SIGNAL day, priced on
    it, whose Sharadar ticker-table `sector` is "Technology" or "Healthcare"
    (ACCRUALS' sector(); NOTE the ticker table gives today's sector, not a
    point-in-time history — a known, small misclassification risk).
  * Trade day: the last close of June each year; SIGNAL day = the previous
    trading day.
  * Eligible: rnd > 0 in the latest ARY row with public date <= signal day
    (calendardate <= 18 months old) — RND's rnd_row.
  * RD/ME = rnd / signal-day market value (Sharadar DAILY x1e6; ARY
    marketcap fallback for the whole date if DAILY is empty) — RND's.
  * WITHIN EACH of the two sectors: hold the top 30% by RD/ME (each sector
    needs >= 8 eligible names, else that sector is skipped that year; the
    whole book needs >= 10 names, else keep the previous book).
  * Weights: equal weight across all picked names; drift until next June.
    SPY before the first book.
  * Variants (robustness gate): top 20% and 40% within sector; add
    "Industrials" as a third R&D sector; sector-equal weights (each sector
    gets 1/k of the book, equal within).
  * Benchmark SPY, 5bp/side, 2000-01 -> vault (lab original), strict bar +
    FF5+Mom alpha gate.
  * Family "rnd-intensity" (same RD/ME core): lifetime 5 (+5 if RNDREV runs
    first) -> trials 15; the harness takes the larger of this and the
    recorded family count.
PRE-RUN DATA CHECK (not a result): the script refuses to run if the ticker
table has no "Technology" or "Healthcare" sector (Sharadar's Morningstar-style
names; MAGICSF/ACCRUALS rely on "Financial Services"/"Utilities" from the
same table).
DATA-TIMING CHECK (theme 21): signal inputs are dated <= dates[i-1], strictly
before the trade day dates[i]: ARY public date <= dates[i-1], DAILY market
value of dates[i-1], membership as of dates[i-1], a price on dates[i-1].
The sector label is static (today's table) — a classification, not a price
or fundamental, but it IS later information: flagged for the red team.
Delisted names: a held stock that delists returns 0 from its last price.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, _here.with_name(fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rev = _load("rndrev", "L-2026-11-10-RNDREV.py")      # make_annual, rdme_scores (RND's definitions)
acc = _load("accruals", "R-2026-11-09-ACCRUALS.py")  # sector()
rnd, ag = rev.rnd, rev.ag

ID = "L-2026-11-11-RNDSECT"
START = rnd.START
BENCH = rnd.BENCH
RD_SECTORS = ("Technology", "Healthcare")


def make_weights(q=0.30, sectors=RD_SECTORS, sector_equal=False, min_sector=8):
    def select(dates, i, px):
        sd = dates[i - 1]
        rd = rev.rdme_scores(sd, i, px)
        books = []
        for s in sectors:
            names = sorted(((-v, t) for t, v in rd.items() if acc.sector(t) == s))
            if len(names) < min_sector:
                continue
            books.append([t for _, t in names[:max(1, int(round(len(names) * q)))]])
        pick = [t for b in books for t in b]
        if len(pick) < 10:
            return None                                  # keep the previous book
        if sector_equal:
            return {t: 1.0 / len(books) / len(b) for b in books for t in b}
        return {t: 1.0 / len(pick) for t in pick}
    return rev.make_annual(select)


weights = make_weights()
VARIANTS = {"q20": make_weights(0.20), "q40": make_weights(0.40),
            "plusInd": make_weights(sectors=RD_SECTORS + ("Industrials",)),
            "sectEq": make_weights(sector_equal=True)}


if __name__ == "__main__":
    import json
    acc.sector("AAPL")                                   # loads the ticker table
    have = set(acc._SECTOR.values())
    missing = [s for s in RD_SECTORS + ("Industrials",) if s not in have]
    if missing:
        raise SystemExit(f"pre-run data check failed: sectors {missing} not in the ticker table {sorted(map(str, have))}")
    out = rb.evaluate(
        ID, weights, ag.all_tickers(START), BENCH, start=START, asset_class="stocks", trials=15,
        family="rnd-intensity", variants=VARIANTS, source="sharadar",
        notes=("Lab RND within R&D sectors: top 30% by RD/ME (rnd / signal-day DAILY market value) inside "
               "Technology and inside Healthcare separately, point-in-time S&P 500, equal weight, each June; "
               "signals read the day before the trade; variants 20/40%, +Industrials, sector-equal; sector "
               "labels are today's (not point-in-time); survivorship-free"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
