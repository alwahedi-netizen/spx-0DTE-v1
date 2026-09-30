"""
stocks_engine.py — the brain of the Stocks & ETF sandbox (paper only)
=====================================================================
Spec: STOCKS_SPEC.md (pre-registered strategies, schema, gates). Playbook:
SANDBOX_PLAYBOOK.md. Nothing here places orders — fills are SIMULATED at
the live quote ± a slippage model; the journal is the lab's only output.

Layout mirrors paper_engine.py:
  * pure decision functions (indicators, candidates, sizing, stops, fills,
    fees, split heal) — no I/O, truth-tabled in tests_stocks.py;
  * an idempotent session loop `run_session(cfg, data, clock)` that
    re-derives all state from the journal, so a crash/restart never
    duplicates or loses a slot, an entry, an exit or a mark. The data
    adapter and the clock are injected so tests_stocks.py can run a whole
    session in milliseconds, crash included.

CLI:
    python3 stocks_engine.py run        # today's session loop (supervised by the dashboard)
    python3 stocks_engine.py status
    python3 stocks_engine.py report
"""

import argparse
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import stocks_store as st

ET = ZoneInfo("America/New_York")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "stocks_config.yaml"

PREMARKET_TIME = "09:15"
ENTRY_SLOT = "09:45"
ENTRY_GRACE_MIN = 30          # freshness guard: never chase a stale signal
EXIT_TIME = "15:50"           # rule exits (time stops, RSI2, MOM review)
CLOSE_TIME = "16:00"
MARK_TIME = "16:10"
TRACK_INTERVAL_S = 120
STALE_MARKS_DELIST = 5        # consecutive quote-less marks -> DELISTED
STRATEGIES = ("MOM", "PB90", "RSI2", "MOMR", "BRK55", "HI52", "QBO", "SECROT")
ETF_STRATEGIES = {"RSI2", "SECROT"}
FAMILY = {"MOMR": "MOM"}          # MOMR = MOM mechanics + a regime filter


def family(strategy: str) -> str:
    return FAMILY.get(strategy, strategy)

# NYSE full closures and 13:00 early closes (2026–2027).
NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}

DEFAULTS = {
    "account_equity": 100000,
    "risk_per_trade_pct": 0.005,
    "max_notional_pct": 0.08,
    "heat_cap_pct": 0.08,
    "daily_new_risk_pct": 0.02,
    "slippage_bps": {"large": 5, "etf": 2},
    "sell_fee_bps": 0.278,
    "taf_per_share": 0.000166,
    "taf_cap": 8.30,
    "universe": {"stocks": [], "etfs": []},
    "mom": {"enabled": True, "stage": "backtest", "expl_rank_min": 90, "max_new_per_day": 2,
            "max_open": 8, "ph1_stop": 0.85, "ph2_trail": 0.85,
            "add_r21_min": 10.0, "add_within_peak": 0.03,
            "review_days": 28, "review_band": 5.0},
    "pb90": {"enabled": True, "stage": "backtest", "expl_rank_min": 75, "r1y_rank_min": 70,
             "pb_lo": 2.0, "pb_hi": 12.0, "atr_stop": 2.0,
             "time_stop_sessions": 20, "max_new_per_day": 2, "max_open": 5},
    "rsi2": {"enabled": True, "stage": "backtest", "rsi_max": 10.0, "atr_stop": 3.0, "exit_sma": 5,
             "time_stop_sessions": 10, "max_new_per_day": 2, "max_open": 4},
    "momr": {"enabled": True, "stage": "backtest", "expl_rank_min": 90, "max_new_per_day": 2,
             "max_open": 8, "ph1_stop": 0.85, "ph2_trail": 0.85, "add_r21_min": 10.0,
             "add_within_peak": 0.03, "review_days": 28, "review_band": 5.0},
    "brk55": {"enabled": True, "stage": "backtest", "atr_stop": 2.0,
              "max_new_per_day": 2, "max_open": 8},
    "hi52": {"enabled": True, "stage": "backtest", "near_high_pct": 2.0, "expl_rank_min": 80,
             "stop_pct": 12.0, "max_new_per_day": 2, "max_open": 8},
    "qbo": {"enabled": True, "stage": "backtest", "r63_rank_min": 90, "r63_min": 25.0,
            "box_max_pct": 10.0, "atr_stop": 1.5, "time_stop_sessions": 40,
            "max_new_per_day": 2, "max_open": 6},
    "secrot": {"enabled": True, "stage": "backtest", "top_n": 3, "entry_sessions": 3,
               "stop_pct": 15.0, "max_new_per_day": 3, "max_open": 3},
    "gates": {"MOM": {"trades": 60, "weeks": 16, "tripwire": -3000},
              "PB90": {"trades": 100, "weeks": 12, "tripwire": -3000},
              "RSI2": {"trades": 100, "weeks": 10, "tripwire": -2500},
              "MOMR": {"trades": 60, "weeks": 16, "tripwire": -3000},
              "BRK55": {"trades": 80, "weeks": 16, "tripwire": -3000},
              "HI52": {"trades": 80, "weeks": 16, "tripwire": -3000},
              "QBO": {"trades": 80, "weeks": 16, "tripwire": -3000},
              "SECROT": {"trades": 30, "weeks": 26, "tripwire": -3000}},
}


def load_config(path=None) -> dict:
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    p = Path(path) if path else CONFIG_FILE
    if p.exists():
        import yaml
        user = yaml.safe_load(p.read_text()) or {}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


# ── time / calendar ──────────────────────────────────────────────────────────

def now_et() -> datetime:
    return datetime.now(ET)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def at(hhmm: str, d: date) -> datetime:
    h, m = hhmm.split(":")
    return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=ET)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in NYSE_HOLIDAYS


def session_times(d: date) -> dict:
    """Close / rule-exit / mark times — shifted 3h earlier on half days."""
    if d.isoformat() in EARLY_CLOSE:
        return {"close": "13:00", "exit": "12:50", "mark": "13:10"}
    return {"close": CLOSE_TIME, "exit": EXIT_TIME, "mark": MARK_TIME}


