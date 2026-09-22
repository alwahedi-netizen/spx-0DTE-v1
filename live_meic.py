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
    limit = round(credit - ENTRY_SLIP, 2)
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
        r.update(status="SKIPPED", note=f"open {s}")
        log(f"{r['position_id']} open {s}")
        return
    age = (_now() - datetime.fromisoformat(r["opened_ts"])).total_seconds()
    if age > ORDER_WAIT_S and not r.get("note"):
        # one reprice, deeper concession
        br.cancel(r["order_id"])
        credit0 = float(r["credit_limit"]) + ENTRY_SLIP
        limit = round(credit0 - REPRICE_SLIP, 2)
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
        limit = max(0.05, round(exit_theo + CLOSE_SLIPS[min(rung, 2)], 2))
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
        pnl = (float(r["credit_fill"] or 0) - px) * 100 * int(r["qty"])
        r.update(status="CLOSED", close_fill=f"{px:.2f}", pnl_live=f"{pnl:.2f}",
                 closed_ts=_now().isoformat(timespec="seconds"))
        log(f"{r['position_id']} CLOSED @ {px:.2f} pnl {pnl:+.0f}")
        return
    if s in ("CANCELED", "REJECTED", "EXPIRED"):
        r.update(status="OPEN", note=f"close {s} — retrying")
        return
    age = (_now() - datetime.fromisoformat(r["closed_ts"])).total_seconds()
    rung = int((r.get("note") or "rung0")[-1] or 0) if (r.get("note") or "").startswith("rung") else 0
    if age > ORDER_WAIT_S and rung < 2:
        br.cancel(r["close_order_id"])
        exit_theo = float(r["close_limit"]) - CLOSE_SLIPS[rung]
        _close_side(br, r, r["exit_reason"], exit_theo, rung + 1)


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

        # 3. mirror the paper journal
        acts = plan_actions(_paper_meic_today(ds), ledger,
                            _now().isoformat(),
                            armed=True, paused=bool(state.get("paused")),
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
                pnl = (float(r["credit_fill"] or 0) - exit_theo) * 100 * int(r["qty"])
                r.update(status="EXPIRED", close_fill=f"{exit_theo:.2f}",
                         pnl_live=f"{pnl:.2f}", exit_reason="EXPIRED",
                         closed_ts=_now().isoformat(timespec="seconds"))
                log(f"{pid} EXPIRED (cash settle {exit_theo:.2f}) pnl {pnl:+.0f}")
    except Exception as e:
        log(f"sync error: {e}")
    _write_ledger({**read_ledger(), **ledger})
    _save_state(state)
    summary.update(realized=realized_today(ledger), sides=len(ledger),
                   halted=bool(state.get("halted")))
    return summary


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
            "sides": len(ledger), "daily_stop": DAILY_STOP, "qty": QTY}


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
