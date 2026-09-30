"""
stocks_store.py — the memory of the Stocks & ETF sandbox
=========================================================
Append-only CSVs in data/stocks/ (see STOCKS_SPEC.md §6). The only in-place
updates are on positions.csv, and those are rail-guarded:

  THEO_COLS     immutable once written (entry facts of the campaign)
  WRITE_ONCE    add_* / exit_* — may go from blank to a value exactly once
  TRACKER_COLS  stop_px, peak_px, phase, split_factor — the tracker's state
  ACTUAL_COLS   *_actual + fill_notes — simulated fills write them, a manual
                paperMoney fill may overwrite them any time

Anything outside the allow-list passed by the caller raises ValueError —
never silently dropped. No network, no engine imports: importable offline.
"""

import csv
import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "stocks"

DAY_COLS = ["date", "status", "spy_close", "spy_sma200", "spy_sma10m",
            "spy_regime", "vix", "breadth50", "bars_source", "notes"]

SIGNAL_COLS = ["ts", "date", "slot", "strategy", "action", "symbol", "side",
               "rank", "expl_rank", "r3d", "r21", "rsi2", "sma50", "sma200",
               "atr20", "ref_close", "last", "stop_px", "target_px", "qty",
               "risk_usd", "position_id", "skip_reason", "note"]

THEO_COLS = ["position_id", "strategy", "symbol", "side", "tier", "signal_ts",
             "entry_ts", "qty", "entry_px_theo", "stop_px_initial",
             "target_px", "risk_usd"]
ADD_COLS = ["add_ts", "add_qty", "add_px_theo"]
EXIT_COLS = ["exit_ts", "exit_px_theo", "exit_reason", "pnl_theo"]
TRACKER = ["stop_px", "peak_px", "phase", "split_factor"]
ACTUAL = ["entry_px_actual", "add_px_actual", "exit_px_actual", "pnl_actual",
          "fill_notes"]
POSITION_COLS = THEO_COLS + ADD_COLS + EXIT_COLS + TRACKER + ACTUAL

EVENT_COLS = ["ts", "date", "position_id", "event", "px", "qty", "note"]
MARK_COLS = ["date", "position_id", "strategy", "symbol", "close", "qty",
             "avg_cost", "unrealized", "peak_px", "stop_px", "phase", "stale"]
EOD_COLS = ["date", "open_count", "realized_today", "realized_cum",
            "unrealized", "equity_est", "heat", "notional"]

FILES = {
    "day": ("day.csv", DAY_COLS),
    "signals": ("signals.csv", SIGNAL_COLS),
    "positions": ("positions.csv", POSITION_COLS),
    "events": ("events.csv", EVENT_COLS),
    "marks": ("marks.csv", MARK_COLS),
    "eod": ("eod.csv", EOD_COLS),
}

WRITE_ONCE = set(ADD_COLS) | set(EXIT_COLS)
TRACKER_COLS = set(TRACKER)
ACTUAL_COLS = set(ACTUAL)


def _path(name: str) -> Path:
    return Path(DATA_DIR) / FILES[name][0]


def append(name: str, row: dict):
    """Append one row; create the file with its header on first write."""
    fname, cols = FILES[name]
    path = _path(name)
    os.makedirs(path.parent, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({c: ("" if row.get(c) is None else row.get(c, "")) for c in cols})


def read(name: str) -> list:
    path = _path(name)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _rewrite(name: str, rows: list):
    fname, cols = FILES[name]
    path = _path(name)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def rows_for_date(name: str, d: str) -> list:
    return [r for r in read(name) if r.get("date") == d]


def signals_for(d: str, strategy: str = None, slot: str = None) -> list:
    out = rows_for_date("signals", d)
    if strategy:
        out = [r for r in out if r.get("strategy") == strategy]
    if slot:
        out = [r for r in out if r.get("slot") == slot]
    return out


def is_open(p: dict) -> bool:
    return not (p.get("exit_ts") or "").strip()


def open_positions(strategy: str = None) -> list:
    return [r for r in read("positions") if is_open(r)
            and (strategy is None or r.get("strategy") == strategy)]


def get_position(position_id: str):
    for r in read("positions"):
        if r.get("position_id") == position_id:
            return r
    return None


def add_position(row: dict) -> bool:
    """Append a campaign unless its (deterministic) id already exists —
    the crash-between-writes rail. Returns True when written."""
    if get_position(row["position_id"]) is not None:
        return False
    append("positions", row)
    return True


def update_position(position_id: str, updates: dict, allow: set) -> bool:
    bad = set(updates) - set(allow)
    if bad:
        raise ValueError(f"immutable/unknown position fields: {sorted(bad)}")
    rows = read("positions")
    hit = False
    for r in rows:
        if r.get("position_id") != position_id:
            continue
        for k, v in updates.items():
            v = "" if v is None else str(v)
            cur = (r.get(k) or "").strip()
            if k in WRITE_ONCE and cur and cur != v:
                raise ValueError(f"{k} is write-once (already {cur!r})")
            r[k] = v
        hit = True
    if hit:
        _rewrite("positions", rows)
    return hit
