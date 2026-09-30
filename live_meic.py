"""
live_meic.py — multi-strategy live pilot: mirrors the paper engine's journal
=============================================================================
The paper engine stays the brain (signals, stops, take-profits, reloads,
settle). This module is only hands: when a side for an ARMED strategy
appears in positions.csv it submits the same SPXW vertical to Schwab; when
the paper engine closes that side it closes the live spread; EXPIRED sides
are left to cash settlement. Live fills are journaled next to theo so the
pilot measures real slippage trade by trade.

Strategies are armed INDIVIDUALLY, each to its own account:
    MEIC  — afternoon iron condors (credit verticals per side)
    FLY   — 13:00 ATM iron fly (credit verticals per side, group-managed
            on paper; the mirror just follows each side's exit)
    FLYR  — reload flies after a fly TP
    ORB   — opening-range breakout DEBIT vertical (signed convention:
            credit_theo < 0, orders go NET_DEBIT, closes receive credit)

SAFETY MODEL — all of these hold at once:
  * DISARMED BY DEFAULT, per strategy. Arming is a runtime act on the
    dashboard (data/paper/live/armed.json — never in git).
  * Fixed small size (contracts hard-capped at 2 in code); ORB debit
    capped at MAX_DEBIT per spread.
  * Entries mirror only FRESH signals (< FRESH_S old): after downtime
    nothing stale is chased.
  * PER-STRATEGY daily stop halts that strategy and flattens its book;
    a GLOBAL daily stop halts everything. Halts survive restarts.
  * Per-strategy side caps and entry cutoffs; tick-grid limit prices.
  * Schwab positions are audited per account each cycle: mismatch holds
    new entries for that account's strategies (DESYNC).
  * Kill switches (pause / disarm / close-now) on the Suggested Trades tab.
  * Every order attempt, fill, cancel and error lands in live CSV + log.

Nothing in this module decides trades. It has no market opinion.
"""

import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import paper_store as st

LIVE_DIR = st.DATA_DIR / "live"
LEDGER = LIVE_DIR / "live_trades.csv"
ARMED_FILE = LIVE_DIR / "armed.json"
STATE_FILE = LIVE_DIR / "state.json"
LOG_FILE = LIVE_DIR / "live.log"

TRADER_BASE = "https://api.schwabapi.com/trader/v1"

# Per-strategy live rails. cap = max mirrored sides/day; entry_last = no new
# entries after this ET time; daily_stop = realized $ that halts + flattens
# that strategy for the day.
STRATS = {
    "MEIC": {"entry_last": "15:00", "cap": 12, "daily_stop": -1000.0},
    "FLY":  {"entry_last": "13:15", "cap": 2,  "daily_stop": -400.0},
    "FLYR": {"entry_last": "14:50", "cap": 4,  "daily_stop": -400.0},
    "ORB":  {"entry_last": "13:15", "cap": 2,  "daily_stop": -600.0},
}
GLOBAL_DAILY_STOP = -2000.0   # realized $ across ALL live strategies

QTY = 1                  # pilot size; hard cap below
QTY_MAX = 2
MAX_DEBIT = 12.50        # never pay more than this per debit spread (ORB)
FRESH_S = 600            # only mirror signals younger than this
ENTRY_SLIP = 0.05        # first limit: theo credit - this (debit: pay more)
REPRICE_SLIP = 0.15      # second try
CLOSE_SLIPS = (0.10, 0.30, 0.75)   # closing limit ladder over theo exit
FEE_PER_LEG = 1.18       # all-in commission + index/regulatory fees, measured
                         # from the 2026-09-24 fills (Schwab cash -388.68 vs
                         # gross -365.00 over 20 legs). Expired legs cost 0.
ORDER_WAIT_S = 240       # per rung on the ladder

LEDGER_COLS = ["position_id", "side", "short_strike", "long_strike", "expiry",
               "qty", "status", "order_id", "credit_limit", "credit_fill",
               "exit_reason", "close_order_id", "close_limit", "close_fill",
               "pnl_live", "opened_ts", "closed_ts", "note"]
# status: OPENING -> OPEN -> CLOSING -> CLOSED | EXPIRED ; or SKIPPED/FAILED


def _now():
    import paper_engine as pe
    return pe.now_et()


def log(msg):
    line = f"[{_now().isoformat(timespec='seconds')}] {msg}"
    print(f"LIVE {msg}", flush=True)
    try:
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ── pure builders (unit-tested offline) ──────────────────────────────────────

def strat_of(position_id: str) -> str:
    """Strategy from a position id: 2026-09-29-FLYR1-PUT -> FLYR."""
    m = re.match(r"\d{4}-\d{2}-\d{2}-([A-Z]+)", position_id or "")
    return m.group(1) if m else "?"


def spx_tick(price: float, up: bool) -> float:
    """Snap a positive limit to a valid SPX option increment — 0.05 below
    $3.00, 0.10 at/above (the grids meet at exactly 3.00). Schwab REJECTS
    any off-tick price. up=True rounds toward paying more."""
    import math
    tick = 0.05 if price < 3.0 else 0.10
    n = price / tick
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)
    return max(0.05, round(n * tick, 2))


