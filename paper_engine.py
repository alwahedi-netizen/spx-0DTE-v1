"""
paper_engine.py — METF + Band Condor paper-mode signal logger
=============================================================
Signal generation + journaling ONLY. No order routing, paper or live — the
human executes in thinkorswim paperMoney and back-fills actual fills with
`fill`. GEX sign is recorded as a tag, never used as an entry condition.

CLI (the spec's `engine paper ...`):
    python3 paper_engine.py run             # full-day loop, idempotent
    python3 paper_engine.py status          # open positions, risk used vs budget
    python3 paper_engine.py fill <position_id> --credit 1.45 --exit 0.00 --note "..."
    python3 paper_engine.py report --weeks 1

Rules implemented (paper_config.yaml holds the one fixed config):
- METF: at each slot, EMA(20/40) on 1-min SPX decides the side (fast>slow ->
  sell PUT vertical below, else CALL vertical above); strikes picked by
  credit (furthest OTM with credit >= target), stop at credit*(1+multiple),
  hold to expiry.
- Band condor: 10:30 expected move = ATM straddle mid * em_factor, rounded
  out to 5s; skew inside [lo,hi] -> iron condor at the band edges, outside
  -> single vertical on the cushioned side. Stop per side = total credit
  collected (single vertical: its credit x2). TP each short at 0.05.
- Every position is tracked ~1/min 09:35-16:00, stopped/TP'd from chain
  mids, and settled at intrinsic vs the 16:00 SPX print. 16:05 writes band
  containment for tomorrow's sizing.

All schedule times are America/New_York; timestamps are ET ISO-8601 with
offset. Pure logic lives in module-level functions with no network imports so
tests_paper.py runs offline; all Schwab I/O goes through paper_data.py.
"""

import argparse
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import paper_store as st

ET = ZoneInfo("America/New_York")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "paper_config.yaml"

PREMARKET_TIME = "09:00"
TRACK_START = "09:35"
SETTLE_TIME = "16:00"
CONTAIN_TIME = "16:05"
TRACK_INTERVAL_S = 60        # spec allows dropping to 2-3 min if rate-limited
SLOT_GRACE_MIN = 5           # a slot missed by more than this logs SKIP/DATA
STRIKE_STEP = 5.0

# FOMC decision days — auto-added to skip_dates. FOMC-minutes and CPI dates
# go in paper_config.yaml's skip_dates by hand (no reliable free source).
FOMC_2026 = {"2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"}

DEFAULTS = {
    "timezone": "America/New_York",
    "account_equity": 100000,
    "daily_risk_pct": 0.015,
    "skip_dates": [],
    "metf": {
        "enabled": True,
        "slots": ["10:00", "10:45", "11:30", "12:30", "13:30", "14:15"],
        "ema_fast": 20, "ema_slow": 40, "ema_bar": "1min",
        "width": 30, "target_credit": 1.50, "min_credit": 1.25,
        "stop_multiple": 1.0, "hold_to_expiry": True, "contracts": 1,
    },
    "band": {
        "enabled": True,
        "band_time": "10:30", "entry_time": "10:35",
        "em_factor": 0.85, "wing_width": 30,
        "skew_lo": 0.80, "skew_hi": 1.25,
        "stop_rule": "total_credit_per_side", "take_profit_short": 0.05,
        "containment_window": 20, "size_full_above": 0.70,
        "size_half_above": 0.55, "contracts": 1,
    },
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


# ── time helpers ─────────────────────────────────────────────────────────────

def now_et() -> datetime:
    return datetime.now(ET)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def at(hhmm: str, d: date) -> datetime:
    h, m = hhmm.split(":")
    return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=ET)


# ── chain helpers (Schwab callExpDateMap/putExpDateMap readers) ─────────────

def contract_map(chain: dict, expiry: str, side: str) -> dict:
    """strike -> contract dict (bid/ask/delta) for the expiry. side: call|put."""
    out = {}
    for exp_key, strikes in (chain.get(f"{side}ExpDateMap") or {}).items():
        if exp_key.startswith(expiry):
            for k, lst in strikes.items():
                if lst:
                    out[float(k)] = lst[0]
    return out