def sessions_between(d0: str, d1: str) -> int:
    """Trading sessions after d0 up to and including d1 (entry day = 0)."""
    a, b = date.fromisoformat(d0), date.fromisoformat(d1)
    n, cur = 0, a + timedelta(days=1)
    while cur <= b:
        if is_trading_day(cur):
            n += 1
        cur += timedelta(days=1)
    return n


# ── indicators (pure) ────────────────────────────────────────────────────────

def sma(closes, n: int):
    if len(closes) < n or n <= 0:
        return None
    return sum(closes[-n:]) / n


def atr(bars, n: int = 20):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-n:]) / n


def rsi(closes, n: int = 2):
    """Wilder RSI over the full history (seeded with the first n changes)."""
    if len(closes) < n + 1:
        return None
    ch = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    ag = sum(max(c, 0) for c in ch[:n]) / n
    al = sum(max(-c, 0) for c in ch[:n]) / n
    for c in ch[n:]:
        ag = (ag * (n - 1) + max(c, 0)) / n
        al = (al * (n - 1) + max(-c, 0)) / n
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    return 100 - 100 / (1 + ag / al)


def ret_pct(closes, n: int):
    if len(closes) < n + 1 or closes[-1 - n] <= 0:
        return None
    return (closes[-1] / closes[-1 - n] - 1) * 100


def pct_rank(values, v) -> float:
    """Percentile of v inside values (100 = the highest)."""
    vals = [x for x in values if x is not None]
    if not vals or v is None:
        return None
    return round(100.0 * sum(1 for x in vals if x <= v) / len(vals), 1)


def features(bars) -> dict:
    """Everything the strategies read, from bars through the prior close."""
    closes = [b["close"] for b in bars]
    if len(closes) < 30:
        return None
    r21, r63 = ret_pct(closes, 21), ret_pct(closes, 63)
    lows = [b["low"] for b in bars]
    return {
        "close": closes[-1], "date": bars[-1]["date"],
        "sma50": sma(closes, 50), "sma200": sma(closes, 200),
        "atr20": atr(bars, 20), "rsi2": rsi(closes, 2),
        "r3d": ret_pct(closes, 3), "r21": r21, "r63": r63,
        "r252": ret_pct(closes, 252),
        "expl_raw": (0.5 * r21 + 0.5 * r63) if None not in (r21, r63) else None,
        "hi63": max(closes[-63:]) if len(closes) >= 63 else None,
        "last4": closes[-4:],
        "r126": ret_pct(closes, 126),
        "sma10": sma(closes, 10), "sma20": sma(closes, 20),
        "hi55": max(closes[-55:]) if len(closes) >= 55 else None,
        "hi252": max(closes[-252:]) if len(closes) >= 252 else None,
        "lo20": min(lows[-20:]) if len(lows) >= 20 else None,
        # QBO: the 10 closes BEFORE the last one = the consolidation box
        "box_hi": max(closes[-11:-1]) if len(closes) >= 11 else None,
        "box_rng": ((max(closes[-11:-1]) / min(closes[-11:-1]) - 1) * 100
                    if len(closes) >= 11 else None),
    }


def universe_features(bars_by_sym: dict, symbols: list) -> dict:
    """{sym: features + expl_rank + r1y_rank}, ranks within `symbols`."""
    feats = {}
    for s in symbols:
        f = features(bars_by_sym.get(s) or [])
        if f:
            feats[s] = f
    expl = [f["expl_raw"] for f in feats.values()]
    r1y = [f["r252"] for f in feats.values()]
    r3m = [f["r63"] for f in feats.values()]
    for f in feats.values():
        f["expl_rank"] = pct_rank(expl, f["expl_raw"])
        f["r1y_rank"] = pct_rank(r1y, f["r252"])
        f["r63_rank"] = pct_rank(r3m, f["r63"])
    return feats


def spy_sma10m(bars) -> float:
    """10-month SMA of COMPLETED month-end closes (Faber timing)."""
    if not bars:
        return None
    month_end = {}
    for b in bars:
        month_end[b["date"][:7]] = b["close"]
    months = sorted(month_end)
    # the last bar's month may still be running — only completed months count
    last_bar = bars[-1]["date"]
    nxt = date.fromisoformat(last_bar) + timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    if nxt.isoformat()[:7] == last_bar[:7]:
        months = months[:-1]
    if len(months) < 10:
        return None
    return sum(month_end[m] for m in months[-10:]) / 10


def breadth50(feats: dict) -> float:
    xs = [f for f in feats.values() if f.get("sma50")]
    if not xs:
        return None
    return round(100.0 * sum(1 for f in xs if f["close"] > f["sma50"]) / len(xs), 1)


# ── strategy candidates (pure) ───────────────────────────────────────────────

def _by(key, reverse=True):
    return lambda kv: ((-(kv[1][key] or 0)) if reverse else (kv[1][key] or 0), kv[0])


def mom_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    out = []
    for s, f in feats.items():
        if None in (f.get("expl_rank"), f.get("sma50"), f.get("sma200"), f.get("r3d")):
            continue
        if (f["expl_rank"] >= c["expl_rank_min"] and f["close"] > f["sma50"] > f["sma200"]
                and f["r3d"] >= 0):
            out.append((s, f))
    return [s for s, _ in sorted(out, key=_by("expl_rank"))]


def pb90_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    out = []
    for s, f in feats.items():
        need = ("expl_rank", "r1y_rank", "sma200", "hi63", "r3d")
        if any(f.get(k) is None for k in need):
            continue
        below = (1 - f["close"] / f["hi63"]) * 100
        if (f["expl_rank"] >= c["expl_rank_min"] and f["r1y_rank"] >= c["r1y_rank_min"]
                and c["pb_lo"] <= below <= c["pb_hi"] and f["r3d"] > 0
                and f["close"] > f["sma200"]):
            out.append((s, f))
    return [s for s, _ in sorted(out, key=_by("expl_rank"))]


def rsi2_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    out = [(s, f) for s, f in feats.items()
           if f.get("sma200") and f.get("rsi2") is not None
           and f["close"] > f["sma200"] and f["rsi2"] < c["rsi_max"]]
    return [s for s, _ in sorted(out, key=_by("rsi2", reverse=False))]