def entry_limit(credit_theo: float) -> float:
    """Signed, tick-legal entry limit with the standard concession.
    Credit spreads (+): receive slip less, rounded down to the grid.
    Debit spreads (−, ORB): pay slip more, magnitude rounded up."""
    v = credit_theo - ENTRY_SLIP
    if credit_theo > 0:
        return spx_tick(max(v, 0.05), up=False)
    return -spx_tick(-v, up=True)


def reprice_entry(credit_theo: float) -> float:
    v = credit_theo - REPRICE_SLIP
    if credit_theo > 0:
        return spx_tick(max(v, 0.05), up=False)
    return -spx_tick(-v, up=True)


def close_limit(exit_theo: float, rung: int, credit_position: bool) -> float:
    """Signed, tick-legal closing limit. Closing a credit spread PAYS
    (positive, concede by paying more); closing a debit spread RECEIVES
    (negative, concede by receiving less, floored at a nickel)."""
    v = exit_theo + CLOSE_SLIPS[min(rung, 2)]
    if credit_position:
        return spx_tick(max(v, 0.05), up=True)
    v = min(v, -0.05)
    return -spx_tick(-v, up=False)


def osi_symbol(root: str, expiry: str, putcall: str, strike: float) -> str:
    """21-char OSI symbol: ROOT(6) + YYMMDD + C/P + strike*1000 (8 digits)."""
    y, m, d = expiry.split("-")
    pc = "P" if putcall.upper().startswith("P") else "C"
    return f"{root.upper():<6}{y[2:]}{int(m):02d}{int(d):02d}{pc}{int(round(float(strike) * 1000)):08d}"


def vertical_order(side: str, short_k: float, long_k: float, expiry: str,
                   qty: int, action: str, limit: float) -> dict:
    """SPXW vertical order payload with SIGNED limit. OPEN always sells the
    short leg and buys the long leg; limit > 0 is a NET_CREDIT order,
    limit < 0 a NET_DEBIT (ORB entries). CLOSE reverses the legs; paying to
    exit (limit > 0) is NET_DEBIT, receiving (limit < 0) NET_CREDIT."""
    pc = "P" if side.upper() == "PUT" else "C"
    if action == "OPEN":
        legs = [("SELL_TO_OPEN", short_k), ("BUY_TO_OPEN", long_k)]
        otype = "NET_CREDIT" if limit > 0 else "NET_DEBIT"
    else:
        legs = [("BUY_TO_CLOSE", short_k), ("SELL_TO_CLOSE", long_k)]
        otype = "NET_DEBIT" if limit > 0 else "NET_CREDIT"
    return {
        "orderType": otype, "session": "NORMAL", "duration": "DAY",
        "orderStrategyType": "SINGLE", "complexOrderStrategyType": "VERTICAL",
        "price": f"{abs(round(limit, 2)):.2f}",
        "orderLegCollection": [
            {"instruction": ins, "quantity": qty,
             "instrument": {"symbol": osi_symbol("SPXW", expiry, pc, k),
                            "assetType": "OPTION"}} for ins, k in legs],
    }


def fill_price(order_json: dict) -> float:
    """Net credit(+)/debit(-) per spread from a filled order's executions:
    sum of sell-leg prices minus buy-leg prices, quantity-weighted."""
    sign = {}
    for leg in order_json.get("orderLegCollection") or []:
        s = 1.0 if "SELL" in (leg.get("instruction") or "") else -1.0
        sign[leg.get("legId")] = s
    tot = qty = 0.0
    for act in order_json.get("orderActivityCollection") or []:
        for el in act.get("executionLegs") or []:
            s = sign.get(el.get("legId"), 0.0)
            q = float(el.get("quantity") or 0)
            tot += s * float(el.get("price") or 0) * q
            if abs(s) > 0 and s > 0:
                qty += q
    return round(tot / qty, 4) if qty else 0.0


def schwab_audit(ledger_rows: list, positions: list, ds: str) -> dict:
    """Pure: compare our live book against Schwab's actual SPXW positions
    (ground truth). missing = we say OPEN, Schwab doesn't hold the SHORT
    leg (for debit spreads, the short leg is still the sold strike).
    unknown = Schwab shorts a same-day SPXW we don't know.
    day_pl = Schwab's own currentDayProfitLoss over SPXW positions."""
    held = {}
    for p in positions:
        sym = ((p.get("instrument") or {}).get("symbol") or "")
        if not sym.startswith("SPXW"):
            continue
        held[sym] = {"short": float(p.get("shortQuantity") or 0),
                     "day_pl": float(p.get("currentDayProfitLoss") or 0)}
    missing, matched = [], set()
    for r in ledger_rows:
        if r["status"] not in ("OPEN", "CLOSING", "STUCK"):
            continue
        pc = "P" if r["side"] == "PUT" else "C"
        s_sym = osi_symbol("SPXW", r["expiry"], pc, float(r["short_strike"]))
        if held.get(s_sym, {}).get("short", 0) >= int(r["qty"]):
            matched.add(s_sym)
        else:
            missing.append(r["position_id"])
    today_tag = f"{ds[2:4]}{ds[5:7]}{ds[8:10]}"
    unknown = [s for s, h in held.items()
               if h["short"] > 0 and s not in matched and s[6:12] == today_tag]
    return {"missing": missing, "unknown": unknown,
            "day_pl": round(sum(h["day_pl"] for h in held.values()), 2),
            "ok": not missing and not unknown}