def mid(c: dict):
    b, a = c.get("bid"), c.get("ask")
    if b is not None and a is not None and (b + a) > 0:
        return (b + a) / 2
    return c.get("mark") or c.get("last")


def leg_ok(c: dict) -> bool:
    """Quote-quality rail: far-OTM strikes quote e.g. 0.15x0.60 — a fictional
    mid that would price credits nobody would ever fill."""
    b, a = c.get("bid"), c.get("ask")
    if b is None or a is None or a <= 0:
        return False
    m = (a + b) / 2
    return m > 0 and (a - b) <= max(0.30, 0.25 * m)


def spot_of(chain: dict) -> float:
    u = chain.get("underlying") or {}
    s = chain.get("underlyingPrice") or u.get("mark") or u.get("last") or u.get("close")
    if not s:
        raise ValueError("no underlying price in chain")
    return float(s)


# ── METF logic ───────────────────────────────────────────────────────────────

def ema_last(closes, n: int):
    """Classic EMA: SMA seed over the first n, then recursive. Needs len>=n."""
    if len(closes) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(closes[:n]) / n
    for c in closes[n:]:
        e = c * k + e * (1 - k)
    return e


def metf_state(closes, fast_n: int, slow_n: int):
    """('UP'|'DOWN', ema_fast, ema_slow). Equality -> DOWN (conservative)."""
    ef, es = ema_last(closes, fast_n), ema_last(closes, slow_n)
    if ef is None or es is None:
        return None, ef, es
    return ("UP" if ef > es else "DOWN"), ef, es


def metf_side(state: str) -> str:
    return "PUT" if state == "UP" else "CALL"


def walk_strikes(cmap: dict, side: str, spot: float, width: float,
                 target_credit: float, min_credit: float):
    """Pick a credit vertical by walking OTM from spot in 5-pt steps.

    Returns (pick, None) or (None, 'CREDIT'). pick: dict with short/long
    strike, credit, mids, delta. Rule: furthest OTM short whose credit >=
    target_credit; if none qualifies, the best (highest-credit) candidate,
    unless even that is < min_credit."""
    if side == "PUT":
        shorts = sorted([k for k in cmap if k < spot], reverse=True)  # nearest OTM first
    else:
        shorts = sorted([k for k in cmap if k > spot])
    cands = []
    for k in shorts:
        lk = k - width if side == "PUT" else k + width
        cs, cl = cmap.get(k), cmap.get(lk)
        if cs is None or cl is None or not leg_ok(cs):
            continue
        ms, ml = mid(cs), mid(cl)
        if ms is None or ml is None:
            continue
        credit = ms - ml
        if credit <= 0:
            continue
        cands.append({"short_strike": k, "long_strike": lk, "credit": credit,
                      "short_mid": ms, "long_mid": ml,
                      "short_delta": cs.get("delta")})
    if not cands:
        return None, "CREDIT"
    qual = [c for c in cands if c["credit"] >= target_credit]
    if qual:
        # furthest OTM: lowest strike for puts, highest for calls
        pick = min(qual, key=lambda c: c["short_strike"]) if side == "PUT" \
            else max(qual, key=lambda c: c["short_strike"])
        return pick, None
    best = max(cands, key=lambda c: c["credit"])
    if best["credit"] < min_credit:
        return None, "CREDIT"
    return best, None


# ── band logic ───────────────────────────────────────────────────────────────

def band_metrics(spot: float, straddle_mid: float, em_factor: float):
    """(em, lower, upper, skew) — band edges rounded outward to 5s."""
    em = straddle_mid * em_factor
    upper = math.ceil((spot + em) / STRIKE_STEP) * STRIKE_STEP
    lower = math.floor((spot - em) / STRIKE_STEP) * STRIKE_STEP
    skew = (upper - spot) / (spot - lower)
    return em, lower, upper, skew


def band_structure(skew: float, lo: float, hi: float) -> str:
    if skew > hi:
        return "CALL_VERTICAL"    # more headroom above = cushioned side
    if skew < lo:
        return "PUT_VERTICAL"
    return "IRON_CONDOR"


