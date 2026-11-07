"""
tests_research.py — Logicon Capital · research-scan harness + ledger tests
=========================================================================
Deploy gate (auto-update-paper.sh). Offline: a fake price feed, no Yahoo.
Guards what makes a weekly verdict trustworthy: no look-ahead, costs and
T-bill cash charged, the verdict thresholds, and a ledger the page can read.
"""

import csv
from datetime import date
import math
import json
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

# ── 2d. world-class gates (owner 2026-11-07) ────────────────────────────────
print("world-class gates")
random.seed(5)
act = [0.0004 + random.gauss(0, 0.004) for _ in range(2500)]
d1, d100 = rb.deflated_sharpe(act, 1), rb.deflated_sharpe(act, 100)
assert d1 is not None and d100 is not None and d100 < d1
weak = [0.00005 + random.gauss(0, 0.004) for _ in range(2500)]
assert rb.deflated_sharpe(weak, 50) < 0.95
ok("Deflated Sharpe falls as trials rise; a weak edge tried 50 ways fails it")
x1 = [random.gauss(0, 1) for _ in range(800)]; x2 = [random.gauss(0, 1) for _ in range(800)]
y = [0.3 + 2 * a - 0.5 * b + random.gauss(0, 0.1) for a, b in zip(x1, x2)]
beta, tv = rb.ols(y, [x1, x2])
assert abs(beta[0] - 0.3) < 0.02 and abs(beta[1] - 2) < 0.02 and abs(beta[2] + 0.5) < 0.02 and tv[0] > 20
ok("OLS recovers intercept and loadings with t-stats")
FFD = [f"{2010 + i // 336}{1 + (i % 336) // 28:02d}{1 + i % 28:02d}" for i in range(336 * 2)]
mk = [random.gauss(0.0004, 0.01) for _ in FFD]
ff5 = "junk header\n,Mkt-RF,SMB,HML,RMW,CMA,RF\n" + "\n".join(
    f"{d},{m*100:.4f},{random.gauss(0,0.5):.4f},{random.gauss(0,0.5):.4f},{random.gauss(0,0.3):.4f},{random.gauss(0,0.3):.4f},0.01"
    for d, m in zip(FFD, mk)) + "\n\nAnnual Factors\n,Mkt-RF\n1990,1.0\n"
momc = "x\n,Mom\n" + "\n".join(f"{d},{random.gauss(0,0.6):.4f}" for d in FFD)
fake_ff = lambda url: ff5 if "5_Factors" in url else momc
rb.CACHE.joinpath("ff5mom.json").unlink(missing_ok=True)
F = rb.ff_factors(fake_ff)
dd = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in FFD]
assert len(F) == len(FFD) and set(F[dd[0]]) >= {"Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"}
assert "1990-..-.." not in F and abs(F[dd[3]]["Mkt-RF"] - round(mk[3] * 100, 4) / 100) < 1e-12
ok("Ken French daily files parsed (5 factors + momentum, annual block ignored)")
beta_only = [F[d]["Mkt-RF"] for d in dd]
fa = rb.factor_alpha(beta_only, [0.0] * len(dd), dd, F)
assert fa and abs(fa["alpha_t"]) < 2 and abs(fa["loadings"]["Mkt-RF"] - 1) < 0.01
alpha = [F[d]["Mkt-RF"] + 0.0006 + random.gauss(0, 0.001) for d in dd]
fa2 = rb.factor_alpha(alpha, [0.0] * len(dd), dd, F)
assert fa2["alpha_t"] > 5
ok("pure market exposure shows no alpha; a real excess return shows alpha t > 5")
r = rb.evaluate("T-WC", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                start="1990-01-01", fetch=fetch, save=False, trials=5)
assert r["verdict"] == "PASS" and r["gates"]["deflated_sharpe"] == "ok" and r["gates"]["t_stat_3"] == "ok"
assert r["gates"]["double_costs"] == "ok" and r["trials"] == 5 and r["sharpe_2x_costs"] is not None
ok("a genuine, consistent edge still PASSes every world-class gate")
r = rb.evaluate("T-WC-FRAGILE", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                start="1990-01-01", fetch=fetch, save=False,
                variants={"v1": lambda i, d, p: {"BEN": 1.0}, "v2": lambda i, d, p: {"BEN": 1.0},
                          "v3": lambda i, d, p: {"BEN": 1.0}})
assert r["gates"]["robustness"] == "FAIL" and r["verdict"] == "PROMISING" and r["trials"] == 4
ok("neighbouring settings that do not work demote PASS -> PROMISING (variants count as trials)")
rb.CACHE.joinpath("ff5mom.json").unlink(missing_ok=True)
r = rb.evaluate("T-WC-STOCK", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN", start="1990-01-01",
                fetch=fetch, save=False, asset_class="stocks", ff_fetch=lambda u: (_ for _ in ()).throw(OSError("offline")))