def net_pnl(credit_fill: float, exit_px: float, qty: int, traded_legs: int) -> float:
    """Spread P&L net of estimated per-leg costs, so pnl_live matches
    Schwab's cash. Works for debit spreads too (both values negative).
    traded_legs: 4 for entry+close, 2 when the exit was cash settlement."""
    return round((credit_fill - exit_px) * 100 * qty
                 - FEE_PER_LEG * traded_legs * qty, 2)


def plan_actions(paper_sides: list, ledger: dict, now_iso: str, *,
                 armed_strats: set, paused: set, halted: set) -> list:
    """Pure mirror logic: what to do this cycle.
    Returns [("open", row) | ("close", pid, reason, exit_theo) |
             ("expire", pid, exit_theo)].
    paper_sides: today's position rows for the armed strategies.
    paused/halted: per-strategy sets (entries blocked; exits still mirror)."""
    acts = []
    now = datetime.fromisoformat(now_iso)
    hm = now.strftime("%H:%M")
    n_today = {}
    for pid in ledger:
        s = strat_of(pid)
        n_today[s] = n_today.get(s, 0) + 1
    for p in paper_sides:
        pid = p["position_id"]
        strat = p.get("strategy") or strat_of(pid)
        cfg = STRATS.get(strat)
        if cfg is None or strat not in armed_strats:
            continue
        lrow = ledger.get(pid)
        exited = bool((p.get("exit_ts") or "").strip())
        if lrow is None:
            if exited or strat in paused or strat in halted:
                continue
            if hm > cfg["entry_last"] or n_today.get(strat, 0) >= cfg["cap"]:
                continue
            try:
                age = (now - datetime.fromisoformat(p["signal_ts"])).total_seconds()
            except ValueError:
                continue
            if 0 <= age <= FRESH_S:
                acts.append(("open", p))
                n_today[strat] = n_today.get(strat, 0) + 1
        elif lrow["status"] == "OPEN" and exited:
            reason = (p.get("exit_reason") or "").strip()
            exit_theo = float(p.get("exit_value_theo") or 0)
            if reason == "EXPIRED":
                acts.append(("expire", pid, exit_theo))
            elif reason in ("STOPPED", "TP"):
                acts.append(("close", pid, reason, exit_theo))
    return acts


# ── armed / state / ledger ───────────────────────────────────────────────────

def armed_map() -> dict:
    """{strategy: {account_tail, dry_run, armed_at}} for armed strategies.
    Migrates the legacy single-strategy file shape (that was MEIC)."""
    try:
        j = json.loads(ARMED_FILE.read_text())
    except (OSError, ValueError):
        return {}
    if "strategies" in j:
        return {s: v for s, v in (j.get("strategies") or {}).items()
                if s in STRATS and v.get("armed") and v.get("account_tail")}
    if j.get("armed") and j.get("account_tail"):
        return {"MEIC": {"armed": True, "account_tail": j["account_tail"],
                         "dry_run": bool(j.get("dry_run")),
                         "armed_at": j.get("armed_at", "")}}
    return {}


def _write_armed(strategies: dict):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ARMED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"strategies": strategies}))
    os.replace(tmp, ARMED_FILE)


def _state() -> dict:
    try:
        s = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}
    # migrate legacy global bools to per-strategy maps (they meant MEIC)
    if not isinstance(s.get("halted"), dict):
        s["halted"] = {"MEIC": True} if s.get("halted") else {}
    if not isinstance(s.get("paused"), dict):
        s["paused"] = {"MEIC": True} if s.get("paused") else {}
    return s


def _save_state(s: dict):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s))
    os.replace(tmp, STATE_FILE)


def read_ledger(day: str = None) -> dict:
    out = {}
    if LEDGER.exists():
        for r in csv.DictReader(open(LEDGER, encoding="utf-8")):
            if day is None or (r.get("position_id") or "").startswith(day):
                out[r["position_id"]] = r
    return out


def _write_ledger(rows: dict):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows.values():
            w.writerow(r)
    os.replace(tmp, LEDGER)


def realized_by_strat(ledger: dict) -> dict:
    out = {}
    for pid, r in ledger.items():
        try:
            out[strat_of(pid)] = round(out.get(strat_of(pid), 0.0)
                                       + float(r.get("pnl_live") or 0), 2)
        except ValueError:
            pass
    return out


def realized_today(ledger: dict) -> float:
    return round(sum(realized_by_strat(ledger).values()), 2)


# ── Schwab trader plumbing ───────────────────────────────────────────────────