def containment_size(contained_history, window: int, full_above: float,
                     half_above: float):
    """(size_factor|None, rc, warmup). None size => SKIP_CONTAINMENT.
    Before `window` days of history, rc is treated as 1.0 but flagged."""
    vals = [v for v in contained_history if v in (0, 1)]
    if len(vals) < window:
        return 1.0, 1.0, True
    rc = sum(vals[-window:]) / window
    if rc >= full_above:
        return 1.0, rc, False
    if rc >= half_above:
        return 0.5, rc, False
    return None, rc, False


# ── risk / stops / settlement ────────────────────────────────────────────────

def stop_risk(credit: float, stop_level: float, contracts: int) -> float:
    """Dollar loss if this side is stopped exactly at stop_level."""
    return max(0.0, (stop_level - credit)) * 100 * contracts


def open_stop_risk(positions=None) -> float:
    total = 0.0
    for p in (st.open_positions() if positions is None else positions):
        try:
            total += stop_risk(float(p["credit_theo"]), float(p["stop_level"]),
                               int(float(p.get("contracts") or 1)))
        except (ValueError, KeyError):
            continue
    return total


def risk_ok(open_risk: float, new_risk: float, budget: float) -> bool:
    return open_risk + new_risk <= budget


def stop_triggered(spread_value: float, stop_level: float) -> bool:
    return spread_value >= stop_level


def intrinsic(side: str, strike: float, spx: float) -> float:
    return max(0.0, spx - strike) if side == "CALL" else max(0.0, strike - spx)


def settle_value(side: str, short_strike: float, long_strike: float,
                 spx_close: float) -> float:
    return intrinsic(side, short_strike, spx_close) - intrinsic(side, long_strike, spx_close)


def vertical_pnl(credit: float, exit_value: float, contracts: int) -> float:
    return (credit - exit_value) * 100 * contracts


# ── idempotency helpers ──────────────────────────────────────────────────────

def pending_metf_slots(cfg: dict, d: str) -> list:
    done = {r.get("slot") for r in st.signals_for(d, "METF")}
    return [s for s in cfg["metf"]["slots"] if s not in done]


def band_signal_pending(cfg: dict, d: str) -> bool:
    return not st.signals_for(d, "BAND")


def band_row_for(d: str):
    rows = st.rows_for_date("band", d)
    return rows[0] if rows else None


def _fmt(x, nd=2):
    if x is None:
        return ""
    return f"{float(x):.{nd}f}"


def _signal_row(cfg, day_row, **kw) -> dict:
    row = {"ts": kw.pop("ts", iso(now_et())), "date": day_row["date"],
           "gex_sign": day_row.get("gex_sign", ""), "vix": day_row.get("vix", "")}
    row.update(kw)
    return row


# ══════════════════════════════════════════════════════════════════════════════
# Run-time event handlers (network via paper_data only; never raise on data
# problems past this point — a data problem is a SKIP/DATA row, not a crash)
# ══════════════════════════════════════════════════════════════════════════════

def do_premarket(cfg: dict, d: date) -> dict:
    """§6.1 — one `day` row. Returns the row (also appended to day.csv)."""
    import paper_data as pd_
    ds = d.isoformat()
    skips = set(cfg.get("skip_dates") or []) | FOMC_2026
    if ds in skips:
        row = {"date": ds, "status": "SKIPPED_CALENDAR", "notes": "calendar skip"}
        st.append("day", row)
        return row

    notes = []
    vix = vix_chg = prior_close = atr20 = None
    try:
        vix, vix_chg = pd_.vix_snapshot()
    except pd_.PaperDataError as e:
        notes.append(f"vix: {e}")
    try:
        prior_close, atr20 = pd_.spx_daily_stats()
    except pd_.PaperDataError as e:
        notes.append(f"spx daily: {e}")
    sign = pd_.gex_sign()
    budget = float(cfg["account_equity"]) * float(cfg["daily_risk_pct"])
    row = {"date": ds, "status": "OK", "vix": _fmt(vix), "vix_chg_5d": _fmt(vix_chg),
           "prior_close": _fmt(prior_close), "atr20": _fmt(atr20),
           "gex_sign": sign, "risk_budget": _fmt(budget),
           "notes": "; ".join(notes)}
    st.append("day", row)
    return row


