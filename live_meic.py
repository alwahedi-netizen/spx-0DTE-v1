"""
live_meic.py — MEIC live pilot: mirrors the paper engine's MEIC journal
=======================================================================
The paper engine stays the brain (signals, stops, take-profits, settle).
This module is only hands: when a MEIC side appears in positions.csv it
submits the same SPXW vertical to Schwab; when the paper engine closes
that side (STOPPED / TP) it closes the live spread; EXPIRED sides are
left to cash settlement. Live fills are journaled next to theo so the
pilot measures real slippage trade by trade.

SAFETY MODEL — all of these hold at once:
  * DISARMED BY DEFAULT. Arming is a runtime act on the dashboard
    (data/paper/live/armed.json — never in git, never deployable).
  * MEIC only, fixed small size (contracts hard-capped at 2 in code).
  * Entries mirror only FRESH signals (< FRESH_S old): after downtime
    nothing stale is chased.
  * Daily loss cap: realized live P&L <= -DAILY_STOP halts new entries
    and flattens whatever is open. Halt survives restarts (state file).
  * Max ENTRY_CAP sides/day, entry window ends at ENTRY_LAST ET.
  * Kill switch (pause / disarm / close-now) on the Suggested Trades tab.
  * Every order attempt, fill, cancel and error lands in live CSV + log.

Nothing in this module decides trades. It has no market opinion.
"""

import csv
import json
import os
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

QTY = 1                  # pilot size; hard cap below
QTY_MAX = 2
DAILY_STOP = -1000.0     # realized $; at/beyond -> halt + flatten
ENTRY_CAP = 12           # max mirrored sides per day (6 condors)
FRESH_S = 600            # only mirror signals younger than this
ENTRY_LAST = "15:00"     # no new entries after (MEIC's last slot is 14:30)
ENTRY_SLIP = 0.05        # first limit: theo credit - this
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

def spx_tick(price: float, up: bool) -> float:
    """Snap a limit to a valid SPX option increment — 0.05 below $3.00,
    0.10 at/above (the grids meet at exactly 3.00). Schwab REJECTS any
    off-tick price (2026-09-23: every 1.72/1.97/4.48-style order bounced).
    up=True rounds toward paying more (marketable debits); up=False rounds
    credits down (stay fillable)."""
    import math
    tick = 0.05 if price < 3.0 else 0.10
    n = price / tick
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)
    return max(0.05, round(n * tick, 2))


def osi_symbol(root: str, expiry: str, putcall: str, strike: float) -> str:
    """21-char OSI symbol: ROOT(6) + YYMMDD + C/P + strike*1000 (8 digits)."""
    y, m, d = expiry.split("-")
    pc = "P" if putcall.upper().startswith("P") else "C"
    return f"{root.upper():<6}{y[2:]}{int(m):02d}{int(d):02d}{pc}{int(round(float(strike) * 1000)):08d}"


def vertical_order(side: str, short_k: float, long_k: float, expiry: str,
                   qty: int, action: str, limit: float) -> dict:
    """SPXW credit-vertical order payload. action: OPEN (NET_CREDIT) or
    CLOSE (NET_DEBIT). Schwab wants the spread price as a positive number."""
    pc = "P" if side.upper() == "PUT" else "C"
    if action == "OPEN":
        legs = [("SELL_TO_OPEN", short_k), ("BUY_TO_OPEN", long_k)]
        otype = "NET_CREDIT"
    else:
        legs = [("BUY_TO_CLOSE", short_k), ("SELL_TO_CLOSE", long_k)]
        otype = "NET_DEBIT"
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
            if s > 0:
                qty += q
    return round(tot / qty, 4) if qty else 0.0


