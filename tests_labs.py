"""
tests_labs.py  —  Logicon Capital  ·  Crypto / FX / Commodities lab tests
========================================================================
Deploy gate (auto-update-paper.sh runs it next to tests_paper.py and
tests_stocks.py). Offline: a fake price feed and a fake clock — no Yahoo.

Covers what the move into the Paper Lab could break: the frozen rule
constants, the scheduler windows, once-per-day idempotency, TR30 entries and
trailing exits, the one-time import from the trader's journal, the CSV
export the hub snapshots, and the dashboard routes.
"""

import csv
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import cmd_lab
import crypto_lab
import fx_lab
import labs_runner as lr

ET = ZoneInfo("America/New_York")
PASS = 0
START = __import__("time").time()


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")


def tmpdb():
    return Path(tempfile.mkdtemp(prefix="labs_test_")) / "labs.sqlite"


CLOCK = {"now": datetime(2026, 10, 15, 21, 30, tzinfo=timezone.utc)}


class FakeDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return CLOCK["now"]


FEED = {}


def fake_chart(sym, rng="6y", interval="1d"):
    s = FEED.get(sym, [100.0] * 60)
    return s[-5:] if rng == "5d" else list(s)


for _m in (crypto_lab, cmd_lab, fx_lab):
    _m.datetime = FakeDT
    _m._chart = fake_chart


def at(day, h=21, m=30):
    CLOCK["now"] = datetime.fromisoformat(f"{day}T{h:02d}:{m:02d}:00+00:00")


# a fresh TR30 breakout today: flat 100, a dip to 90, then 101 (new 30-bar high)
BREAKOUT = [100.0] * 35 + [90.0] * 5 + [101.0]


# ── 1. frozen rules survived the move ────────────────────────────────────────
print("frozen rule constants")
assert crypto_lab.LANES == {"H5": 5, "H10": 10} and crypto_lab.COST_RT == 0.0010
assert crypto_lab.ANN == 365 and crypto_lab.POS_FRAC == 0.25 and crypto_lab.MIN_SCORE == 15
assert (crypto_lab.TR_W, crypto_lab.TR_BAND, crypto_lab.TR_STOP) == (30, 0.99, 0.85)
assert len(crypto_lab.ETFS) == 16
ok("crypto: H5/H10, TR30 30/1%/15%, 10bp, 365-day vol, 16 coins")
assert cmd_lab.LANES == {"H21": 21, "H63": 63} and cmd_lab.COST_RT == 0.0006
assert (cmd_lab.TR_W, cmd_lab.TR_BAND, cmd_lab.TR_STOP) == (30, 0.99, 0.85)
assert len(cmd_lab.ETFS) == 17 and cmd_lab.POS_FRAC == 0.25
ok("commodities: H21/H63, TR30 30/1%/15%, 6bp, 17 ETFs")
assert fx_lab.LANES == ("CARRY", "CARRY-V", "TSMOM") and fx_lab.GROSS == 2.0
assert (fx_lab.COST_RT, fx_lab.COST_RT_SCANDI) == (0.0004, 0.0008)
assert (fx_lab.TR_W, fx_lab.TR_BAND, fx_lab.TR_STOP) == (30, 0.99, 0.85)
ok("fx: CARRY/CARRY-V/TSMOM, gross 2x, 4/8bp, TR30 30/1%/15%")
for m in (crypto_lab, cmd_lab, fx_lab):
    assert m.DB.parts[-3:] == ("data", "labs", "labs.sqlite"), m.DB
ok("all three journals point at data/labs/labs.sqlite")