def _skip_row(cfg, day_row, strategy, slot, reason, note=""):
    # note goes to the run log only — signals.csv columns are fixed by the spec
    st.append("signals", _signal_row(cfg, day_row, slot=slot, strategy=strategy,
                                     action="SKIP", skip_reason=reason))
    print(f"[{slot}] {strategy} SKIP/{reason} {note}", flush=True)


def do_metf_slot(cfg: dict, day_row: dict, slot: str, chain: dict, expiry: str,
                 closes: list):
    """§6.2 — one deterministic signal row per slot; opens a position on trade."""
    m = cfg["metf"]
    state, ef, es = metf_state(closes, m["ema_fast"], m["ema_slow"])
    if state is None:
        _skip_row(cfg, day_row, "METF", slot, "DATA", "not enough bars for EMA")
        return
    side = metf_side(state)
    spot = spot_of(chain)
    cmap = contract_map(chain, expiry, side.lower())
    pick, skip = walk_strikes(cmap, side, spot, m["width"],
                              m["target_credit"], m["min_credit"])
    base = dict(slot=slot, strategy="METF", side=side, state=state,
                structure=f"{side}_VERTICAL", ema_fast=_fmt(ef),
                ema_slow=_fmt(es), spot=_fmt(spot), width=m["width"])
    if skip:
        st.append("signals", _signal_row(cfg, day_row, action="SKIP",
                                         skip_reason=skip, **base))
        print(f"[{slot}] METF SKIP/{skip} (state {state})", flush=True)
        return

    credit = pick["credit"]
    stop_level = credit * (1 + m["stop_multiple"])
    new_risk = stop_risk(credit, stop_level, m["contracts"])
    budget = float(day_row.get("risk_budget") or 0)
    if not risk_ok(open_stop_risk(), new_risk, budget):
        st.append("signals", _signal_row(cfg, day_row, action="SKIP",
                                         skip_reason="RISK", **base))
        print(f"[{slot}] METF SKIP/RISK", flush=True)
        return

    ts = iso(now_et())
    st.append("signals", _signal_row(
        cfg, day_row, ts=ts, action="SELL_VERTICAL",
        short_strike=pick["short_strike"], long_strike=pick["long_strike"],
        credit_theo=_fmt(credit), short_delta=_fmt(pick["short_delta"], 3),
        short_mid=_fmt(pick["short_mid"]), long_mid=_fmt(pick["long_mid"]),
        stop_level=_fmt(stop_level), **base))
    st.append("positions", {
        "position_id": f"{day_row['date']}-METF-{slot}-{side}",
        "signal_ts": ts, "strategy": "METF", "side": side,
        "contracts": m["contracts"],
        "short_strike": pick["short_strike"], "long_strike": pick["long_strike"],
        "credit_theo": _fmt(credit), "stop_level": _fmt(stop_level)})
    print(f"[{slot}] METF SELL {side} {pick['short_strike']}/{pick['long_strike']}"
          f" credit {credit:.2f} stop {stop_level:.2f}", flush=True)


def do_band_snapshot(cfg: dict, d: str, chain: dict, expiry: str):
    """§6.3 @ band_time — write the band row."""
    import paper_data as pd_
    b = cfg["band"]
    spot = spot_of(chain)
    k_atm = round(spot / STRIKE_STEP) * STRIKE_STEP
    calls = contract_map(chain, expiry, "call")
    puts = contract_map(chain, expiry, "put")
    mc, mp = calls.get(k_atm), puts.get(k_atm)
    if mc is None or mp is None or mid(mc) is None or mid(mp) is None:
        raise pd_.PaperDataError(f"no ATM straddle quotes at {k_atm}")
    straddle = mid(mc) + mid(mp)
    em, lower, upper, skew = band_metrics(spot, straddle, b["em_factor"])
    st.append("band", {"date": d, "spot_1030": _fmt(spot),
                       "straddle_mid": _fmt(straddle), "em": _fmt(em),
                       "lower": _fmt(lower, 0), "upper": _fmt(upper, 0),
                       "skew": _fmt(skew, 3)})
    print(f"[{cfg['band']['band_time']}] band {lower:.0f}-{upper:.0f} "
          f"em {em:.1f} skew {skew:.3f}", flush=True)