class Broker:
    def __init__(self, account_tail: str, dry_run: bool = False):
        self.tail = str(account_tail)
        self.dry = dry_run
        self._hash = None

    def _headers(self):
        # No Content-Type here: Schwab's trader gateway 400s a GET that
        # carries it without a body. requests adds it itself on json= POSTs.
        import schwab_auth
        return {"Authorization": f"Bearer {schwab_auth.get_access_token()}",
                "Accept": "application/json"}

    def account_hash(self) -> str:
        if self._hash:
            return self._hash
        import requests
        r = requests.get(f"{TRADER_BASE}/accounts/accountNumbers",
                         headers=self._headers(), timeout=20)
        r.raise_for_status()
        for a in r.json():
            if str(a.get("accountNumber", "")).endswith(self.tail):
                self._hash = a["hashValue"]
                return self._hash
        raise RuntimeError(f"no linked account ends with {self.tail} — if it "
                           "was added recently, redo the Schwab re-auth and "
                           "tick that account on the approval screen")

    def place(self, order: dict) -> str:
        if self.dry:
            log(f"DRY-RUN …{self.tail} place {order['orderType']} {order['price']}")
            return f"dry-{int(time.time()*1000)}"
        import requests
        r = requests.post(f"{TRADER_BASE}/accounts/{self.account_hash()}/orders",
                          headers=self._headers(), json=order, timeout=20)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"place: HTTP {r.status_code} {r.text[:200]}")
        loc = r.headers.get("Location", "")
        return loc.rstrip("/").rsplit("/", 1)[-1] or "unknown"

    def status(self, order_id: str) -> dict:
        if self.dry:
            return {"status": "FILLED", "orderActivityCollection": []}
        import requests
        r = requests.get(f"{TRADER_BASE}/accounts/{self.account_hash()}/orders/{order_id}",
                         headers=self._headers(), timeout=20)
        r.raise_for_status()
        return r.json()

    def positions(self) -> list:
        if self.dry:
            return []
        import requests
        r = requests.get(f"{TRADER_BASE}/accounts/{self.account_hash()}",
                         headers=self._headers(), params={"fields": "positions"},
                         timeout=20)
        r.raise_for_status()
        return (r.json().get("securitiesAccount") or {}).get("positions") or []

    def orders_today(self) -> list:
        if self.dry:
            return []
        import requests
        from datetime import timezone
        day0 = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        fmt = "%Y-%m-%dT%H:%M:%S.000Z"
        r = requests.get(f"{TRADER_BASE}/accounts/{self.account_hash()}/orders",
                         headers=self._headers(),
                         params={"fromEnteredTime": day0.astimezone(timezone.utc).strftime(fmt),
                                 "toEnteredTime": _now().astimezone(timezone.utc).strftime(fmt)},
                         timeout=20)
        r.raise_for_status()
        return r.json()

    def cancel(self, order_id: str):
        if self.dry:
            return
        import requests
        r = requests.delete(f"{TRADER_BASE}/accounts/{self.account_hash()}/orders/{order_id}",
                            headers=self._headers(), timeout=20)
        if r.status_code not in (200, 201):
            log(f"cancel {order_id}: HTTP {r.status_code}")


# ── the mirror cycle ─────────────────────────────────────────────────────────

def _paper_today(ds: str, strats: set) -> list:
    return [p for p in st.read("positions")
            if p.get("strategy") in strats
            and (p.get("signal_ts") or "")[:10] == ds]


def _open_side(br, ledger, p, ds):
    pid = p["position_id"]
    credit = float(p["credit_theo"])
    limit = entry_limit(credit)
    if 0 < limit <= 0.05:
        ledger[pid] = dict.fromkeys(LEDGER_COLS, "")
        ledger[pid].update(position_id=pid, status="SKIPPED", note="credit too small")
        return
    if limit < -MAX_DEBIT:
        ledger[pid] = dict.fromkeys(LEDGER_COLS, "")
        ledger[pid].update(position_id=pid, status="SKIPPED",
                           note=f"debit {abs(limit):.2f} > cap {MAX_DEBIT}")
        return
    o = vertical_order(p["side"], float(p["short_strike"]), float(p["long_strike"]),
                       ds, min(QTY, QTY_MAX), "OPEN", limit)
    try:
        oid = br.place(o)
    except Exception as e:
        log(f"{pid} OPEN failed: {e}")
        ledger[pid] = dict.fromkeys(LEDGER_COLS, "")
        ledger[pid].update(position_id=pid, status="FAILED", note=str(e)[:120])
        return
    ledger[pid] = dict.fromkeys(LEDGER_COLS, "")
    ledger[pid].update(position_id=pid, side=p["side"], short_strike=p["short_strike"],
                       long_strike=p["long_strike"], expiry=ds, qty=min(QTY, QTY_MAX),
                       status="OPENING", order_id=oid, credit_limit=f"{limit:.2f}",
                       opened_ts=_now().isoformat(timespec="seconds"))
    log(f"{pid} OPEN submitted {limit:+.2f} (order {oid})")