# ── 2. scheduler windows ─────────────────────────────────────────────────────
print("scheduler windows (ET)")
d = lambda s: datetime.fromisoformat(s).replace(tzinfo=ET)
assert lr.due(d("2026-10-15T17:20")) == ["fx-nav", "cmd-daily", "crypto-daily"]
assert lr.due(d("2026-10-15T17:12")) == ["fx-nav"]
assert lr.due(d("2026-10-17T17:30")) == ["crypto-daily"]          # Saturday
assert lr.due(d("2026-10-15T18:50")) == []                        # UTC day rolls soon
assert lr.due(d("2026-10-15T12:00")) == []
assert lr.due(d("2026-11-02T07:30")) == ["fx-rebalance"]          # Mon the 2nd
assert lr.due(d("2026-11-01T07:30")) == []                        # Sunday
assert lr.due(d("2026-11-05T07:30")) == []                        # past day 3
ok("crypto daily 7d, cmd + fx-nav weekdays, fx rebalance day<=3, windows close 18:50")
for t in ("17:20", "17:45", "18:49"):     # every evening window is still the same UTC day
    for mon in ("2026-07-15", "2026-12-15"):
        loc = d(f"{mon}T{t}")
        assert loc.astimezone(timezone.utc).date() == loc.date(), (mon, t)
ok("evening windows never cross the UTC date the labs key on (EDT and EST)")

calls = []
saved = dict(lr.JOBS)
for k in lr.JOBS:
    lr.JOBS[k] = (lambda k=k: calls.append(k) or {"ok": True, "msg": "x"})
saved_export = lr.export
lr.export = lambda *a, **k: 0
done, logs = set(), []
lr.run_due(d("2026-10-15T17:20"), done, log=logs.append)
lr.run_due(d("2026-10-15T17:40"), done, log=logs.append)
assert calls == ["fx-nav", "cmd-daily", "crypto-daily"], calls
lr.run_due(d("2026-10-16T17:20"), done, log=logs.append)
assert len(calls) == 6
ok("run_due: each job once per ET date per process")
lr.JOBS["cmd-daily"] = lambda: 1 / 0
lr.run_due(d("2026-10-19T17:20"), done, log=logs.append)
assert any("cmd-daily failed" in x for x in logs) and calls[-1] == "crypto-daily"
ok("one lab raising does not stop the others")
lr.JOBS.update(saved)
lr.export = saved_export

# ── 3. crypto lab: start, TR30 entry, idempotency, trailing exit ─────────────
print("crypto lab (fake feed)")
crypto_lab.DB = tmpdb()
FEED.clear()
FEED["SOL-USD"] = list(BREAKOUT)
at("2026-10-15")
r = crypto_lab.start()
assert r["ok"] and r["lanes"]["TR30"]["opened"] == 1 and r["tr_signals"] == ["SOL-USD"]
assert r["lanes"]["H5"]["opened"] == 0           # star needs 5y of history
ok("start runs the first pass; fresh 30-bar breakout opens TR30 only")
assert crypto_lab.start()["ok"] is False
assert "already ran" in crypto_lab.daily()["msg"]
ok("start refuses twice; daily is once per UTC day")
FEED["SOL-USD"] = BREAKOUT + [120.0]
at("2026-10-16")
crypto_lab.daily()
FEED["SOL-USD"] = BREAKOUT + [120.0, 101.0]      # 101 < 120 * 0.85 = 102
at("2026-10-17")
r = crypto_lab.daily()
assert r["lanes"]["TR30"]["closed"] == 1
with sqlite3.connect(crypto_lab.DB) as c:
    t = c.execute("SELECT exit_px, note FROM cryptolab_trades WHERE exit_day IS NOT NULL").fetchone()
assert t[0] == 101.0 and "peak 120.00" in t[1]
ok("TR30 exits on a close 15% below the peak since entry")
s = crypto_lab.status()
assert s["started"] and s["closed_n"] == 1 and set(s["lanes"]) == {"H5", "H10", "TR30"}
ok("status() reports lanes and closed trades")

# ── 4. commodities lab: same mechanics ───────────────────────────────────────
print("commodities lab (fake feed)")
cmd_lab.DB = tmpdb()
FEED.clear()
FEED["GLD"] = list(BREAKOUT)
at("2026-10-15")
r = cmd_lab.start()
assert r["ok"] and r["lanes"]["TR30"]["opened"] == 1
assert "already ran" in cmd_lab.daily()["msg"]
ok("start + TR30 entry + once per day")