def regime_ok(ctx: dict) -> bool:
    """Risk-on: SPY above its SMA200 and ≥ 50% of stocks above their SMA50."""
    spy = (ctx or {}).get("spy") or {}
    b = (ctx or {}).get("breadth")
    return bool(spy.get("sma200") and spy["close"] > spy["sma200"]
                and b is not None and b >= 50)


def momr_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    """MOM entries, only in a risk-on regime (Faber-style filter)."""
    return mom_candidates(feats, c) if regime_ok(ctx) else []


def brk55_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    """Turtle breakout: close at its 55-session high, above SMA200."""
    out = [(s, f) for s, f in feats.items()
           if f.get("hi55") and f.get("sma200") and f.get("r63") is not None
           and f["close"] >= f["hi55"] and f["close"] > f["sma200"]]
    return [s for s, _ in sorted(out, key=_by("r63"))]


def hi52_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    """52-week-high momentum: within x% of the 1y high, strong, stacked trend."""
    out = []
    for s, f in feats.items():
        if None in (f.get("hi252"), f.get("sma50"), f.get("sma200"), f.get("expl_rank")):
            continue
        if (f["close"] >= f["hi252"] * (1 - c["near_high_pct"] / 100)
                and f["expl_rank"] >= c["expl_rank_min"]
                and f["close"] > f["sma50"] > f["sma200"]):
            out.append((s, f))
    return [s for s, _ in sorted(out, key=_by("expl_rank"))]


def qbo_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    """High-octane breakout: a top-decile 3-month mover that went sideways in
    a tight 10-day box and just closed above it, on rising short MAs."""
    out = []
    for s, f in feats.items():
        need = ("r63_rank", "r63", "box_hi", "box_rng", "sma10", "sma20")
        if any(f.get(k) is None for k in need):
            continue
        if (f["r63_rank"] >= c["r63_rank_min"] and f["r63"] >= c["r63_min"]
                and f["box_rng"] <= c["box_max_pct"] and f["close"] > f["box_hi"]
                and f["close"] > f["sma10"] > f["sma20"]):
            out.append((s, f))
    return [s for s, _ in sorted(out, key=_by("r63"))]


def secrot_score(f: dict):
    if f.get("r63") is None or f.get("r126") is None:
        return None
    return 0.5 * f["r63"] + 0.5 * f["r126"]


def secrot_top(feats: dict, c: dict) -> list:
    """Top-N ETFs by 3m+6m momentum that also pass the absolute filter
    (score > 0 and above SMA200) — dual momentum."""
    sc = [(s, secrot_score(f)) for s, f in feats.items()
          if secrot_score(f) is not None and f.get("sma200")
          and secrot_score(f) > 0 and f["close"] > f["sma200"]]
    sc.sort(key=lambda x: (-x[1], x[0]))
    return [s for s, _ in sc[:c["top_n"]]]


def secrot_candidates(feats: dict, c: dict, ctx: dict = None) -> list:
    """Monthly rotation: buys only in the first sessions of a month."""
    if (ctx or {}).get("som", 99) > c["entry_sessions"]:
        return []
    return secrot_top(feats, c)


CANDIDATES = {"MOM": mom_candidates, "PB90": pb90_candidates, "RSI2": rsi2_candidates,
              "MOMR": momr_candidates, "BRK55": brk55_candidates,
              "HI52": hi52_candidates, "QBO": qbo_candidates,
              "SECROT": secrot_candidates}


def group_of(strategy: str, cfg: dict) -> list:
    return cfg["universe"]["etfs"] if strategy in ETF_STRATEGIES else cfg["universe"]["stocks"]


def initial_stop(strategy: str, entry: float, f: dict, cfg: dict):
    c = cfg[strategy.lower()]
    if "ph1_stop" in c:
        return round(entry * c["ph1_stop"], 2)
    if "stop_pct" in c:
        return round(entry * (1 - c["stop_pct"] / 100), 2)
    a = f.get("atr20")
    if not a:
        return None
    return round(entry - c["atr_stop"] * a, 2)


def initial_target(strategy: str, entry: float, f: dict):
    """PB90 only: retest of the 63-session high (None if already above it)."""
    if strategy != "PB90" or not f.get("hi63"):
        return None
    return round(f["hi63"], 2) if f["hi63"] > entry * 1.005 else None


def mom_add_ok(p: dict, f: dict, last: float, c: dict) -> bool:
    """Platform DOUBLE-DOWN rule: 1M >= +10%, 3D >= 0, within 3% of peak."""
    if (p.get("add_ts") or "").strip() or not f or last is None:
        return False
    peak = max(fnum(p.get("peak_px")) or 0, last)
    return ((f.get("r21") or -1e9) >= c["add_r21_min"] and (f.get("r3d") or -1) >= 0
            and last >= peak * (1 - c["add_within_peak"]))


# ── sizing / fills / fees (pure) ─────────────────────────────────────────────