def _poll_opening(br, r):
    """OPENING -> OPEN / reprice once / SKIPPED."""
    try:
        j = br.status(r["order_id"])
    except Exception as e:
        log(f"{r['position_id']} status: {e}")
        return
    s = j.get("status")
    if s == "FILLED":
        px = fill_price(j) or float(r["credit_limit"])
        r.update(status="OPEN", credit_fill=f"{px:.2f}")
        log(f"{r['position_id']} FILLED @ {px:+.2f} (limit {r['credit_limit']})")
        return
    if s in ("CANCELED", "REJECTED", "EXPIRED"):
        why = (j.get("statusDescription") or s)[:80]
        r.update(status="SKIPPED", note=f"open {s}: {why}")
        log(f"{r['position_id']} open {s} ({why})")
        return
    age = (_now() - datetime.fromisoformat(r["opened_ts"])).total_seconds()
    if age > ORDER_WAIT_S and not r.get("note"):
        # one reprice, deeper concession
        br.cancel(r["order_id"])
        credit0 = float(r["credit_limit"]) + ENTRY_SLIP
        limit = reprice_entry(credit0)
        try:
            o = vertical_order(r["side"], float(r["short_strike"]),
                               float(r["long_strike"]), r["expiry"],
                               int(r["qty"]), "OPEN", limit)
            r.update(order_id=br.place(o), credit_limit=f"{limit:.2f}",
                     note="repriced")
            log(f"{r['position_id']} repriced to {limit:+.2f}")
        except Exception as e:
            r.update(status="SKIPPED", note=f"reprice failed: {e}"[:120])
    elif age > 2 * ORDER_WAIT_S:
        br.cancel(r["order_id"])
        r.update(status="SKIPPED", note="unfilled after reprice")
        log(f"{r['position_id']} unfilled after reprice — skipped")


def _is_credit_row(r) -> bool:
    try:
        return float(r.get("credit_fill") or r.get("credit_limit") or 0) >= 0
    except ValueError:
        return True


def _close_side(br, r, reason, exit_theo, rung=0):
    credit_pos = _is_credit_row(r)
    if reason in ("HALT", "MANUAL"):
        # Emergency, guaranteed-marketable: credit spreads pay up to the full
        # width (they can't be worth more); debit spreads accept a nickel.
        limit = (abs(float(r["short_strike"]) - float(r["long_strike"]))
                 if credit_pos else -0.05)
    else:
        limit = close_limit(exit_theo, rung, credit_pos)
    o = vertical_order(r["side"], float(r["short_strike"]), float(r["long_strike"]),
                       r["expiry"], int(r["qty"]), "CLOSE", limit)
    try:
        oid = br.place(o)
    except Exception as e:
        log(f"{r['position_id']} CLOSE failed: {e}")
        r.update(note=f"close failed: {e}"[:120])
        return
    r.update(status="CLOSING", close_order_id=oid, close_limit=f"{limit:.2f}",
             exit_reason=reason, note=f"rung{rung}",
             closed_ts=_now().isoformat(timespec="seconds"))
    log(f"{r['position_id']} CLOSE ({reason}) submitted @ {limit:+.2f}")


def _poll_closing(br, r):
    try:
        j = br.status(r["close_order_id"])
    except Exception as e:
        log(f"{r['position_id']} close status: {e}")
        return
    s = j.get("status")
    if s == "FILLED":
        raw = abs(fill_price(j)) or abs(float(r["close_limit"]))
        px = raw if _is_credit_row(r) else -raw
        pnl = net_pnl(float(r["credit_fill"] or 0), px, int(r["qty"]), 4)
        r.update(status="CLOSED", close_fill=f"{px:.2f}", pnl_live=f"{pnl:.2f}",
                 closed_ts=_now().isoformat(timespec="seconds"))
        log(f"{r['position_id']} CLOSED @ {px:+.2f} pnl {pnl:+.0f}")
        return
    if s in ("CANCELED", "REJECTED", "EXPIRED"):
        # Escalate at most twice, then STUCK: never loop rejected orders.
        why = (j.get("statusDescription") or s)[:80]
        n = int((r.get("note") or "x0").rsplit("x", 1)[-1] or 0) + 1 \
            if "close rejected" in (r.get("note") or "") else 1
        if n >= 3:
            r.update(status="STUCK", note=f"close rejected x{n}: {why}")
            log(f"{r['position_id']} close rejected x{n} ({why}) — STUCK, "
                "will cash-settle")
        else:
            r.update(status="OPEN", note=f"close rejected x{n}: {why}")
            log(f"{r['position_id']} close {s} ({why}) — retry {n}/3")
        return
    age = (_now() - datetime.fromisoformat(r["closed_ts"])).total_seconds()
    rung = int((r.get("note") or "rung0")[-1] or 0) if (r.get("note") or "").startswith("rung") else 0
    if age > ORDER_WAIT_S and rung < 2:
        br.cancel(r["close_order_id"])
        exit_theo = (abs(float(r["close_limit"])) - CLOSE_SLIPS[rung]) \
            * (1 if _is_credit_row(r) else -1)
        _close_side(br, r, r["exit_reason"], exit_theo, rung + 1)