def _band_side_legs(structure, lower, upper, wing):
    """[(side, short, long)] for the chosen structure."""
    put_leg = ("PUT", lower, lower - wing)
    call_leg = ("CALL", upper, upper + wing)
    if structure == "IRON_CONDOR":
        return [put_leg, call_leg]
    return [call_leg] if structure == "CALL_VERTICAL" else [put_leg]


def do_band_entry(cfg: dict, day_row: dict, brow: dict, chain: dict, expiry: str):
    """§6.3 @ entry_time — containment sizing, structure, credits, positions."""
    b = cfg["band"]
    d = day_row["date"]
    slot = b["entry_time"]
    lower, upper, skew = float(brow["lower"]), float(brow["upper"]), float(brow["skew"])

    hist = [int(r["contained"]) for r in st.read("band")
            if r["date"] < d and (r.get("contained") or "").strip() in ("0", "1")]
    size, rc, warmup = containment_size(hist, b["containment_window"],
                                        b["size_full_above"], b["size_half_above"])
    # §6.3: before `containment_window` days of history, rc is treated as 1.0
    # but flagged — signals.csv has no warmup column, so the flag is the
    # literal string "warmup" in containment_rc.
    base = dict(slot=slot, strategy="BAND", band_lower=_fmt(lower, 0),
                band_upper=_fmt(upper, 0), skew=_fmt(skew, 3),
                containment_rc="warmup" if warmup else _fmt(rc, 2),
                width=b["wing_width"])
    if size is None:
        st.append("signals", _signal_row(cfg, day_row, action="SKIP",
                                         skip_reason="CONTAINMENT", **base))
        print(f"[{slot}] BAND SKIP/CONTAINMENT rc={rc:.2f}", flush=True)
        return

    structure = band_structure(skew, b["skew_lo"], b["skew_hi"])
    legs = _band_side_legs(structure, lower, upper, b["wing_width"])
    sides = []
    for side, ks, kl in legs:
        cmap = contract_map(chain, expiry, side.lower())
        cs, cl = cmap.get(ks), cmap.get(kl)
        if cs is None or cl is None or mid(cs) is None or mid(cl) is None:
            _skip_row(cfg, day_row, "BAND", slot, "DATA",
                      f"missing strikes {ks}/{kl} {side}")
            return
        credit = mid(cs) - mid(cl)
        if credit <= 0:
            _skip_row(cfg, day_row, "BAND", slot, "CREDIT",
                      f"no credit at {ks}/{kl} {side}")
            return
        sides.append({"side": side, "short": ks, "long": kl, "credit": credit,
                      "short_mid": mid(cs), "long_mid": mid(cl),
                      "short_delta": cs.get("delta")})

    total_credit = sum(s["credit"] for s in sides)
    # Stop per side = total credit both sides; single vertical: credit x2,
    # keeping the same breakeven logic (§6.3).
    stop_level = total_credit if structure == "IRON_CONDOR" else total_credit * 2
    new_risk = sum(stop_risk(s["credit"], stop_level, b["contracts"]) for s in sides)
    budget = float(day_row.get("risk_budget") or 0)
    if not risk_ok(open_stop_risk(), new_risk, budget):
        st.append("signals", _signal_row(cfg, day_row, action="SKIP",
                                         skip_reason="RISK", structure=structure, **base))
        print(f"[{slot}] BAND SKIP/RISK", flush=True)
        return

    ts = iso(now_et())
    p0 = sides[0]
    p1 = sides[1] if len(sides) > 1 else None
    st.append("signals", _signal_row(
        cfg, day_row, ts=ts,
        action="SELL_CONDOR" if structure == "IRON_CONDOR" else "SELL_VERTICAL",
        side="BOTH" if p1 else p0["side"], structure=structure,
        spot=_fmt(spot_of(chain)),
        short_strike=p0["short"], long_strike=p0["long"],
        short_strike_2=p1["short"] if p1 else "",
        long_strike_2=p1["long"] if p1 else "",
        credit_theo=_fmt(total_credit), short_delta=_fmt(p0["short_delta"], 3),
        short_mid=_fmt(p0["short_mid"]), long_mid=_fmt(p0["long_mid"]),
        stop_level=_fmt(stop_level),
        size_factor=_fmt(size, 1), **base))
    for s in sides:
        st.append("positions", {
            "position_id": f"{d}-BAND-{s['side']}",
            "signal_ts": ts, "strategy": "BAND", "side": s["side"],
            "contracts": b["contracts"],
            "short_strike": s["short"], "long_strike": s["long"],
            "credit_theo": _fmt(s["credit"]), "stop_level": _fmt(stop_level)})
    print(f"[{slot}] BAND {structure} credit {total_credit:.2f} "
          f"stop/side {stop_level:.2f} size {size}", flush=True)


