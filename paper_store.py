"""
paper_store.py — CSV data model for the paper-mode signal logger
================================================================
All files live in data/paper/, one row appended per event. day / signals /
band rows are append-only; positions.csv and the band row's settlement
columns are the two sanctioned in-place updates (keyed by position_id /
date). Theo columns on positions are immutable once written — `paper fill`
may only touch the *_actual columns.

No network, no engine imports: this module must stay importable offline so
tests_paper.py can run without Schwab credentials.
"""

import csv
import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "paper"

DAY_COLS = ["date", "status", "vix", "vix_chg_5d", "prior_close", "atr20",
            "gex_sign", "risk_budget", "notes"]

SIGNAL_COLS = ["ts", "date", "slot", "strategy", "action", "side", "structure",
               "state", "ema_fast", "ema_slow", "spot", "short_strike",
               "long_strike", "short_strike_2", "long_strike_2", "width",
               "credit_theo", "short_delta", "short_mid", "long_mid",
               "stop_level", "skip_reason", "gex_sign", "vix", "band_lower",
               "band_upper", "skew", "containment_rc", "size_factor"]

# `contracts` is not in the spec's column list but pnl/risk cannot be
# reconstructed from the CSVs alone without it (report must run offline).
POSITION_COLS = ["position_id", "signal_ts", "strategy", "side", "contracts",
                 "short_strike", "long_strike", "credit_theo", "stop_level",
                 "exit_ts", "exit_value_theo", "exit_reason", "pnl_theo",
                 "credit_actual", "exit_value_actual", "pnl_actual", "fill_notes"]

BAND_COLS = ["date", "spot_1030", "straddle_mid", "em", "lower", "upper",
             "skew", "spx_close", "contained"]

FILES = {
    "day": ("day.csv", DAY_COLS),
    "signals": ("signals.csv", SIGNAL_COLS),
    "positions": ("positions.csv", POSITION_COLS),
    "band": ("band.csv", BAND_COLS),
}

# The only columns `paper fill` may write; everything theo is immutable.
ACTUAL_COLS = {"credit_actual", "exit_value_actual", "pnl_actual", "fill_notes"}
# Columns the tracker itself may update on an open position.
EXIT_COLS = {"exit_ts", "exit_value_theo", "exit_reason", "pnl_theo"}


def _path(name: str) -> Path:
    return DATA_DIR / FILES[name][0]


def append(name: str, row: dict):
    """Append one row; create the file with its header on first write."""
    fname, cols = FILES[name]
    path = DATA_DIR / fname
    os.makedirs(DATA_DIR, exist_ok=True)
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
    """Atomic full rewrite — used only for the sanctioned in-place updates."""
    fname, cols = FILES[name]
    path = DATA_DIR / fname
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
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


def signals_for(d: str, strategy: str = None) -> list:
    out = rows_for_date("signals", d)
    if strategy:
        out = [r for r in out if r.get("strategy") == strategy]
    return out


def open_positions() -> list:
    return [r for r in read("positions") if not (r.get("exit_ts") or "").strip()]


def update_position(position_id: str, updates: dict, allow: set) -> bool:
    """Update one position row in place. Fields outside `allow` are rejected
    outright (never silently dropped) — that is the theo-immutability rail."""
    bad = set(updates) - set(allow)
    if bad:
        raise ValueError(f"immutable/unknown position fields: {sorted(bad)}")
    rows = read("positions")
    hit = False
    for r in rows:
        if r.get("position_id") == position_id:
            for k, v in updates.items():
                r[k] = "" if v is None else v
            hit = True
    if hit:
        _rewrite("positions", rows)
    return hit


def update_band(d: str, updates: dict) -> bool:
    """Fill the settlement columns (spx_close, contained) on the day's band row."""
    bad = set(updates) - {"spx_close", "contained"}
    if bad:
        raise ValueError(f"band columns are append-only: {sorted(bad)}")
    rows = read("band")
    hit = False
    for r in rows:
        if r.get("date") == d:
            for k, v in updates.items():
                r[k] = "" if v is None else v
            hit = True
    if hit:
        _rewrite("band", rows)
    return hit