def _absorb_external_closes(br, ledger, missing_pids):
    """A side we say is OPEN doesn't exist at Schwab: find the real closing
    fill in today's orders (e.g. the owner closed it by hand) and book its
    true P&L; otherwise flag the row for a human."""
    try:
        orders = br.orders_today()
    except Exception as e:
        log(f"orders fetch: {e}")
        return
    for pid in missing_pids:
        r = ledger.get(pid)
        if not r:
            continue
        pc = "P" if r["side"] == "PUT" else "C"
        s_sym = osi_symbol("SPXW", r["expiry"], pc, float(r["short_strike"]))
        for o in orders:
            if o.get("status") != "FILLED":
                continue
            if any((l.get("instrument") or {}).get("symbol") == s_sym
                   and l.get("instruction") == "BUY_TO_CLOSE"
                   for l in (o.get("orderLegCollection") or [])):
                raw = abs(fill_price(o))
                px = raw if _is_credit_row(r) else -raw
                pnl = net_pnl(float(r["credit_fill"] or 0), px, int(r["qty"]), 4)
                r.update(status="CLOSED", close_fill=f"{px:.2f}",
                         pnl_live=f"{pnl:.2f}",
                         exit_reason=r.get("exit_reason") or "MANUAL",
                         closed_ts=_now().isoformat(timespec="seconds"),
                         note=((r.get("note") or "") + " | closed at Schwab").strip(" |"))
                log(f"{pid} absorbed external close @ {px:+.2f} pnl {pnl:+.0f}")
                break
        else:
            if "missing at Schwab" not in (r.get("note") or ""):
                r["note"] = ((r.get("note") or "") + " | missing at Schwab").strip(" |")
                log(f"{pid} OPEN in ledger but missing at Schwab — entries held")


def _reconcile_settlement(get_br, ledger, ds, hm):
    """Cash-settled sides can't stay working: any row still OPEN/CLOSING/
    STUCK after its expiry's 16:00 settlement is booked at intrinsic vs
    that day's SPX close (band row), today and for any past day whose loop
    window closed before the close price landed. get_br(pid) supplies the
    right broker for cancels (a dry one is fine — cancel is best-effort)."""
    import paper_engine as pe
    past = {pid: r for pid, r in read_ledger().items() if pid not in ledger}
    fixed_past = False
    for r in list(ledger.values()) + list(past.values()):
        day = r.get("expiry") or ""
        if (not day or day > ds or (day == ds and hm < "16:07")
                or r["status"] not in ("OPEN", "CLOSING", "STUCK")):
            continue
        brow = pe.band_row_for(day)
        if not brow or not (brow.get("spx_close") or "").strip():
            continue
        if r.get("close_order_id") and day == ds:
            get_br(r["position_id"]).cancel(r["close_order_id"])
        v = pe.settle_value(r["side"], float(r["short_strike"]),
                            float(r["long_strike"]), float(brow["spx_close"]))
        pnl = net_pnl(float(r["credit_fill"] or 0), v, int(r["qty"]), 2)
        r.update(status="EXPIRED", close_fill=f"{v:.2f}", pnl_live=f"{pnl:.2f}",
                 exit_reason=r.get("exit_reason") or "EXPIRED",
                 closed_ts=_now().isoformat(timespec="seconds"),
                 note=((r.get("note") or "") + " | cash settle").strip(" |"))
        fixed_past = fixed_past or r["position_id"] in past
        log(f"{r['position_id']} settled at intrinsic {v:+.2f} pnl {pnl:+.0f}")
    if fixed_past:
        _write_ledger({**read_ledger(), **past})