def size_position(entry: float, stop: float, cfg: dict, heat_used: float,
                  budget_used: float, notional_used: float):
    """(qty, risk, skip_reason). Risk units: qty x stop distance."""
    eq = float(cfg["account_equity"])
    dist = entry - stop if stop is not None else 0
    if dist <= 0:
        return 0, 0.0, "QTY"
    qty = int(eq * cfg["risk_per_trade_pct"] // dist)
    qty = min(qty, int(eq * cfg["max_notional_pct"] // entry))
    if qty < 1:
        return 0, 0.0, "QTY"
    risk = round(qty * dist, 2)
    if budget_used + risk > eq * cfg["daily_new_risk_pct"] + 1e-9:
        return 0, risk, "BUDGET"
    if heat_used + risk > eq * cfg["heat_cap_pct"] + 1e-9:
        return 0, risk, "HEAT"
    if notional_used + qty * entry > eq + 1e-9:
        return 0, risk, "CASH"
    return qty, risk, ""


def tick(px: float) -> float:
    return 0.01 if px >= 1.0 else 0.0001


def tick_up(px: float) -> float:
    t = tick(px)
    return round(math.ceil(round(px / t, 6)) * t, 4)


def tick_down(px: float) -> float:
    t = tick(px)
    return round(math.floor(round(px / t, 6)) * t, 4)


def sim_buy(theo: float, bps: float) -> float:
    return tick_up(theo * (1 + bps / 1e4))


def sim_sell(theo: float, bps: float) -> float:
    return tick_down(theo * (1 - bps / 1e4))


def sell_fees(px: float, qty: float, cfg: dict) -> float:
    sec = px * qty * cfg["sell_fee_bps"] / 1e4
    taf = min(cfg["taf_per_share"] * qty, cfg["taf_cap"])
    return round(sec + taf, 2)


def fnum(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def tier_of(sym: str, cfg: dict) -> str:
    return "etf" if sym in (cfg["universe"].get("etfs") or []) else "large"


# ── campaign math (split-aware) ──────────────────────────────────────────────
# Theo/actual entry prices are stored in the terms of the day they traded
# (immutable). split_factor f turns them into today's terms: px/f, qty*f.
# Adds are converted to entry-day terms at write time. Tracker columns
# (stop_px, peak_px) are always kept in today's terms.

def sf(p: dict) -> float:
    return fnum(p.get("split_factor")) or 1.0


def total_qty(p: dict) -> float:
    """Shares in entry-day terms."""
    return (fnum(p.get("qty")) or 0) + (fnum(p.get("add_qty")) or 0)


def eff_qty(p: dict) -> float:
    return total_qty(p) * sf(p)


def avg_cost(p: dict, actual: bool = False) -> float:
    """Average entry price in TODAY's terms."""
    e = fnum(p.get("entry_px_actual")) if actual else None
    e = e if e is not None else fnum(p.get("entry_px_theo"))
    q1 = fnum(p.get("qty")) or 0
    q2 = fnum(p.get("add_qty")) or 0
    a = None
    if q2:
        a = fnum(p.get("add_px_actual")) if actual else None
        a = a if a is not None else fnum(p.get("add_px_theo"))
    cost = e * q1 + ((a or 0) * q2)
    return cost / (q1 + q2) / sf(p) if (q1 + q2) else 0.0


def campaign_pnl(p: dict, exit_px: float, cfg: dict, actual: bool = False) -> float:
    q = eff_qty(p)
    return round((exit_px - avg_cost(p, actual)) * q - sell_fees(exit_px, q, cfg), 2)


def open_risk(p: dict, ref_px: float) -> float:
    stop = fnum(p.get("stop_px")) or 0
    return max(0.0, (ref_px - stop) * eff_qty(p))


def exit_check(p: dict, last: float):
    """Intraday stop/target: (reason, theo_exit) or None. A stop fills at the
    observed last (it may have gapped through); a target is a resting limit."""
    stop, tgt = fnum(p.get("stop_px")), fnum(p.get("target_px"))
    if tgt is not None:
        tgt = tgt / sf(p)
    if stop is not None and last <= stop:
        return "STOPPED", last
    if tgt is not None and last >= tgt:
        return "TARGET", tgt
    return None


def rule_exit(p: dict, f: dict, last: float, today: str, cfg: dict, held: int = None,
              ctx: dict = None):
    """15:50 rule exits: reason or None. `held` (sessions since entry) may be
    passed by the backtester, whose history predates NYSE_HOLIDAYS."""
    strat = p.get("strategy")
    entry_day = (p.get("entry_ts") or "")[:10]
    if held is None:
        held = sessions_between(entry_day, today)
    if strat == "RSI2":
        c = cfg["rsi2"]
        if f and len(f.get("last4") or []) == c["exit_sma"] - 1:
            sma_now = (sum(f["last4"]) + last) / c["exit_sma"]
            if last > sma_now:
                return "RULE"
        if held >= c["time_stop_sessions"]:
            return "TIME"
    elif strat == "PB90":
        if held >= cfg["pb90"]["time_stop_sessions"]:
            return "TIME"
    elif family(strat) == "MOM":
        c = cfg[strat.lower()]
        days = (date.fromisoformat(today) - date.fromisoformat(entry_day)).days
        r = (last / avg_cost(p) - 1) * 100 if avg_cost(p) else 0
        if days >= c["review_days"] and abs(r) <= c["review_band"]:
            return "REVIEW"
    elif strat == "BRK55":
        if f and f.get("lo20") and last < f["lo20"]:
            return "TRAIL"                              # Turtle 20-day-low exit
    elif strat == "HI52":
        if f and f.get("sma50") and last < f["sma50"]:
            return "TREND"
    elif strat == "QBO":
        if f and f.get("sma10") and held >= 1 and last < f["sma10"]:
            return "TRAIL"                              # close below the 10-day MA
        if held >= cfg["qbo"]["time_stop_sessions"]:
            return "TIME"
    elif strat == "SECROT":
        c = cfg["secrot"]
        ctx = ctx or {}
        if ctx.get("som") == 1 and ctx.get("etfs") is not None \
                and p.get("symbol") not in secrot_top(ctx["etfs"], c):
            return "ROTATE"
    return None


def trail_stop(p: dict, peak: float, cfg: dict):
    """New stop in today's terms: MOM phase 2 trails the peak; else fixed."""
    cur = fnum(p.get("stop_px"))
    if family(p.get("strategy")) == "MOM" and str(p.get("phase")) == "2" and peak:
        new = round(peak * cfg[p["strategy"].lower()]["ph2_trail"], 2)
        return max(cur or 0, new)
    return cur


SPLIT_RATIOS = (2, 3, 4, 5, 10, 1.5, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 2 / 3)


def detect_split(prev_mark_close: float, adj_close_same_day: float):
    """Ratio R if the adjusted history now shows the prior mark divided by a
    clean split ratio (prev mark / adjusted close == R within 3%)."""
    if not prev_mark_close or not adj_close_same_day:
        return None
    r = prev_mark_close / adj_close_same_day
    for R in SPLIT_RATIOS:
        if abs(r - R) <= 0.03 * R:
            return R
    return None


# ── journal helpers ──────────────────────────────────────────────────────────

def _f2(x):
    return "" if x is None else f"{x:.2f}"


def in_paper(cfg: dict, strategy: str) -> bool:
    """Only strategies promoted past their backtest (stage: paper) take new
    entries. Open campaigns of a demoted strategy keep being tracked/exited."""
    c = cfg.get(strategy.lower()) or {}
    return bool(c.get("enabled")) and c.get("stage") == "paper"


def entry_pending(ds: str, strategy: str) -> bool:
    return not any(r.get("action") == "DONE"
                   for r in st.signals_for(ds, strategy, ENTRY_SLOT))


def realized(p: dict):
    v = fnum(p.get("pnl_actual"))
    return v if v is not None else fnum(p.get("pnl_theo"))


def last_marks() -> dict:
    out = {}
    for m in st.read("marks"):
        out[m["position_id"]] = m
    return out


def ref_price(p: dict, quotes: dict, marks: dict) -> float:
    q = quotes.get(p["symbol"])
    if q:
        return q
    m = fnum((marks.get(p["position_id"]) or {}).get("close"))
    return m if m else avg_cost(p)


def book_state(ds: str, quotes: dict) -> dict:
    """heat / notional / today's new risk — re-derived from the journal."""
    marks = last_marks()
    heat = notional = 0.0
    for p in st.open_positions():
        px = ref_price(p, quotes, marks)
        heat += open_risk(p, px)
        notional += eff_qty(p) * px
    budget = sum(fnum(r.get("risk_usd")) or 0 for r in st.rows_for_date("signals", ds)
                 if r.get("action") in ("BUY", "ADD"))
    return {"heat": heat, "notional": notional, "budget": budget}


def _event(ts, pid, ev, px=None, qty=None, note=""):
    st.append("events", {"ts": ts, "date": ts[:10], "position_id": pid, "event": ev,
                         "px": "" if px is None else f"{px:.4f}".rstrip("0").rstrip("."),
                         "qty": "" if qty is None else qty, "note": note})


# ── session steps ────────────────────────────────────────────────────────────

def universe(cfg) -> list:
    return list(cfg["universe"]["stocks"]) + list(cfg["universe"]["etfs"])


def build_features(cfg, bars: dict) -> dict:
    """{'stocks': feats ranked among stocks, 'etfs': feats among ETFs}."""
    return {"stocks": universe_features(bars, cfg["universe"]["stocks"]),
            "etfs": universe_features(bars, cfg["universe"]["etfs"])}


def session_of_month(ds: str) -> int:
    """1 on the month's first NYSE session, 2 on the second, …"""
    d = date.fromisoformat(ds)
    cur, n = d.replace(day=1), 0
    while cur <= d:
        n += is_trading_day(cur)
        cur += timedelta(days=1)
    return n


def session_ctx(fe: dict, ds: str, som: int = None) -> dict:
    """Cross-sectional context the strategies may read (regime, calendar)."""
    return {"today": ds, "som": som if som is not None else session_of_month(ds),
            "spy": fe["etfs"].get("SPY"), "breadth": breadth50(fe["stocks"]),
            "etfs": fe["etfs"]}


def feat_for(fe: dict, sym: str):
    return fe["stocks"].get(sym) or fe["etfs"].get(sym)


def heal_splits(bars: dict, ts: str) -> list:
    """Apply splits to open campaigns (idempotent per position per day)."""
    marks = last_marks()
    done = {(e["position_id"], e["date"]) for e in st.read("events")
            if e.get("event") == "SPLIT"}
    healed = []
    for p in st.open_positions():
        pid = p["position_id"]
        m = marks.get(pid)
        if not m or (pid, ts[:10]) in done:
            continue
        adj = {b["date"]: b["close"] for b in bars.get(p["symbol"]) or []}
        R = detect_split(fnum(m.get("close")), adj.get(m["date"]))
        if not R:
            continue
        upd = {"split_factor": f"{sf(p) * R:.6g}"}
        for k in ("stop_px", "peak_px"):
            v = fnum(p.get(k))
            if v:
                upd[k] = f"{v / R:.2f}"
        st.update_position(pid, upd, allow=st.TRACKER_COLS)
        _event(ts, pid, "SPLIT", R, None, f"ratio {R:g} healed")
        healed.append((p["symbol"], R))
    return healed


def do_premarket(cfg, ds: str, data, clock) -> tuple:
    """Write the day row (once) and return (day_row, features)."""
    bars, src, failed = data.universe_bars(universe(cfg), ds)
    fe = build_features(cfg, bars)
    existing = st.rows_for_date("day", ds)
    if existing:
        return existing[0], fe
    ts = iso(clock.now())
    healed = heal_splits(bars, ts)
    spy = bars.get("SPY") or []
    spy_close = spy[-1]["close"] if spy else None
    s10 = spy_sma10m(spy)
    s200 = sma([b["close"] for b in spy], 200) if spy else None
    try:
        vix = data.vix_last()
    except Exception:
        vix = None
    n = len(universe(cfg))
    status = "OK" if len(failed) <= n // 2 else "DATA_FAIL"
    notes = []
    if failed:
        notes.append(f"no bars: {' '.join(failed[:12])}{' …' if len(failed) > 12 else ''}")
    if healed:
        notes.append("splits: " + ", ".join(f"{s} {r:g}:1" for s, r in healed))
    row = {"date": ds, "status": status, "spy_close": _f2(spy_close),
           "spy_sma200": _f2(s200), "spy_sma10m": _f2(s10),
           "spy_regime": ("" if None in (spy_close, s10)
                          else ("ABOVE" if spy_close >= s10 else "BELOW")),
           "vix": _f2(vix), "breadth50": breadth50(fe["stocks"]) or "",
           "bars_source": " ".join(f"{k}:{v}" for k, v in sorted(src.items())),
           "notes": "; ".join(notes)}
    st.append("day", row)
    return row, fe


def _sig(ds, ts, strategy, action, **kw):
    row = {"ts": ts, "date": ds, "slot": ENTRY_SLOT, "strategy": strategy,
           "action": action, "side": "LONG" if action in ("BUY", "ADD") else ""}
    row.update(kw)
    st.append("signals", row)


def _cand_fields(f: dict) -> dict:
    if not f:
        return {}
    return {"expl_rank": f.get("expl_rank") or "", "r3d": _f2(f.get("r3d")),
            "r21": _f2(f.get("r21")), "rsi2": _f2(f.get("rsi2")),
            "sma50": _f2(f.get("sma50")), "sma200": _f2(f.get("sma200")),
            "atr20": _f2(f.get("atr20")), "ref_close": _f2(f.get("close"))}


def skip_slot(ds: str, ts: str, strategy: str, reason: str, note: str = ""):
    _sig(ds, ts, strategy, "DONE", skip_reason=reason, note=note)


def do_entries(cfg, ds: str, day_row: dict, fe: dict, data, clock, strategy: str):
    """The 09:45 slot for one strategy. Candidate-level idempotent; the slot
    closes with a DONE row (skip_reason NOSIGNAL when nothing qualified)."""
    ts = iso(clock.now())
    key = strategy.lower()
    c = cfg[key]
    feats = fe["etfs"] if strategy in ETF_STRATEGIES else fe["stocks"]
    cands = CANDIDATES[strategy](feats, c, session_ctx(fe, ds))
    if day_row.get("status") == "DATA_FAIL":
        skip_slot(ds, ts, strategy, "DATA", "premarket bars failed")
        return
    held = st.open_positions(strategy)
    logged = {r.get("symbol") for r in st.signals_for(ds, strategy, ENTRY_SLOT)}
    need = set(cands) | {p["symbol"] for p in held}
    try:
        quotes = data.quotes(sorted(need)) if need else {}
    except Exception as e:
        skip_slot(ds, ts, strategy, "DATA", f"quotes: {e}")
        return

    # adds first (MOM double-down) — they belong to already-proven names
    if family(strategy) == "MOM":
        for p in held:
            sym, pid = p["symbol"], p["position_id"]
            last = quotes.get(sym)
            if (p.get("add_ts") or "")[:10] == ds and sym not in logged:
                _sig(ds, ts, strategy, "ADD", symbol=sym, position_id=pid,
                     qty=p.get("add_qty"), note="recovered after restart")
                continue
            if sym in logged or not mom_add_ok(p, feat_for(fe, sym), last, c):
                continue
            b = book_state(ds, quotes)
            stop_now = round(max(fnum(p.get("peak_px")) or 0, last) * c["ph2_trail"], 2)
            qty_now = int(round(eff_qty(p)))          # same size again
            risk = round(qty_now * max(0.0, last - stop_now), 2)
            # heat after the add: the whole campaign re-risked to the new stop
            heat_after = (b["heat"] - open_risk(p, last)
                          + open_risk({**p, "stop_px": stop_now}, last) + risk)
            eq = float(cfg["account_equity"])
            reason = ""
            if b["budget"] + risk > eq * cfg["daily_new_risk_pct"] + 1e-9:
                reason = "BUDGET"
            elif heat_after > eq * cfg["heat_cap_pct"] + 1e-9:
                reason = "HEAT"
            elif b["notional"] + qty_now * last > eq + 1e-9:
                reason = "CASH"
            if reason:
                _sig(ds, ts, strategy, "SKIP", symbol=sym, position_id=pid,
                     skip_reason=reason, note="add", last=_f2(last),
                     **_cand_fields(feat_for(fe, sym)))
                continue
            bps = cfg["slippage_bps"][tier_of(sym, cfg)]
            f_ = sf(p)
            st.update_position(pid, {"add_ts": ts, "add_qty": f"{qty_now / f_:.6g}",
                                     "add_px_theo": f"{last * f_:.4f}"},
                               allow=st.WRITE_ONCE)
            st.update_position(pid, {"add_px_actual": f"{sim_buy(last, bps) * f_:.4f}",
                                     "phase": "2", "stop_px": f"{stop_now:.2f}"},
                               allow=st.ACTUAL_COLS | st.TRACKER_COLS)
            _event(ts, pid, "ADD", last, qty_now, "double-down → phase 2")
            _sig(ds, ts, strategy, "ADD", symbol=sym, position_id=pid, qty=qty_now,
                 last=_f2(last), stop_px=_f2(stop_now), risk_usd=_f2(risk),
                 **_cand_fields(feat_for(fe, sym)))
            logged.add(sym)

    held_syms = {p["symbol"] for p in st.open_positions(strategy)}
    n_open = len(held_syms)
    n_new = sum(1 for r in st.signals_for(ds, strategy, ENTRY_SLOT) if r.get("action") == "BUY")
    for rank, sym in enumerate(cands, 1):
        if sym in logged:
            continue
        f = feats[sym]
        pid = f"{ds}-{strategy}-{sym}"
        base = dict(symbol=sym, rank=rank, **_cand_fields(f))
        existing = st.get_position(pid)
        if existing is not None:                       # crash between writes
            _sig(ds, ts, strategy, "BUY", position_id=pid, qty=existing.get("qty"),
                 last=existing.get("entry_px_theo"), stop_px=existing.get("stop_px_initial"),
                 target_px=existing.get("target_px"), risk_usd=existing.get("risk_usd"),
                 note="recovered after restart", **base)
            n_new += 1
            n_open += 1
            continue
        if sym in held_syms:
            _sig(ds, ts, strategy, "SKIP", skip_reason="HELD", **base)
            continue
        if n_new >= c["max_new_per_day"] or n_open >= c["max_open"]:
            _sig(ds, ts, strategy, "SKIP", skip_reason="MAXPOS", **base)
            continue
        last = quotes.get(sym)
        if not last:
            _sig(ds, ts, strategy, "SKIP", skip_reason="DATA", note="no quote", **base)
            continue
        stop = initial_stop(strategy, last, f, cfg)
        tgt = initial_target(strategy, last, f)
        b = book_state(ds, quotes)
        qty, risk, reason = size_position(last, stop, cfg, b["heat"], b["budget"],
                                          b["notional"])
        if reason:
            _sig(ds, ts, strategy, "SKIP", skip_reason=reason, last=_f2(last),
                 stop_px=_f2(stop), risk_usd=_f2(risk), **base)
            continue
        tier = tier_of(sym, cfg)
        fill = sim_buy(last, cfg["slippage_bps"][tier])
        st.add_position({
            "position_id": pid, "strategy": strategy, "symbol": sym, "side": "LONG",
            "tier": tier, "signal_ts": ts, "entry_ts": ts, "qty": qty,
            "entry_px_theo": f"{last:.4f}", "stop_px_initial": f"{stop:.2f}",
            "target_px": _f2(tgt), "risk_usd": f"{risk:.2f}",
            "stop_px": f"{stop:.2f}", "peak_px": f"{last:.2f}", "phase": "1",
            "split_factor": "1", "entry_px_actual": f"{fill:.4f}",
            "fill_notes": "simulated"})
        _event(ts, pid, "ENTRY", last, qty, f"sim fill {fill:.2f}")
        _sig(ds, ts, strategy, "BUY", position_id=pid, qty=qty, last=_f2(last),
             stop_px=_f2(stop), target_px=_f2(tgt), risk_usd=f"{risk:.2f}", **base)
        n_new += 1
        n_open += 1
        held_syms.add(sym)
    buys = sum(1 for r in st.signals_for(ds, strategy, ENTRY_SLOT) if r.get("action") == "BUY")
    adds = sum(1 for r in st.signals_for(ds, strategy, ENTRY_SLOT) if r.get("action") == "ADD")
    skip_slot(ds, ts, strategy, "" if (cands or adds) else "NOSIGNAL",
              f"{len(cands)} candidates, {buys} buys, {adds} adds")


def close_campaign(cfg, p: dict, theo: float, reason: str, ts: str) -> dict:
    bps = cfg["slippage_bps"].get(p.get("tier") or "large", 5)
    fill = sim_sell(theo, bps)
    manual_exit = fnum(p.get("exit_px_actual"))
    ex_act = manual_exit if manual_exit is not None else fill
    upd = {"exit_ts": ts, "exit_px_theo": f"{theo:.4f}", "exit_reason": reason,
           "pnl_theo": f"{campaign_pnl(p, theo, cfg):.2f}"}
    st.update_position(p["position_id"], upd, allow=st.WRITE_ONCE)
    st.update_position(p["position_id"],
                       {"exit_px_actual": f"{ex_act:.4f}",
                        "pnl_actual": f"{campaign_pnl(p, ex_act, cfg, actual=True):.2f}"},
                       allow=st.ACTUAL_COLS)
    _event(ts, p["position_id"], "EXIT", theo, eff_qty(p), reason)
    return upd


def do_tracking(cfg, data, clock, rule_exits: bool, fe: dict, ds: str) -> int:
    """One pass: stops/targets on every open campaign (+ rule exits in the
    15:50 window). Returns the number of campaigns closed."""
    opens = st.open_positions()
    if not opens:
        return 0
    try:
        q = data.quotes(sorted({p["symbol"] for p in opens}))
    except Exception as e:
        print(f"track: quotes failed: {e}", flush=True)
        return 0
    ts = iso(clock.now())
    n = 0
    for p in opens:
        last = q.get(p["symbol"])
        if not last:
            continue
        hit = exit_check(p, last)
        if hit:
            close_campaign(cfg, p, hit[1], hit[0], ts)
            n += 1
            continue
        if rule_exits:
            why = rule_exit(p, feat_for(fe, p["symbol"]), last, ds, cfg,
                            ctx=session_ctx(fe, ds))
            if why:
                close_campaign(cfg, p, last, why, ts)
                n += 1
    return n


def do_mark(cfg, ds: str, data, clock) -> dict:
    """End-of-day: mark every open campaign (once per date), move trailing
    stops, write the eod row. Idempotent by (date, position_id) and date."""
    ts = iso(clock.now())
    opens = st.open_positions()
    try:
        q = data.quotes(sorted({p["symbol"] for p in opens})) if opens else {}
    except Exception as e:
        print(f"mark: quotes failed ({e}) — marking at last marks", flush=True)
        q = {}
    already = {m["position_id"] for m in st.rows_for_date("marks", ds)}
    prev = last_marks()
    all_marks = st.read("marks")
    for p in opens:
        pid = p["position_id"]
        if pid in already:
            continue
        close = q.get(p["symbol"])
        stale = close is None
        if stale:
            close = fnum((prev.get(pid) or {}).get("close")) or avg_cost(p)
            trail = [m for m in all_marks if m["position_id"] == pid][-(STALE_MARKS_DELIST - 1):]
            if (len(trail) >= STALE_MARKS_DELIST - 1
                    and all(m.get("stale") == "1" for m in trail)):
                close_campaign(cfg, p, close, "DELISTED", ts)
                continue
        peak = max(fnum(p.get("peak_px")) or 0, close)
        new_stop = trail_stop({**p, "peak_px": peak}, peak, cfg)
        upd = {"peak_px": f"{peak:.2f}"}
        if new_stop is not None and new_stop != fnum(p.get("stop_px")):
            upd["stop_px"] = f"{new_stop:.2f}"
            _event(ts, pid, "STOP_MOVE", new_stop, None, f"peak {peak:.2f}")
        st.update_position(pid, upd, allow=st.TRACKER_COLS)
        p = {**p, **upd}
        st.append("marks", {"date": ds, "position_id": pid, "strategy": p["strategy"],
                            "symbol": p["symbol"], "close": f"{close:.2f}",
                            "qty": f"{eff_qty(p):.6g}", "avg_cost": f"{avg_cost(p):.4f}",
                            "unrealized": f"{(close - avg_cost(p)) * eff_qty(p):.2f}",
                            "peak_px": p.get("peak_px"), "stop_px": p.get("stop_px"),
                            "phase": p.get("phase"), "stale": "1" if stale else ""})
    if st.rows_for_date("eod", ds):
        return st.rows_for_date("eod", ds)[0]
    return write_eod(cfg, ds)


def write_eod(cfg, ds: str) -> dict:
    positions = st.read("positions")
    closed = [p for p in positions if not st.is_open(p)]
    r_today = sum(realized(p) or 0 for p in closed if (p.get("exit_ts") or "")[:10] == ds)
    r_cum = sum(realized(p) or 0 for p in closed if (p.get("exit_ts") or "")[:10] <= ds)
    marks = {m["position_id"]: m for m in st.rows_for_date("marks", ds)}
    opens = [p for p in positions if st.is_open(p)]
    unreal = sum(fnum((marks.get(p["position_id"]) or {}).get("unrealized")) or 0 for p in opens)
    heat = notional = 0.0
    for p in opens:
        px = fnum((marks.get(p["position_id"]) or {}).get("close")) or avg_cost(p)
        heat += open_risk(p, px)
        notional += eff_qty(p) * px
    row = {"date": ds, "open_count": len(opens), "realized_today": _f2(r_today),
           "realized_cum": _f2(r_cum), "unrealized": _f2(unreal),
           "equity_est": _f2(float(cfg["account_equity"]) + r_cum + unreal),
           "heat": _f2(heat), "notional": _f2(notional)}
    st.append("eod", row)
    return row


# ── the session loop ─────────────────────────────────────────────────────────

class RealClock:
    def now(self):
        return now_et()

    def sleep(self, s):
        time.sleep(s)


def run_session(cfg: dict, data, clock) -> str:
    """Run today's session to completion. Re-entrant: every step re-derives
    its state from the journal. Returns a short outcome string."""
    d = clock.now().date()
    ds = d.isoformat()
    if not is_trading_day(d):
        if d.weekday() < 5 and not st.rows_for_date("day", ds):
            st.append("day", {"date": ds, "status": "SKIPPED_HOLIDAY"})
        return "closed"
    if st.rows_for_date("eod", ds):
        return "done"
    pm = at(PREMARKET_TIME, d)
    if clock.now() < pm:
        clock.sleep((pm - clock.now()).total_seconds())
    day_row, fe = do_premarket(cfg, ds, data, clock)
    times = session_times(d)
    t_entry, t_exit = at(ENTRY_SLOT, d), at(times["exit"], d)
    t_close, t_mark = at(times["close"], d), at(times["mark"], d)
    print(f"stocks session {ds} | {day_row.get('status')} | SPY {day_row.get('spy_regime')}"
          f" | breadth50 {day_row.get('breadth50')}", flush=True)
    while True:
        now = clock.now()
        if now.date() != d:
            return "rolled"
        for strat in STRATEGIES:
            if not in_paper(cfg, strat) or not entry_pending(ds, strat):
                continue
            if now < t_entry:
                continue
            if now - t_entry > timedelta(minutes=ENTRY_GRACE_MIN):
                skip_slot(ds, iso(now), strat, "MISSED",
                          "engine offline through the entry window")
                continue
            try:
                do_entries(cfg, ds, day_row, fe, data, clock, strat)
            except Exception as e:     # a bug in one strategy never blocks the rest
                print(f"entries {strat}: {e!r}", flush=True)
                skip_slot(ds, iso(clock.now()), strat, "DATA", f"error: {e!r}"[:200])
        now = clock.now()
        if t_entry <= now < t_close:
            do_tracking(cfg, data, clock, now >= t_exit, fe, ds)
        if now >= t_mark:
            row = do_mark(cfg, ds, data, clock)
            print(f"marked {ds}: open {row.get('open_count')} realized "
                  f"{row.get('realized_today')} unrealized {row.get('unrealized')}",
                  flush=True)
            return "done"
        # sleep to the next event: tracking tick, entry, or the mark
        nxt = now + timedelta(seconds=TRACK_INTERVAL_S)
        for t in (t_entry, t_exit, t_mark):
            if now < t < nxt:
                nxt = t
        if now >= t_close:
            nxt = t_mark
        clock.sleep(max(1.0, (nxt - now).total_seconds()))


# ── manual fills (paperMoney mirror) ─────────────────────────────────────────

def apply_fill(cfg, position_id: str, entry=None, add=None, exit_=None, note=None) -> dict:
    p = st.get_position(position_id)
    if p is None:
        raise KeyError(position_id)
    upd = {}
    if entry is not None:
        upd["entry_px_actual"] = f"{float(entry):.4f}"
    if add is not None:
        if not (p.get("add_ts") or "").strip():
            raise ValueError("campaign has no add")
        upd["add_px_actual"] = f"{float(add):.4f}"
    if exit_ is not None:
        if st.is_open(p):
            raise ValueError("campaign still open — the engine books exits")
        upd["exit_px_actual"] = f"{float(exit_):.4f}"
    if note is not None:
        upd["fill_notes"] = note
    q = {**p, **upd}
    if not st.is_open(q) and fnum(q.get("exit_px_actual")) is not None:
        upd["pnl_actual"] = f"{campaign_pnl(q, fnum(q['exit_px_actual']), cfg, actual=True):.2f}"
    st.update_position(position_id, upd, allow=st.ACTUAL_COLS)
    return upd


def cmd_status(cfg):
    ds = now_et().date().isoformat()
    b = book_state(ds, {})
    print(f"open campaigns: {len(st.open_positions())} | heat ${b['heat']:.0f} | "
          f"notional ${b['notional']:.0f} | today's new risk ${b['budget']:.0f}")
    for p in st.open_positions():
        print(f"  {p['position_id']:<28} {p['symbol']:<5} qty {eff_qty(p):g} "
              f"avg {avg_cost(p):.2f} stop {p.get('stop_px')} phase {p.get('phase')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stocks & ETF paper sandbox")
    ap.add_argument("cmd", choices=["run", "status", "report"])
    a = ap.parse_args(argv)
    cfg = load_config()
    if a.cmd == "run":
        import stocks_data
        print(run_session(cfg, stocks_data, RealClock()), flush=True)
    elif a.cmd == "status":
        cmd_status(cfg)
    else:
        import stocks_report
        print(stocks_report.text_report(cfg))


if __name__ == "__main__":
    sys.exit(main())
