"""
tests_research.py — Logicon Capital · research-scan harness + ledger tests
=========================================================================
Deploy gate (auto-update-paper.sh). Offline: a fake price feed, no Yahoo.
Guards what makes a weekly verdict trustworthy: no look-ahead, costs and
T-bill cash charged, the verdict thresholds, and a ledger the page can read.
"""

import csv
import math
import random
import sys
import tempfile
from pathlib import Path

import research_bt as rb

PASS = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")


tmp = Path(tempfile.mkdtemp(prefix="research_test_"))
rb.CACHE, rb.RESULTS = tmp / "cache", tmp / "results"
DAYS = [f"{2000 + i // 250}-{1 + (i % 250) // 21:02d}-{1 + i % 21:02d}" for i in range(3000)]
random.seed(7)
UP = [100.0]
for _ in DAYS[1:]:
    UP.append(UP[-1] * (1 + random.gauss(0.0004, 0.01)))
FEED = {"AAA": dict(zip(DAYS, UP)), "^IRX": {d: 5.0 for d in DAYS}}
fetch = lambda s: FEED[s]

# ── 1. no look-ahead: a weight decided at close i only earns i -> i+1 ────────
print("simulation mechanics")
dates, px = rb.prices(["AAA"], "1990-01-01", fetch)
rf = rb.tbill(dates, fetch)
assert abs(rf[0] - 0.05 / 252) < 1e-12
peek = lambda i, d, p: {"AAA": 1.0} if i + 1 < len(d) and p["AAA"][i + 1] > p["AAA"][i] else {}
try:
    rb.simulate(peek, dates, px, rf, cost_bps=0)
    raise AssertionError("peeking at tomorrow was allowed")
except rb.LookAheadError:
    pass
ok("an idea that reads tomorrow's price is stopped (LookAheadError)")
mom = lambda i, d, p: {"AAA": 1.0} if i and p["AAA"][-1] > p["AAA"][-2] else {}
r_mom, _ = rb.simulate(mom, dates, px, rf, cost_bps=0)
exp = [(px["AAA"][i + 1] / px["AAA"][i] - 1) if i and px["AAA"][i] > px["AAA"][i - 1] else rf[i + 1]
       for i in range(len(dates) - 1)]
assert max(abs(a - b) for a, b in zip(r_mom, exp)) < 1e-12
ok("a decision at close i earns exactly close i -> i+1 (negative and slice indexing see only the past)")
hold = lambda i, d, p: {"AAA": 1.0}
r_hold, turn = rb.simulate(hold, dates, px, rf, cost_bps=0)
b = rb.bench_returns("AAA", dates, px, rf)
assert max(abs(x - y) for x, y in zip(r_hold, b)) < 1e-12
ok("always-long matches buy & hold exactly")
q = lambda i, d, p: {"AAA": 0.5}
_, tq = rb.simulate(q, dates, px, rf, cost_bps=0)
assert tq < 0.5 + 0.02 * len(dates), tq
ok("a constant weight only trades the small daily drift back to target")
r_cash, _ = rb.simulate(lambda i, d, p: {}, dates, px, rf, cost_bps=0)
assert all(abs(x - 0.05 / 252) < 1e-12 for x in r_cash)
ok("uninvested capital earns the T-bill rate")
flip = lambda i, d, p: {"AAA": 1.0} if i % 2 else {}
r0, t0 = rb.simulate(flip, dates, px, rf, cost_bps=0)
r9, t9 = rb.simulate(flip, dates, px, rf, cost_bps=50)
assert t0 > 1000 and sum(r0) - sum(r9) > 0.5 * t0 * 50 / 1e4
ok("costs are charged on turnover")
lev = lambda i, d, p: {"AAA": 2.0}
r_lev, _ = rb.simulate(lev, dates, px, rf, cost_bps=0)

assert abs(r_lev[5] - (2 * b[5] - rf[6])) < 1e-9
ok("leverage above 1x pays T-bill financing")