def schwab_audit(ledger_rows: list, positions: list, ds: str) -> dict:
    """Pure: compare our live book against Schwab's actual SPXW positions
    (ground truth). missing = we say OPEN, Schwab doesn't hold the short
    leg (manual close?). unknown = Schwab shorts a same-day SPXW we don't
    know. day_pl = Schwab's own currentDayProfitLoss over SPXW positions."""
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
    Schwab's cash. traded_legs: 4 for entry+close, 2 when the exit was
    cash settlement (expiry costs nothing)."""
    return round((credit_fill - exit_px) * 100 * qty
                 - FEE_PER_LEG * traded_legs * qty, 2)


def plan_actions(paper_sides: list, ledger: dict, now_iso: str, *,
                 armed: bool, paused: bool, halted: bool) -> list:
    """Pure mirror logic: what to do this cycle.
    Returns [("open", row) | ("close", pid, reason, exit_theo) |
             ("expire", pid, exit_theo)].
    paper_sides: today's MEIC position rows. ledger: pid -> live row."""
    acts = []
    now = datetime.fromisoformat(now_iso)
    hm = now.strftime("%H:%M")
    n_today = len(ledger)
    for p in paper_sides:
        pid = p["position_id"]
        lrow = ledger.get(pid)
        exited = bool((p.get("exit_ts") or "").strip())
        if lrow is None:
            if exited or not armed or paused or halted:
                continue
            if hm > ENTRY_LAST or n_today >= ENTRY_CAP:
                continue
            try:
                age = (now - datetime.fromisoformat(p["signal_ts"])).total_seconds()
            except ValueError:
                continue
            if 0 <= age <= FRESH_S:
                acts.append(("open", p))
                n_today += 1
        elif lrow["status"] == "OPEN" and exited:
            reason = (p.get("exit_reason") or "").strip()
            exit_theo = float(p.get("exit_value_theo") or 0)
            if reason == "EXPIRED":
                acts.append(("expire", pid, exit_theo))
            elif reason in ("STOPPED", "TP"):
                acts.append(("close", pid, reason, exit_theo))
    return acts


# ── armed / state / ledger ───────────────────────────────────────────────────

def armed_info() -> dict:
    try:
        j = json.loads(ARMED_FILE.read_text())
        return j if j.get("armed") and j.get("account_tail") else {}
    except (OSError, ValueError):
        return {}


def _state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


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


def realized_today(ledger: dict) -> float:
    tot = 0.0
    for r in ledger.values():
        try:
            tot += float(r.get("pnl_live") or 0)
        except ValueError:
            pass
    return round(tot, 2)


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
        raise RuntimeError(f"no linked account ends with {self.tail}")

    def place(self, order: dict) -> str:
        if self.dry:
            log(f"DRY-RUN place {order['orderType']} {order['price']}")
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

def _paper_meic_today(ds: str) -> list:
    return [p for p in st.read("positions")
            if p.get("strategy") == "MEIC" and (p.get("signal_ts") or "")[:10] == ds]


def _open_side(br, ledger, p, ds):
    pid = p["position_id"]
    credit = float(p["credit_theo"])
    limit = spx_tick(credit - ENTRY_SLIP, up=False)
    if limit <= 0.05:
        ledger[pid] = dict.fromkeys(LEDGER_COLS, "")
        ledger[pid].update(position_id=pid, status="SKIPPED", note="credit too small")
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
    log(f"{pid} OPEN submitted {limit:.2f} cr (order {oid})")


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
        log(f"{r['position_id']} FILLED @ {px:.2f} (theo limit {r['credit_limit']})")
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
        limit = spx_tick(credit0 - REPRICE_SLIP, up=False)
        try:
            o = vertical_order(r["side"], float(r["short_strike"]),
                               float(r["long_strike"]), r["expiry"],
                               int(r["qty"]), "OPEN", limit)
            r.update(order_id=br.place(o), credit_limit=f"{limit:.2f}",
                     note="repriced")
            log(f"{r['position_id']} repriced to {limit:.2f}")
        except Exception as e:
            r.update(status="SKIPPED", note=f"reprice failed: {e}"[:120])
    elif age > 2 * ORDER_WAIT_S:
        br.cancel(r["order_id"])
        r.update(status="SKIPPED", note="unfilled after reprice")
        log(f"{r['position_id']} unfilled after reprice — skipped")


def _close_side(br, r, reason, exit_theo, rung=0):
    if reason in ("HALT", "MANUAL"):
        # Emergency: limit at the spread's full width — it can never be worth
        # more, so this is a market-speed close with a sane ceiling.
        limit = abs(float(r["short_strike"]) - float(r["long_strike"]))
    else:
        limit = spx_tick(exit_theo + CLOSE_SLIPS[min(rung, 2)], up=True)
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
    log(f"{r['position_id']} CLOSE ({reason}) submitted @ {limit:.2f}")


