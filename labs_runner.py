"""
labs_runner.py — schedule, journal export and one-time import for the
Crypto, FX and Commodities labs.
=====================================================================
The three labs were built inside the trader (combo-trader-tv, 2026-10-02..06)
and moved here on 2026-10-15 so every sandbox lives in one Paper Lab. Their
rules are frozen and copied verbatim (crypto_lab.py, cmd_lab.py, fx_lab.py);
this file only replaces the trader's gex_scheduler hooks:

  Crypto       daily()          17:20 ET, seven days a week
  Commodities  daily()          17:15 ET, weekdays
  FX           snapshot_nav()   17:10 ET, weekdays (TR30 rides this job)
  FX           rebalance()      07:15 ET, first weekday of the month (day <= 3)
  Allocations  daily()          16:30 ET, weekdays (alloc_lab.py, added 2026-10-28)

Every job is idempotent inside its lab (per UTC day / per month), so the
runner uses windows instead of exact minutes: a restart inside a window
re-calls the job and gets "already ran". Evening windows close at 18:50 ET
because the labs key their day on the UTC date, which rolls at 19:00/20:00 ET.

After each job the lab tables are exported to data/labs/*.csv — those CSVs
are what the hub's hourly snapshot commits (the SQLite file itself is not).

One-time import from the trader's journal (run on the hub by the owner):
    python3 labs_runner.py import /opt/logicon/combo-beta/logicon_journal.sqlite
It copies the cryptolab_*, cmdlab_*, fxlab_* tables and refuses to overwrite
a lab that already has state here unless --force is given.
"""

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import alloc_lab
import cmd_lab
import crypto_lab
import fx_lab

ET = ZoneInfo("America/New_York")
BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "data" / "labs"

LABS = {            # prefix -> (module, state table)
    "cryptolab": (crypto_lab, "cryptolab_state"),
    "cmdlab": (cmd_lab, "cmdlab_state"),
    "fxlab": (fx_lab, "fxlab_state"),
    "alloclab": (alloc_lab, "alloclab_state"),
}


def _in(hhmm, lo, hi):
    return lo <= hhmm < hi


def due(now_et: datetime) -> list:
    """Jobs whose window is open at `now_et` (ET wall clock). Pure."""
    hhmm = now_et.strftime("%H:%M")
    weekday = now_et.weekday() < 5
    jobs = []
    if weekday and now_et.day <= 3 and _in(hhmm, "07:15", "09:00"):
        jobs.append("fx-rebalance")
    if weekday and _in(hhmm, "17:10", "18:50"):
        jobs.append("fx-nav")
    if weekday and _in(hhmm, "16:30", "18:50"):
        jobs.append("alloc-daily")
    if weekday and _in(hhmm, "17:15", "18:50"):
        jobs.append("cmd-daily")
    if _in(hhmm, "17:20", "18:50"):
        jobs.append("crypto-daily")
    return jobs


JOBS = {
    "fx-rebalance": lambda: fx_lab.rebalance(),
    "fx-nav": lambda: fx_lab.snapshot_nav(),
    "cmd-daily": lambda: cmd_lab.daily(),
    "crypto-daily": lambda: crypto_lab.daily(),
    "alloc-daily": lambda: alloc_lab.daily(),
}


def run_due(now_et: datetime, done: set, log=print) -> list:
    """Run each due job once per (job, ET date) in this process; export after."""
    ran = []
    for job in due(now_et):
        key = f"{job}-{now_et:%Y-%m-%d}"
        if key in done:
            continue
        done.add(key)
        try:
            r = JOBS[job]()
            msg = r.get("msg") or r.get("lanes") or r.get("navs")
            log(f"labs {job}: {str(msg)[:200]}")
        except Exception as e:          # one lab failing must not stop the others
            log(f"labs {job} failed: {str(e)[:160]}")
        ran.append(job)
    if ran:
        try:
            export()
        except Exception as e:
            log(f"labs export failed: {str(e)[:160]}")
    return ran


def _tables(c, prefix):
    return [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        if r[0].startswith(prefix + "_")]


def export(db: Path = None, out_dir: Path = None) -> int:
    """Dump every lab table to <out_dir>/<table>.csv. Returns tables written."""
    db = db or crypto_lab.DB
    out_dir = out_dir or OUT_DIR
    if not Path(db).exists():
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with sqlite3.connect(db) as c:
        for prefix in LABS:
            for t in _tables(c, prefix):
                cur = c.execute(f"SELECT * FROM {t}")
                cols = [d[0] for d in cur.description]
                tmp = out_dir / f"{t}.csv.tmp"
                with open(tmp, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(cols)
                    w.writerows(cur.fetchall())
                tmp.replace(out_dir / f"{t}.csv")
                n += 1
    return n


def import_from(src: Path, dst: Path = None, force=False, out_dir: Path = None) -> dict:
    """Copy the three labs' tables from the trader's journal into ours.
    A lab that already has state here is skipped unless force=True."""
    dst = dst or crypto_lab.DB
    if not Path(src).exists():
        return {"ok": False, "msg": f"source not found: {src}"}
    for mod, _ in LABS.values():        # create our schemas (incl. migrations)
        mod.DB = dst
        mod._db().close()
    out = {}
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        for prefix, (mod, state) in LABS.items():
            src_tables = _tables(s, prefix)
            if not src_tables:
                out[prefix] = "nothing in source"
                continue
            have = d.execute(f"SELECT COUNT(*) FROM {state}").fetchone()[0]
            if have and not force:
                out[prefix] = "SKIPPED — already has state here (use --force)"
                continue
            rows = 0
            for t in src_tables:
                cols = [r[1] for r in s.execute(f"PRAGMA table_info({t})")]
                ours = {r[1] for r in d.execute(f"PRAGMA table_info({t})")}
                if not ours:
                    out[prefix] = f"FAILED — unknown table {t}"
                    break
                keep = [c for c in cols if c in ours]
                d.execute(f"DELETE FROM {t}")
                data = s.execute(f"SELECT {','.join(keep)} FROM {t}").fetchall()
                d.executemany(f"INSERT INTO {t} ({','.join(keep)}) VALUES "
                              f"({','.join('?' * len(keep))})", data)
                rows += len(data)
            else:
                out[prefix] = f"imported {rows} rows from {len(src_tables)} tables"
    export(dst, out_dir)
    return {"ok": True, "labs": out}


def main(argv):
    if len(argv) >= 2 and argv[0] == "import":
        r = import_from(Path(argv[1]), force="--force" in argv)
        for k, v in (r.get("labs") or {}).items():
            print(f"{k:10s} {v}")
        if not r["ok"]:
            print(r["msg"])
        return 0 if r["ok"] else 1
    if argv and argv[0] == "export":
        print(f"exported {export()} tables to {OUT_DIR}")
        return 0
    if argv and argv[0] == "due":
        now = datetime.now(ET)
        print(now.strftime("%F %H:%M ET"), due(now) or "nothing due")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