def sync_once() -> dict:
    """One mirror pass. Never raises. Returns a summary for the API."""
    amap = armed_map()
    state = _state()
    ds = _now().date().isoformat()
    if state.get("day") != ds:
        state = {"day": ds, "halted": {}, "paused": state.get("paused", {})}
    ledger = read_ledger(ds)
    dry_br = Broker("0", dry_run=True)
    if not amap:
        # Accounting never requires being armed: still book cash-settled
        # sides at intrinsic (dry broker — no orders can be sent).
        try:
            _reconcile_settlement(lambda pid: dry_br, ledger, ds,
                                  _now().strftime("%H:%M"))
            _write_ledger({**read_ledger(), **ledger})
            _save_state(state)
        except Exception as e:
            log(f"disarmed reconcile: {e}")
        return sync_summary()

    brokers = {}
    for strat, cfg in amap.items():
        key = (cfg["account_tail"], bool(cfg.get("dry_run")))
        if key not in brokers:
            brokers[key] = Broker(*key)

    def br_for(strat):
        cfg = amap[strat]
        return brokers[(cfg["account_tail"], bool(cfg.get("dry_run")))]

    def br_for_pid(pid):
        s = strat_of(pid)
        return br_for(s) if s in amap else None

    try:
        # 1. finish in-flight orders first
        for r in ledger.values():
            b = br_for_pid(r["position_id"])
            if b is None:
                continue
            if r["status"] == "OPENING":
                _poll_opening(b, r)
            elif r["status"] == "CLOSING":
                _poll_closing(b, r)

        # 2. daily loss caps — per strategy, plus the global stop over REAL
        # money only (a dry-run rehearsal loss must never halt live books)
        rs = realized_by_strat(ledger)
        halted = state.setdefault("halted", {})
        for strat in amap:
            if rs.get(strat, 0) <= STRATS[strat]["daily_stop"] and not halted.get(strat):
                halted[strat] = True
                log(f"{strat} DAILY STOP hit ({rs.get(strat, 0):+.0f}) — halting")
        real_total = sum(v for s, v in rs.items()
                         if s in amap and not bool(amap[s].get("dry_run")))
        if real_total <= GLOBAL_DAILY_STOP and not state.get("global_halt"):
            state["global_halt"] = True
            for strat in amap:
                halted[strat] = True
            log(f"GLOBAL DAILY STOP hit ({real_total:+.0f}) — halting all")
        for r in ledger.values():
            s = strat_of(r["position_id"])
            if halted.get(s) and s in amap and r["status"] == "OPEN":
                _close_side(br_for(s), r, "HALT", 0.0, rung=2)

        # 3. Schwab is ground truth, per account: audit, absorb, hold on
        # mismatch (only that account's LIVE strategies are held).
        # 2026-09-30 lesson: scope the audit to strategies on THIS broker
        # key (tail AND live-mode) — a dry-run strategy's shadow rows can
        # never exist at Schwab, and auditing them against the real account
        # raised a phantom DESYNC that held FLY out of its debut.
        desync = set()
        schwab = {}
        for (tail, dry), b in brokers.items():
            if dry:
                continue
            strats_here = {s for s, c in amap.items()
                           if c["account_tail"] == tail
                           and not bool(c.get("dry_run"))}
            rows = [r for r in ledger.values()
                    if strat_of(r["position_id"]) in strats_here]
            try:
                audit = schwab_audit(rows, b.positions(), ds)
                schwab[tail] = {"ts": _now().isoformat(timespec="seconds"), **audit}
                if audit["missing"]:
                    _absorb_external_closes(b, ledger, audit["missing"])
                if not audit["ok"]:
                    desync |= strats_here
            except Exception as e:
                log(f"schwab audit …{tail}: {e}")
        state["schwab"] = schwab

        # 4. mirror the paper journal
        paused = {s for s in amap if state.get("paused", {}).get(s)} | desync
        halted_set = {s for s in amap if halted.get(s)}
        acts = plan_actions(_paper_today(ds, set(amap)), ledger,
                            _now().isoformat(),
                            armed_strats=set(amap),
                            paused=paused, halted=halted_set)
        for a in acts:
            if a[0] == "open":
                p = a[1]
                _open_side(br_for(p.get("strategy") or strat_of(p["position_id"])),
                           ledger, p, ds)
            elif a[0] == "close":
                _, pid, reason, exit_theo = a
                _close_side(br_for_pid(pid), ledger[pid], reason, exit_theo)
            elif a[0] == "expire":
                _, pid, exit_theo = a
                r = ledger[pid]
                pnl = net_pnl(float(r["credit_fill"] or 0), exit_theo, int(r["qty"]), 2)
                r.update(status="EXPIRED", close_fill=f"{exit_theo:.2f}",
                         pnl_live=f"{pnl:.2f}", exit_reason="EXPIRED",
                         closed_ts=_now().isoformat(timespec="seconds"))
                log(f"{pid} EXPIRED (cash settle {exit_theo:+.2f}) pnl {pnl:+.0f}")

        # 5. after cash settlement, book anything still working at intrinsic
        _reconcile_settlement(lambda pid: br_for_pid(pid) or dry_br,
                              ledger, ds, _now().strftime("%H:%M"))
    except Exception as e:
        log(f"sync error: {e}")
    _write_ledger({**read_ledger(), **ledger})
    _save_state(state)
    return sync_summary()


def live_report() -> dict:
    """Trade-by-trade live results, Schwab-synced, rolled up by model.
    Only rows that actually filled count as trades."""
    rows, skipped = [], 0
    by_model, by_day = {}, {}
    for pid, r in sorted(read_ledger().items()):
        strat = strat_of(pid)
        day = pid[:10]
        if not (r.get("credit_fill") or "").strip():
            skipped += 1
            continue
        pnl = None
        try:
            pnl = float(r.get("pnl_live"))
        except (TypeError, ValueError):
            pass
        rows.append({"day": day, "model": strat, "position_id": pid,
                     "side": r.get("side"), "strikes": f"{r.get('short_strike')}/{r.get('long_strike')}",
                     "entry": r.get("credit_fill"), "exit": r.get("close_fill"),
                     "reason": r.get("exit_reason") or r.get("status"),
                     "pnl": pnl, "open": r.get("status") in ("OPEN", "CLOSING", "STUCK")})
        if pnl is not None:
            m = by_model.setdefault(strat, {"model": strat, "trades": 0,
                                            "wins": 0, "pnl": 0.0})
            m["trades"] += 1
            m["wins"] += 1 if pnl > 0 else 0
            m["pnl"] = round(m["pnl"] + pnl, 2)
            d = by_day.setdefault(day, {"day": day, "pnl": 0.0, "trades": 0})
            d["pnl"] = round(d["pnl"] + pnl, 2)
            d["trades"] += 1
    return {"rows": rows[::-1], "by_model": sorted(by_model.values(),
                                                   key=lambda m: -m["pnl"]),
            "by_day": sorted(by_day.values(), key=lambda d: d["day"],
                             reverse=True),
            "skipped": skipped,
            "total": round(sum(m["pnl"] for m in by_model.values()), 2)}