def _poll_closing(br, r):
    try:
        j = br.status(r["close_order_id"])
    except Exception as e:
        log(f"{r['position_id']} close status: {e}")
        return
    s = j.get("status")
    if s == "FILLED":
        px = abs(fill_price(j)) or float(r["close_limit"])
        pnl = net_pnl(float(r["credit_fill"] or 0), px, int(r["qty"]), 4)
        r.update(status="CLOSED", close_fill=f"{px:.2f}", pnl_live=f"{pnl:.2f}",
                 closed_ts=_now().isoformat(timespec="seconds"))
        log(f"{r['position_id']} CLOSED @ {px:.2f} pnl {pnl:+.0f}")
        return
    if s in ("CANCELED", "REJECTED", "EXPIRED"):
        # Escalate at most twice, then STUCK: never loop rejected orders
        # (2026-09-23: an off-tick close resubmitted every cycle for 2h).
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
        exit_theo = float(r["close_limit"]) - CLOSE_SLIPS[rung]
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
                px = abs(fill_price(o))
                pnl = net_pnl(float(r["credit_fill"] or 0), px, int(r["qty"]), 4)
                r.update(status="CLOSED", close_fill=f"{px:.2f}",
                         pnl_live=f"{pnl:.2f}",
                         exit_reason=r.get("exit_reason") or "MANUAL",
                         closed_ts=_now().isoformat(timespec="seconds"),
                         note=((r.get("note") or "") + " | closed at Schwab").strip(" |"))
                log(f"{pid} absorbed external close @ {px:.2f} pnl {pnl:+.0f}")
                break
        else:
            if "missing at Schwab" not in (r.get("note") or ""):
                r["note"] = ((r.get("note") or "") + " | missing at Schwab").strip(" |")
                log(f"{pid} OPEN in ledger but missing at Schwab — entries held")


def _reconcile_settlement(br, ledger, ds, hm):
    """Cash-settled sides can't stay working: any row still OPEN/CLOSING/
    STUCK after its expiry's 16:00 settlement is booked at intrinsic vs
    that day's SPX close (band row), today and for any past day whose loop
    window closed before the close price landed."""
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
            br.cancel(r["close_order_id"])
        v = pe.settle_value(r["side"], float(r["short_strike"]),
                            float(r["long_strike"]), float(brow["spx_close"]))
        pnl = net_pnl(float(r["credit_fill"] or 0), v, int(r["qty"]), 2)
        r.update(status="EXPIRED", close_fill=f"{v:.2f}", pnl_live=f"{pnl:.2f}",
                 exit_reason=r.get("exit_reason") or "EXPIRED",
                 closed_ts=_now().isoformat(timespec="seconds"),
                 note=((r.get("note") or "") + " | cash settle").strip(" |"))
        fixed_past = fixed_past or r["position_id"] in past
        log(f"{r['position_id']} settled at intrinsic {v:.2f} pnl {pnl:+.0f}")
    if fixed_past:
        _write_ledger({**read_ledger(), **past})


def sync_once() -> dict:
    """One mirror pass. Never raises. Returns a summary for the API."""
    info = armed_info()
    state = _state()
    ds = _now().date().isoformat()
    if state.get("day") != ds:
        state = {"day": ds, "halted": False, "paused": state.get("paused", False)}
    ledger = read_ledger(ds)
    summary = {"armed": bool(info), "paused": bool(state.get("paused")),
               "halted": bool(state.get("halted")), "day": ds,
               "realized": realized_today(ledger), "sides": len(ledger)}
    if not info:
        # Accounting never requires being armed: still book cash-settled
        # sides at intrinsic (dry broker — no orders can be sent).
        try:
            _reconcile_settlement(Broker("0", dry_run=True), ledger, ds,
                                  _now().strftime("%H:%M"))
            _write_ledger({**read_ledger(), **ledger})
            _save_state(state)
            summary["realized"] = realized_today(ledger)
        except Exception as e:
            log(f"disarmed reconcile: {e}")
        return summary
    br = Broker(info["account_tail"], dry_run=bool(info.get("dry_run")))
    try:
        # 1. finish in-flight orders first
        for r in ledger.values():
            if r["status"] == "OPENING":
                _poll_opening(br, r)
            elif r["status"] == "CLOSING":
                _poll_closing(br, r)

        # 2. daily loss cap — once halted, keep flattening anything open
        realized = realized_today(ledger)
        if realized <= DAILY_STOP and not state.get("halted"):
            state["halted"] = True
            log(f"DAILY STOP hit ({realized:+.0f}) — halting")
        if state.get("halted"):
            for r in ledger.values():
                if r["status"] == "OPEN":
                    _close_side(br, r, "HALT", 0.0, rung=2)

        # 3. Schwab is ground truth: audit our open book against the real
        # positions; absorb external closes, hold new entries on any mismatch
        desync = False
        if not br.dry:
            try:
                audit = schwab_audit(list(ledger.values()), br.positions(), ds)
                state["schwab"] = {"ts": _now().isoformat(timespec="seconds"),
                                   **audit}
                if audit["missing"]:
                    _absorb_external_closes(br, ledger, audit["missing"])
                desync = not audit["ok"]
            except Exception as e:
                log(f"schwab audit: {e}")

        # 4. mirror the paper journal
        acts = plan_actions(_paper_meic_today(ds), ledger,
                            _now().isoformat(),
                            armed=True,
                            paused=bool(state.get("paused")) or desync,
                            halted=bool(state.get("halted")))
        for a in acts:
            if a[0] == "open":
                _open_side(br, ledger, a[1], ds)
            elif a[0] == "close":
                _, pid, reason, exit_theo = a
                _close_side(br, ledger[pid], reason, exit_theo)
            elif a[0] == "expire":
                _, pid, exit_theo = a
                r = ledger[pid]
                pnl = net_pnl(float(r["credit_fill"] or 0), exit_theo, int(r["qty"]), 2)
                r.update(status="EXPIRED", close_fill=f"{exit_theo:.2f}",
                         pnl_live=f"{pnl:.2f}", exit_reason="EXPIRED",
                         closed_ts=_now().isoformat(timespec="seconds"))
                log(f"{pid} EXPIRED (cash settle {exit_theo:.2f}) pnl {pnl:+.0f}")
        # 5. after cash settlement, book anything still working at intrinsic
        _reconcile_settlement(br, ledger, ds, _now().strftime("%H:%M"))
    except Exception as e:
        log(f"sync error: {e}")
    _write_ledger({**read_ledger(), **ledger})
    _save_state(state)
    summary.update(realized=realized_today(ledger), sides=len(ledger),
                   halted=bool(state.get("halted")))
    return summary