assert r["gates"]["factor_alpha"] == "n/a" and r["cost_bps"] == rb.COST_BPS["stocks"]
rb.CACHE.joinpath("ff5mom.json").unlink(missing_ok=True)
r = rb.evaluate("T-WC-CRYPTO", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN", start="1990-01-01",
                fetch=fetch, save=False, asset_class="crypto")
assert r["cost_bps"] == 25.0 and r["factor_alpha"] is None
ok("per-class costs; factor gate n/a (never blocks) when the factor data cannot be fetched")

# ── 2e. original-research safeguards: vault + automatic trials ──────────────
print("vault and automatic trials")
for n in ("trials.json", "vault_log.json"):
    (rb.RESULTS / n).unlink(missing_ok=True)
old_vault = rb.VAULT_FROM
rb.VAULT_FROM = LONG[len(LONG) * 3 // 4]
dev = rb.evaluate("T-VAULT", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                  start="1990-01-01", fetch=fetch, save=True, family="FAM-X")
assert dev["period"][1] < rb.VAULT_FROM and dev["vault"].startswith("sealed")
ok("development runs never see the vault period")
dev2 = rb.evaluate("T-VAULT-2", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                   start="1990-01-01", fetch=fetch, save=True, family="FAM-X",
                   variants={"a": lambda i, d, p: {"BETTER": 1.0}})
assert dev2["trials"] == 3, dev2["trials"]          # 1 earlier + this run's 2
assert json.loads((rb.RESULTS / "trials.json").read_text())["FAM-X"] == 3
ok("trials accumulate per family automatically (variants included)")
v = rb.evaluate("T-VAULT-EXAM", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                start="1990-01-01", fetch=fetch, save=True, family="FAM-X", vault=True)
assert v["period"][1] >= rb.VAULT_FROM and v["vault"].startswith("VAULT TEST")
try:
    rb.evaluate("T-VAULT-AGAIN", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                start="1990-01-01", fetch=fetch, save=True, family="FAM-X", vault=True)
    raise AssertionError("second vault test allowed")
except rb.VaultUsedError:
    pass
ok("the vault opens exactly once per idea family")
rb.VAULT_FROM = old_vault
for n in ("trials.json", "vault_log.json"):
    (rb.RESULTS / n).unlink(missing_ok=True)

# ── 2f. potential rating / building blocks (owner 2026-11-07) ───────────────
print("potential rating")
random.seed(21)
bret_t = [random.gauss(0.0004, 0.012) for _ in range(252 * 12)]
rf_t = [0.0001] * len(bret_t)
safer = [b * 0.5 if b < -0.01 else b * 0.9 for b in bret_t]       # cuts crashes, keeps most upside
tr = rb.traits(safer, bret_t, rf_t)
assert tr["dd_cut"] >= 0.3 and "risk-reducer" in tr["building_blocks"], tr
assert tr["potential_suggested"] >= 2
ok("a crash-cutting rule is tagged risk-reducer even without beating the benchmark")
indep = [random.gauss(0.0003, 0.008) for _ in bret_t]
tr2 = rb.traits(indep, bret_t, rf_t)
assert "diversifier" in tr2["building_blocks"] and abs(tr2["corr_to_bench"]) < 0.1
ok("an uncorrelated positive stream is tagged diversifier")
r = rb.evaluate("T-TRAITS", lambda i, d, p: {"BETTER": 1.0}, ["BETTER"], "BEN",
                start="1990-01-01", fetch=fetch, save=False)
assert "traits" in r and "potential_suggested" in r["traits"] and "active_sharpe_bench_uptrend" in r["traits"]
ok("every result carries traits + a suggested potential (regime split included)")

# ── 2g. portfolio construction (owner shortfall #3) ─────────────────────────
print("portfolio construction")
import portfolio as pf
random.seed(33)
ms = [f"{2000 + i // 12}-{1 + i % 12:02d}" for i in range(240)]
eq_ = {m: random.gauss(0.008, 0.045) for m in ms}
bond = {m: random.gauss(0.003, 0.015) for m in ms}
clone = {m: eq_[m] * 0.9 + random.gauss(0, 0.003) for m in ms}
indep = {m: random.gauss(0.006, 0.02) for m in ms}
w = pf.inverse_vol_weights({"eq": eq_, "bond": bond})
assert w["bond"] > w["eq"] and abs(sum(w.values()) - 1) < 1e-12
ok("inverse-vol weights: the calmer sleeve gets more capital, weights sum to 1")
c = pf.correlation({"eq": eq_, "clone": clone})
assert c[("eq", "clone")] > 0.95 and abs(c[("eq", "eq")] - 1) < 1e-9
base = {"eq": eq_, "bond": bond}
m_ind = pf.marginal(base, "indep", indep)
m_cln = pf.marginal(base, "clone", clone)
assert m_ind["adds_value"] and m_ind["sharpe_gain"] > m_cln["sharpe_gain"]
assert m_ind["corr_to_book"] < m_cln["corr_to_book"]
ok("an uncorrelated edge adds more to the book than a correlated clone")
dts = ["2020-01-02", "2020-01-03", "2020-02-03"]
mo = pf.monthly(dts, [0.01, 0.02, -0.01])
assert abs(mo["2020-01"] - (1.01 * 1.02 - 1)) < 1e-12 and abs(mo["2020-02"] + 0.01) < 1e-12
ok("daily -> monthly compounding")

# ── 2h. Sharadar connector (survivorship-free data, owner 2026-11-07) ──────
print("Sharadar connector")
def fake_sh(table, params):
    if table == "stocks":
        t = params["ticker"]
        return [{"date": d, "closeadj": 10.0 + i} for i, d in enumerate(["2020-01-02", "2020-01-03", "2020-01-06"])
                if not (t == "GONEQ" and d == "2020-01-06")]
    if table == "sp500":
        y = params["from"][:4]
        return {"2019": [{"date": "2019-12-31", "action": "historical", "ticker": "AAA"},
                         {"date": "2019-12-31", "action": "historical", "ticker": "GONEQ"}],
                "2020": [{"date": "2020-03-02", "action": "added", "ticker": "NEW"},
                         {"date": "2020-03-02", "action": "removed", "ticker": "GONEQ"}]}.get(y, [])
    if table == "fundamentals":
        return [{"date": "2020-05-01", "calendardate": "2020-03-31"}, {"date": "2020-02-01", "calendardate": "2019-12-31"}]
    return []
for _f in rb.CACHE.glob("sh_*.json"):
    _f.unlink()
d_, p_ = rb.sharadar_prices(["AAA", "GONEQ"], "2020-01-01", fetch=fake_sh)
assert d_ == ["2020-01-02", "2020-01-03", "2020-01-06"] and p_["GONEQ"][2] is None and p_["AAA"][2] == 12.0
ok("Sharadar prices on the union calendar; a delisted name simply stops")
hist = rb.sp500_history(fake_sh, 2019, 2020)
assert rb.sp500_members("2020-01-15", hist) == {"AAA", "GONEQ"}
assert rb.sp500_members("2020-03-02", hist) == {"AAA", "NEW"}
assert rb.sp500_members("2018-06-30", hist) == set()
ok("point-in-time S&P 500 membership: snapshot + adds/removes up to the date")
fr = rb.fundamentals_pit("AAA", fetch=fake_sh)
assert [r["date"] for r in fr] == ["2020-02-01", "2020-05-01"]
ok("fundamentals sorted by the date they became public")
for _f in rb.CACHE.glob("sh_*.json"):
    _f.unlink()

# ── 2c. weekly performance report ───────────────────────────────────────────
print("performance report")
import perf_report as pr
spy_feed = {d: 100.0 + i * 0.1 for i, d in enumerate(f"2026-{m:02d}-{dd:02d}" for m in (9, 10, 11) for dd in range(1, 29))}
rep = pr.build(fetch=lambda s: spy_feed)
assert rep["asof"] and set(rep["labs"]) <= set(pr.LAB_META)
for lab in rep["labs"].values():
    for s in lab["lanes"].values():
        assert {"now", "week_pct", "total_pct", "max_dd", "open"} <= set(s) and s["max_dd"] <= 0
if rep.get("stocks"):
    assert set(pr.STOCK_PAPER_LANES) <= set(rep["stocks"]["lanes"])
body = pr.html(rep)
assert "Needs attention" in body and "<table" in body and "Options and Project Shine" in body
assert "week" in rep["spy"] or "error" in rep["spy"]
ok("perf_report builds from the snapshotted journals and renders the email (offline SPY)")
s = pr.stats([(date(2026, 1, 1), 10_000.0), (date(2026, 1, 5), 12_000.0), (date(2026, 1, 9), 9_000.0)],
             10_000.0, date(2026, 1, 9), date(2026, 1, 6))
assert s["week_pct"] == -0.25 and s["max_dd"] == -0.25 and s["total_pct"] == -0.1
ok("lane stats: week change, since start, drawdown from peak")

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

for _f in (rb.BASE_DIR / "data" / "research" / "series").glob("T-*.json"):
    _f.unlink()                                  # test fixtures never stay in the repo
print(f"\nALL {PASS} RESEARCH CHECKS PASSED")
sys.exit(0)