# ── 5. FX lab: blocked until the owner confirms the rates ────────────────────
print("fx lab")
fx_lab.DB = tmpdb()
assert fx_lab.start()["ok"] is False
assert fx_lab.snapshot_nav()["ok"] is False
ok("start blocked until rates are confirmed; NAV job is a no-op before start")

# ── 6. one-time import from the trader's journal + CSV export ────────────────
print("import + export")
src = crypto_lab.DB                  # the crypto journal built above stands in
for m in (cmd_lab, fx_lab):          # for the trader's logicon_journal.sqlite
    m.DB = src
cmd_lab.start()
with sqlite3.connect(src) as c:
    c.execute("CREATE TABLE trader_other (x)")      # unrelated trader tables stay behind
    n_src = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("cryptolab_state", "cryptolab_trades", "cryptolab_nav", "cmdlab_pos")}
dst = tmpdb()
CSV = Path(tempfile.mkdtemp(prefix="labs_csv_"))
lr.OUT_DIR = CSV                     # never touch the real data/labs
r = lr.import_from(src, dst, out_dir=CSV)
assert r["ok"] and r["labs"]["cryptolab"].startswith("imported")
assert r["labs"]["cmdlab"].startswith("imported")
with sqlite3.connect(dst) as c:
    for t, n in n_src.items():
        assert c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == n, t
    assert not c.execute("SELECT name FROM sqlite_master WHERE name='trader_other'").fetchone()
ok("import copies every lab row, nothing else")
r = lr.import_from(src, dst, out_dir=CSV)
assert "SKIPPED" in r["labs"]["cryptolab"] and "SKIPPED" in r["labs"]["cmdlab"]
r = lr.import_from(src, dst, force=True, out_dir=CSV)
assert r["labs"]["cryptolab"].startswith("imported")
with sqlite3.connect(dst) as c:
    assert c.execute("SELECT COUNT(*) FROM cryptolab_state").fetchone()[0] == n_src["cryptolab_state"]
ok("re-import refuses existing state; --force replaces it without duplicating")
assert not lr.import_from(Path("/nonexistent.sqlite"), dst, out_dir=CSV)["ok"]
ok("missing source is reported, not crashed on")
out = Path(tempfile.mkdtemp(prefix="labs_csv_"))
n = lr.export(dst, out)
assert n >= 8 and (out / "cryptolab_trades.csv").exists()
with open(out / "cryptolab_state.csv") as f:
    rows = list(csv.DictReader(f))
assert {r["lane"] for r in rows} == {"H5", "H10", "TR30"}
assert not list(out.glob("*.tmp"))
ok("export writes one CSV per lab table, atomically")

# ── 7. dashboard routes ──────────────────────────────────────────────────────
print("dashboard")
for m in (crypto_lab, cmd_lab, fx_lab):
    m.DB = dst
import paper_dashboard as pdash
cl = pdash.app.test_client()
for path, needle in (("/crypto", b"Crypto Lab"), ("/fx", b"FX Lab"),
                     ("/commodities", b"Commodities Lab")):
    resp = cl.get(path)
    assert resp.status_code == 200 and needle in resp.data and b"lab-nav.js" in resp.data, path
    assert b"desk.js" not in resp.data
ok("/crypto, /fx, /commodities serve the lab pages with the Paper Lab nav")
j = cl.get("/api/cryptolab/status").get_json()
assert j["started"] and "TR30" in j["lanes"]
assert cl.get("/api/fxlab/status").status_code == 200
ok("lab status APIs answer from the imported journal")
ov = cl.get("/api/lab/overview").get_json()
assert ov["crypto"]["started"] and set(ov["crypto"]["lanes"]) >= {"TR30"}
assert ov["fx"]["started"] is False
assert ov["commodities"]["started"]
ok("overview carries crypto / fx / commodities headlines")

real = Path(__file__).resolve().parent / "data" / "labs"
assert not real.exists() or real.stat().st_mtime < START, "tests wrote into data/labs"
ok("tests never wrote into the real data/labs")

print(f"\nALL {PASS} LAB CHECKS PASSED")
sys.exit(0)