def _close_position(p: dict, exit_value: float, reason: str):
    pnl = vertical_pnl(float(p["credit_theo"]), exit_value,
                       int(float(p.get("contracts") or 1)))
    st.update_position(p["position_id"],
                       {"exit_ts": iso(now_et()), "exit_value_theo": _fmt(exit_value),
                        "exit_reason": reason, "pnl_theo": _fmt(pnl)},
                       allow=st.EXIT_COLS)
    print(f"  {p['position_id']} {reason} @ {exit_value:.2f} pnl {pnl:+.0f}", flush=True)


def do_tracking(cfg: dict, chain: dict, expiry: str):
    """§6.4 — reprice each open side from chain mids; stop / TP."""
    tp = cfg["band"]["take_profit_short"]
    for p in st.open_positions():
        side = p["side"]
        cmap = contract_map(chain, expiry, side.lower())
        cs, cl = cmap.get(float(p["short_strike"])), cmap.get(float(p["long_strike"]))
        if cs is None or cl is None:
            continue
        ms, ml = mid(cs), mid(cl)
        if ms is None or ml is None:
            continue
        value = ms - ml
        if stop_triggered(value, float(p["stop_level"])):
            _close_position(p, value, "STOPPED")
        elif p["strategy"] == "BAND" and ms <= tp:
            _close_position(p, value, "TP")
        # METF hold_to_expiry: no take-profit; stop only.


def do_settle(spx_close: float):
    """§6.4 @ 16:00 — settle remaining legs at intrinsic vs the close."""
    for p in st.open_positions():
        v = settle_value(p["side"], float(p["short_strike"]),
                         float(p["long_strike"]), spx_close)
        _close_position(p, v, "EXPIRED")


def do_containment(d: str, spx_close: float) -> bool:
    """§6.5 @ 16:05 — contained = lower <= close <= upper, feeds tomorrow."""
    brow = band_row_for(d)
    if not brow or (brow.get("contained") or "").strip() != "":
        return False
    contained = int(float(brow["lower"]) <= spx_close <= float(brow["upper"]))
    st.update_band(d, {"spx_close": _fmt(spx_close), "contained": contained})
    print(f"[16:05] contained={contained} close {spx_close:.2f} "
          f"band {brow['lower']}-{brow['upper']}", flush=True)
    return True


# ══════════════════════════════════════════════════════════════════════════════
# The full-day loop (idempotent: re-running mid-day resumes, never duplicates)
# ══════════════════════════════════════════════════════════════════════════════