def sync_summary() -> dict:
    """Read-only status for the UI (no orders, no network)."""
    amap = armed_map()
    state = _state()
    ds = _now().date().isoformat()
    ledger = read_ledger(ds)
    rs = realized_by_strat(ledger)
    same_day = state.get("day") == ds
    strategies = {}
    for strat in STRATS:
        cfg = amap.get(strat) or {}
        strategies[strat] = {
            "armed": strat in amap,
            "account_tail": cfg.get("account_tail", ""),
            "dry_run": bool(cfg.get("dry_run")),
            "paused": bool(state.get("paused", {}).get(strat)),
            "halted": bool(same_day and state.get("halted", {}).get(strat)),
            "realized": rs.get(strat, 0.0),
            "daily_stop": STRATS[strat]["daily_stop"],
        }
    return {"armed": bool(amap), "day": ds,
            "realized": round(sum(rs.values()), 2), "sides": len(ledger),
            "global_stop": GLOBAL_DAILY_STOP, "qty": QTY,
            "strategies": strategies,
            "schwab": state.get("schwab") if same_day else None}


# ── control surface (called by the dashboard API) ────────────────────────────

def _all_strategies_raw() -> dict:
    try:
        j = json.loads(ARMED_FILE.read_text())
        if "strategies" in j:
            return j["strategies"] or {}
        if j.get("armed"):
            return {"MEIC": {"armed": True, "account_tail": j.get("account_tail"),
                             "dry_run": bool(j.get("dry_run")),
                             "armed_at": j.get("armed_at", "")}}
    except (OSError, ValueError):
        pass
    return {}


def arm(strategy: str, account_tail: str, confirm: str, dry_run: bool = False) -> dict:
    strategy = (strategy or "").upper()
    if strategy not in STRATS:
        raise ValueError(f"unknown strategy {strategy!r} — one of {sorted(STRATS)}")
    if confirm != "ARM LIVE":
        raise ValueError('type exactly "ARM LIVE" to confirm')
    if not (account_tail or "").strip().isdigit():
        raise ValueError("account tail must be the digits at the end of the account")
    Broker(account_tail, dry_run=dry_run).account_hash()   # validates it exists
    s = _all_strategies_raw()
    s[strategy] = {"armed": True, "account_tail": account_tail.strip(),
                   "dry_run": bool(dry_run),
                   "armed_at": _now().isoformat(timespec="seconds")}
    _write_armed(s)
    log(f"{strategy} ARMED on …{account_tail}{' (dry-run)' if dry_run else ''}")
    return {"strategy": strategy, "armed": True,
            "account_tail": account_tail, "dry_run": dry_run}


def disarm(strategy: str = None) -> dict:
    if strategy:
        s = _all_strategies_raw()
        s.pop(strategy.upper(), None)
        _write_armed(s)
        log(f"{strategy.upper()} DISARMED")
        return {"strategy": strategy.upper(), "armed": False}
    try:
        ARMED_FILE.unlink()
    except OSError:
        pass
    log("ALL DISARMED")
    return {"armed": False}


def set_paused(strategy: str, on: bool) -> dict:
    s = _state()
    p = s.setdefault("paused", {})
    p[strategy.upper()] = bool(on)
    _save_state(s)
    log(f"{strategy.upper()} paused={on}")
    return {"strategy": strategy.upper(), "paused": bool(on)}


def close_now(position_id: str) -> dict:
    """Emergency: close one live side immediately (marketable limit)."""
    amap = armed_map()
    strat = strat_of(position_id)
    cfg = amap.get(strat)
    if not cfg:
        raise RuntimeError(f"{strat} is not armed")
    ledger = read_ledger()
    r = ledger.get(position_id)
    if not r or r["status"] not in ("OPEN", "OPENING"):
        raise RuntimeError(f"{position_id} is not open live")
    br = Broker(cfg["account_tail"], dry_run=bool(cfg.get("dry_run")))
    if r["status"] == "OPENING":
        br.cancel(r["order_id"])
        r.update(status="SKIPPED", note="cancelled by owner")
    else:
        _close_side(br, r, "MANUAL", 0.0, rung=2)
    _write_ledger(ledger)
    return {"ok": True, "status": r["status"]}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "sync":
        print(json.dumps(sync_once(), indent=1))
    elif cmd == "disarm":
        print(disarm(sys.argv[2] if len(sys.argv) > 2 else None))
    else:
        print(json.dumps(sync_summary(), indent=1))