# ── 2. statistics + verdicts ────────────────────────────────────────────────
print("statistics and verdicts")
assert abs(rb.max_dd([0.1, -0.5, 0.2]) + 0.5) < 1e-12
assert abs(rb.cagr([0.0] * 252)) < 1e-12
assert rb.sharpe_confidence(r_hold, r_hold, rf[1:]) == 0.5
ok("max drawdown, CAGR, identical-series confidence = 50%")
good = [f + 0.0008 + random.gauss(0, 0.002) for f in rf[1:]]
assert rb.sharpe_confidence(good, [f for f in rf[1:]], rf[1:]) > 0.99
ok("a strong edge over cash is >99% confident")
res = rb.evaluate("T-HOLD", hold, ["AAA"], "AAA", start="1990-01-01", fetch=fetch, save=True)
assert res["verdict"] == "FAIL"
assert (rb.RESULTS / "T-HOLD.json").exists()
ok("a near-copy of the benchmark FAILs (materiality floor) and the result file is written")
res = rb.evaluate("T-CASH", lambda i, d, p: {}, ["AAA"], None, start="1990-01-01", fetch=fetch, save=False)
assert res["bench"] == "T-bills" and res["verdict"] == "FAIL"
ok("cash vs a cash benchmark cannot pass")
for k in ("idea_cagr", "bench_cagr", "idea_sharpe", "confidence", "oos_idea_sharpe", "trials", "turnover_per_year"):
    assert k in res
ok("results carry every field the Research page shows")

# ── 2b. allocation track ─────────────────────────────────────────────────────
print("allocation track")
LONG = [f"{1990 + i // 252}-{1 + (i % 252) // 21:02d}-{1 + i % 21:02d}" for i in range(252 * 26)]
random.seed(11)
base = [100.0]
for _ in LONG[1:]:
    base.append(base[-1] * (1 + random.gauss(0.0003, 0.01)))
better = [p * (1.0002 ** k) for k, p in enumerate(base)]     # bench + ~5%/yr, same swings
FEED.update({"BEN": dict(zip(LONG, base)), "BETTER": dict(zip(LONG, better))})
FEED["^IRX"].update({d: 3.0 for d in LONG})
r = rb.evaluate_allocation("T-ALLOC-WIN", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                           start="1990-01-01", fetch=fetch, save=False)
assert r["h10"]["status"] == "PASS" and r["h20"]["status"] == "PASS" and r["verdict"] == "PASS"
assert r["h10"]["share_beating"] == 1.0 and r["h10"]["windows"] >= 12
ok("an allocation that beats the benchmark every decade PASSes 10y then 20y")
r = rb.evaluate_allocation("T-ALLOC-SAME", lambda i, d, p: {"BEN": 1.0}, ["BEN"], "BEN",
                           start="1990-01-01", fetch=fetch, save=False)
assert r["verdict"] == "FAIL" and r["h20"]["status"].startswith("NOT RUN")
ok("the benchmark itself FAILs and the 20-year check is skipped")
r = rb.evaluate_allocation("T-ALLOC-SHORT", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                           start="2003-01-01", fetch=fetch, save=False)
assert r["h10"]["status"] == "PASS" and r["h20"]["status"] == "INSUFFICIENT" and r["verdict"] == "PROMISING"
ok("too little history for 20-year windows gives PROMISING, not PASS")
assert "worst_year" in r and len(r["calendar_years"]) >= 13
ok("worst calendar year and the year-by-year table are reported")

# ── 3. ledger ────────────────────────────────────────────────────────────────
print("ledger")
COLS = ["id", "date", "asset_class", "name", "summary", "source", "evidence", "costs", "diversify",
        "testable", "tradeable", "simplicity", "score", "phase", "verdict", "result", "notes"]
led = Path(__file__).resolve().parent / "data" / "research" / "ideas.csv"
with open(led, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
assert list(rows[0].keys()) == COLS
ids = [r["id"] for r in rows]
assert len(ids) == len(set(ids))
PH = {"idea", "backtest", "paper-proposed", "paper", "live", "rejected", "graveyard"}
assert all(r["phase"] in PH for r in rows)
for r in rows:
    if r["score"]:
        parts = sum(int(r[k] or 0) for k in COLS[6:12])
        assert int(r["score"]) == parts, r["id"]
assert not any(r["asset_class"] == "options" for r in rows)
ok(f"ideas.csv: {len(rows)} rows, columns, unique ids, valid phases, score = sum, no options")

import paper_dashboard as pdash
cl = pdash.app.test_client()
j = cl.get("/api/research").get_json()
assert len(j["ideas"]) == len(rows) and cl.get("/research").status_code == 200
ok("/research page and /api/research serve the ledger")

print(f"\nALL {PASS} RESEARCH CHECKS PASSED")
sys.exit(0)