def cmd_run(cfg: dict):
    import paper_data as pd_
    d = now_et().date()
    ds = d.isoformat()
    if d.weekday() >= 5:
        print(f"{ds} is a weekend — nothing to do.")
        return

    day_rows = st.rows_for_date("day", ds)
    if not day_rows:
        pm = at(PREMARKET_TIME, d)
        if now_et() < pm:      # §6.1 runs once at 09:00 — don't sample earlier
            wait = (pm - now_et()).total_seconds()
            print(f"waiting {wait:.0f}s for {PREMARKET_TIME} ET pre-market step",
                  flush=True)
            time.sleep(wait)
    day_row = day_rows[0] if day_rows else do_premarket(cfg, d)
    if day_row["status"] == "SKIPPED_CALENDAR":
        print(f"{ds}: SKIPPED_CALENDAR — no signals today.")
        return
    print(f"paper run {ds} | budget ${float(day_row.get('risk_budget') or 0):.0f} "
          f"| gex {day_row.get('gex_sign')}", flush=True)

    settle_done_flag = {"done": False}

    while True:
        now = now_et()
        if now.date() != d:
            break
        grace = timedelta(minutes=SLOT_GRACE_MIN)
        chain_cache = {}

        def get_chain():
            if "c" not in chain_cache:
                chain_cache["c"] = pd_.chain_0dte()
            return chain_cache["c"]

        # ── METF slots ──
        if cfg["metf"]["enabled"]:
            for slot in pending_metf_slots(cfg, ds):
                t = at(slot, d)
                if now < t:
                    continue
                if now - t > grace:
                    _skip_row(cfg, day_row, "METF", slot, "DATA",
                              "slot missed (engine offline)")
                    continue
                try:
                    chain, expiry = get_chain()
                    closes = pd_.minute_closes(count=60, until=t)
                    do_metf_slot(cfg, day_row, slot, chain, expiry, closes)
                except pd_.PaperDataError as e:
                    _skip_row(cfg, day_row, "METF", slot, "DATA", str(e))

        # ── band snapshot + entry ──
        if cfg["band"]["enabled"]:
            bt, et_ = at(cfg["band"]["band_time"], d), at(cfg["band"]["entry_time"], d)
            if band_row_for(ds) is None and bt <= now <= bt + grace:
                try:
                    chain, expiry = get_chain()
                    do_band_snapshot(cfg, ds, chain, expiry)
                except pd_.PaperDataError as e:
                    print(f"band snapshot failed: {e}", flush=True)
            if band_signal_pending(cfg, ds) and now >= et_:
                brow = band_row_for(ds)
                if brow is None and now - et_ > grace:
                    _skip_row(cfg, day_row, "BAND", cfg["band"]["entry_time"],
                              "DATA", "no 10:30 band (engine offline?)")
                elif brow is not None and now - et_ > grace:
                    _skip_row(cfg, day_row, "BAND", cfg["band"]["entry_time"],
                              "DATA", "entry window missed (engine offline)")
                elif brow is not None:
                    try:
                        chain, expiry = get_chain()
                        do_band_entry(cfg, day_row, brow, chain, expiry)
                    except pd_.PaperDataError as e:
                        _skip_row(cfg, day_row, "BAND", cfg["band"]["entry_time"],
                                  "DATA", str(e))

        # ── tracking / settle / containment ──
        settle_t, contain_t = at(SETTLE_TIME, d), at(CONTAIN_TIME, d)
        if st.open_positions():
            if now >= settle_t:
                try:
                    do_settle(pd_.spx_last())
                    settle_done_flag["done"] = True
                except pd_.PaperDataError as e:
                    print(f"settle failed (retrying next cycle): {e}", flush=True)
            elif now >= at(TRACK_START, d):
                try:
                    chain, expiry = get_chain()
                    do_tracking(cfg, chain, expiry)
                except pd_.PaperDataError as e:
                    print(f"tracking cycle skipped: {e}", flush=True)

        if now >= contain_t:
            brow = band_row_for(ds)
            needs_contain = brow is not None and (brow.get("contained") or "") == ""
            if needs_contain:
                try:
                    do_containment(ds, pd_.spx_last())
                    needs_contain = False
                except pd_.PaperDataError as e:
                    print(f"containment failed (retrying next cycle): {e}", flush=True)
            if not st.open_positions() and not needs_contain:
                break

        # ── sleep until the next scheduled thing (tracking tick at most) ──
        pending = [at(s, d) for s in pending_metf_slots(cfg, ds)
                   if cfg["metf"]["enabled"]]
        if cfg["band"]["enabled"]:
            if band_row_for(ds) is None:
                pending.append(at(cfg["band"]["band_time"], d))
            if band_signal_pending(cfg, ds):
                pending.append(at(cfg["band"]["entry_time"], d))
        if st.open_positions():
            pending.append(settle_t if now >= settle_t - timedelta(minutes=1)
                           else now + timedelta(seconds=TRACK_INTERVAL_S))
        pending.append(contain_t)
        nxt = min((t for t in pending if t > now), default=now + timedelta(seconds=TRACK_INTERVAL_S))
        time.sleep(max(2.0, min((nxt - now).total_seconds(), 600)))

    print("paper run: day complete.", flush=True)