def live_report() -> dict:
    """Trade-by-trade live results, Schwab-synced, rolled up by model.
    Strategy comes from the position id (YYYY-MM-DD-STRAT-...). Only rows
    that actually filled count as trades; SKIPPED/FAILED are listed apart."""
    rows, skipped = [], 0
    by_model, by_day = {}, {}
    for pid, r in sorted(read_ledger().items()):
        strat = (pid.split("-")[3] if len(pid.split("-")) > 3 else "?")
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
    info = armed_info()
    state = _state()
    ds = _now().date().isoformat()
    ledger = read_ledger(ds)
    return {"armed": bool(info), "account_tail": info.get("account_tail", ""),
            "dry_run": bool(info.get("dry_run")),
            "paused": bool(state.get("paused")),
            "halted": bool(state.get("halted") and state.get("day") == ds),
            "day": ds, "realized": realized_today(ledger),
            "sides": len(ledger), "daily_stop": DAILY_STOP, "qty": QTY,
            "schwab": state.get("schwab") if state.get("day") == ds else None}


# ── control surface (called by the dashboard API) ────────────────────────────

def arm(account_tail: str, confirm: str, dry_run: bool = False) -> dict:
    if confirm != "ARM LIVE":
        raise ValueError('type exactly "ARM LIVE" to confirm')
    if not (account_tail or "").strip().isdigit():
        raise ValueError("account tail must be the digits at the end of the account")
    Broker(account_tail, dry_run=dry_run).account_hash()   # validates it exists
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    ARMED_FILE.write_text(json.dumps({
        "armed": True, "account_tail": account_tail.strip(),
        "dry_run": bool(dry_run),
        "armed_at": _now().isoformat(timespec="seconds")}))
    log(f"ARMED on …{account_tail}{' (dry-run)' if dry_run else ''}")
    return {"armed": True, "account_tail": account_tail, "dry_run": dry_run}


def disarm() -> dict:
    try:
        ARMED_FILE.unlink()
    except OSError:
        pass
    log("DISARMED")
    return {"armed": False}


def set_paused(on: bool) -> dict:
    s = _state()
    s["paused"] = bool(on)
    _save_state(s)
    log(f"paused={on}")
    return {"paused": bool(on)}


def close_now(position_id: str) -> dict:
    """Emergency: close one live side immediately (marketable limit)."""
    info = armed_info()
    if not info:
        raise RuntimeError("not armed")
    ledger = read_ledger()
    r = ledger.get(position_id)
    if not r or r["status"] not in ("OPEN", "OPENING"):
        raise RuntimeError(f"{position_id} is not open live")
    br = Broker(info["account_tail"], dry_run=bool(info.get("dry_run")))
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
        print(disarm())
    else:
        print(json.dumps({"armed": armed_info() or False,
                          "state": _state(),
                          "today": realized_today(read_ledger(_now().date().isoformat()))},
                         indent=1))