# ── status / fill ────────────────────────────────────────────────────────────

def cmd_status(cfg: dict):
    ds = now_et().date().isoformat()
    day_rows = st.rows_for_date("day", ds)
    budget = float(day_rows[0]["risk_budget"]) if day_rows and day_rows[0].get("risk_budget") else \
        float(cfg["account_equity"]) * float(cfg["daily_risk_pct"])
    opens = st.open_positions()
    used = open_stop_risk(opens)
    print(f"date {ds} | risk used ${used:.0f} / budget ${budget:.0f} "
          f"| open positions: {len(opens)}")
    if not opens:
        return
    values = {}
    try:
        import paper_data as pd_
        chain, expiry = pd_.chain_0dte()
        for p in opens:
            cmap = contract_map(chain, expiry, p["side"].lower())
            cs, cl = cmap.get(float(p["short_strike"])), cmap.get(float(p["long_strike"]))
            if cs and cl and mid(cs) is not None and mid(cl) is not None:
                values[p["position_id"]] = mid(cs) - mid(cl)
    except Exception as e:
        print(f"  (live repricing unavailable: {e})")
    for p in opens:
        v = values.get(p["position_id"])
        live = f"now {v:.2f} | to stop {float(p['stop_level']) - v:+.2f}" if v is not None else "now n/a"
        print(f"  {p['position_id']:<28} {p['side']:<4} "
              f"{p['short_strike']}/{p['long_strike']} "
              f"credit {p['credit_theo']} stop {p['stop_level']} | {live}")


def cmd_fill(position_id: str, credit=None, exit_value=None, note=None):
    rows = [r for r in st.read("positions") if r["position_id"] == position_id]
    if not rows:
        print(f"no such position_id: {position_id}", file=sys.stderr)
        sys.exit(1)
    row = rows[0]
    updates = {}
    if credit is not None:
        updates["credit_actual"] = _fmt(credit)
    if exit_value is not None:
        updates["exit_value_actual"] = _fmt(exit_value)
    if note is not None:
        updates["fill_notes"] = note
    ca = updates.get("credit_actual", row.get("credit_actual") or "")
    ea = updates.get("exit_value_actual", row.get("exit_value_actual") or "")
    if ca and ea:
        updates["pnl_actual"] = _fmt(vertical_pnl(
            float(ca), float(ea), int(float(row.get("contracts") or 1))))
    st.update_position(position_id, updates, allow=st.ACTUAL_COLS)
    print(f"{position_id}: " + ", ".join(f"{k}={v}" for k, v in updates.items()))


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="paper_engine",
        description="METF + Band Condor paper-mode signal logger (no order routing)")
    ap.add_argument("--config", default=None, help="path to paper_config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="full-day loop (idempotent)")
    sub.add_parser("status", help="open positions, stop distance, risk vs budget")
    f = sub.add_parser("fill", help="record actual paperMoney fills")
    f.add_argument("position_id")
    f.add_argument("--credit", type=float, default=None)
    f.add_argument("--exit", dest="exit_value", type=float, default=None)
    f.add_argument("--note", default=None)
    r = sub.add_parser("report", help="stats from the CSVs alone")
    r.add_argument("--weeks", type=int, default=1)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd == "run":
        cmd_run(cfg)
    elif args.cmd == "status":
        cmd_status(cfg)
    elif args.cmd == "fill":
        cmd_fill(args.position_id, args.credit, args.exit_value, args.note)
    elif args.cmd == "report":
        import paper_report
        paper_report.run_report(weeks=args.weeks)


if __name__ == "__main__":
    main()
