"""
paper_dashboard.py — browser UI for the paper-mode signal logger
================================================================
Run this (or START_PAPER.bat / start_paper.sh) and open the printed URL —
everything else happens in the browser: live signals, positions, risk, the
fill form for paperMoney executions, the weekly report, and the engine log.

It also SUPERVISES the day loop: on trading days it launches
`paper_engine.py run` as a subprocess (08:55–16:06 ET), restarts it if it
dies, and logs its output to data/paper/logs/. Nothing here places orders.

Env overrides:
  PAPER_HOST  bind address (default 127.0.0.1; use 0.0.0.0 on a server)
  PAPER_PORT  port (default 5250)
"""

import io
import os
import subprocess
import sys
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import live_meic
import paper_engine as pe
import paper_report
import paper_store as st
import schwab_auth

BASE_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("PAPER_HOST", "127.0.0.1")
PORT = int(os.environ.get("PAPER_PORT", "5250"))
LOG_DIR = st.DATA_DIR / "logs"
RESTART_BACKOFF_S = 180   # engine exits clean when the day is done; don't spin

app = Flask(__name__, static_folder=str(BASE_DIR / "static"))
_proc = {"p": None, "log": None, "started": 0.0, "last_exit": None}


# ── MEIC live mirror loop ────────────────────────────────────────────────────

def _live_loop():
    """One live-mirror pass every 30 s inside the session window, plus a
    bookkeeping pass every 10 min outside it (and once at boot) so cash
    settlements get booked even while disarmed."""
    last_idle = 0.0
    while True:
        try:
            now = pe.now_et()
            in_win = (now.weekday() < 5
                      and "11:50" <= now.strftime("%H:%M") <= "16:20")
            if in_win or time.time() - last_idle > 600:
                live_meic.sync_once()
                if not in_win:
                    last_idle = time.time()
        except Exception as e:
            print(f"live loop: {e}", flush=True)
        time.sleep(30)


# ── engine supervisor ────────────────────────────────────────────────────────

def _engine_window(now) -> tuple:
    """(should_run, reason_if_not)."""
    if now.weekday() >= 5:
        return False, "weekend"
    hm = now.strftime("%H:%M")
    if not ("08:55" <= hm <= "16:06"):
        return False, "outside session window (08:55-16:06 ET)"
    rows = st.rows_for_date("day", now.date().isoformat())
    if rows and rows[0].get("status") == "SKIPPED_CALENDAR":
        return False, "calendar skip day"
    return True, ""


def _supervisor():
    while True:
        try:
            now = pe.now_et()
            p = _proc["p"]
            if p is not None and p.poll() is not None:
                _proc["last_exit"] = p.returncode
                _proc["p"] = None
                p = None
            should, _why = _engine_window(now)
            if should and p is None and time.time() - _proc["started"] > RESTART_BACKOFF_S:
                os.makedirs(LOG_DIR, exist_ok=True)
                lp = LOG_DIR / f"engine_{now.date().isoformat()}.log"
                f = open(lp, "a", encoding="utf-8")
                _proc["p"] = subprocess.Popen(
                    [sys.executable, str(BASE_DIR / "paper_engine.py"), "run"],
                    stdout=f, stderr=subprocess.STDOUT, cwd=str(BASE_DIR))
                _proc["log"] = str(lp)
                _proc["started"] = time.time()
                print(f"engine started (pid {_proc['p'].pid}) -> {lp}", flush=True)
        except Exception as e:
            print(f"supervisor: {e}", flush=True)
        time.sleep(20)


# ── pages / API ──────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "paper.html")


@app.get("/api/state")
def api_state():
    cfg = pe.load_config()
    now = pe.now_et()
    ds = now.date().isoformat()
    day_rows = st.rows_for_date("day", ds)
    day = day_rows[0] if day_rows else None
    positions = st.read("positions")
    opens = [p for p in positions if not (p.get("exit_ts") or "").strip()]
    budget = (float(day["risk_budget"]) if day and (day.get("risk_budget") or "").strip()
              else float(cfg["account_equity"]) * float(cfg["daily_risk_pct"]))
    p = _proc["p"]
    running = p is not None and p.poll() is None
    should, why = _engine_window(now)
    from datetime import timedelta
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    return jsonify({
        "now": pe.iso(now), "date": ds,
        "pnl": paper_report.pnl_summary(today=ds, week_start=week_start),
        "engine": {"running": running,
                   "state": "running" if running else (why or "idle (will start in window)"),
                   "last_exit": _proc["last_exit"]},
        "auth": {"shared": schwab_auth.shared_mode(),
                 "status": schwab_auth.token_status(),
                 "token_file": str(schwab_auth.TOKEN_FILE)},
        "day": day,
        "band": pe.band_row_for(ds),
        "signals": st.signals_for(ds),
        "positions": [p_ for p_ in positions
                      if (p_.get("signal_ts") or "")[:10] == ds or p_ in opens],
        "risk": {"used": round(pe.open_stop_risk(opens), 2), "budget": round(budget, 2)},
        "slots": cfg["metf"]["slots"],
    })


@app.get("/api/log")
def api_log():
    lp = LOG_DIR / f"engine_{pe.now_et().date().isoformat()}.log"
    if not lp.exists():
        return jsonify({"text": "(no engine log for today yet)"})
    lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
    return jsonify({"text": "\n".join(lines[-200:])})


@app.post("/api/fill")
def api_fill():
    j = request.get_json(force=True, silent=True) or {}

    def num(x):
        return None if x in (None, "") else float(x)
    try:
        updates = pe.apply_fill(j.get("position_id", ""), num(j.get("credit")),
                                num(j.get("exit_value")), (j.get("note") or None))
    except KeyError:
        return jsonify({"error": "no such position_id"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "updates": updates})


@app.get("/api/report")
def api_report():
    try:
        weeks = max(1, int(request.args.get("weeks", 1)))
    except ValueError:
        weeks = 1
    buf = io.StringIO()
    with redirect_stdout(buf):
        paper_report.run_report(weeks=weeks)
    return jsonify({"text": buf.getvalue()})


@app.get("/suggested")
def suggested_page():
    return send_from_directory(app.static_folder, "suggested.html")


@app.get("/api/suggested")
def api_suggested():
    """Today's suggested trades across every strategy, joined with the paper
    position outcome and (for MEIC) the live pilot ledger."""
    ds = pe.now_et().date().isoformat()
    positions = {p["position_id"]: p for p in st.read("positions")
                 if (p.get("signal_ts") or "")[:10] == ds}
    ledger = live_meic.read_ledger(ds)
    rows = []
    for s_ in st.signals_for(ds):
        if s_.get("action") == "SKIP":
            continue
        base_id = f"{ds}-{s_.get('strategy')}"
        linked = [p for p in positions.values()
                  if p.get("signal_ts") == s_.get("ts")]
        for p in linked or [None]:
            live = ledger.get((p or {}).get("position_id") or "")
            rows.append({
                "time": (s_.get("ts") or "")[11:16], "strategy": s_.get("strategy"),
                "structure": s_.get("structure") or s_.get("action"),
                "side": (p or {}).get("side") or s_.get("side"),
                "short_strike": (p or {}).get("short_strike") or s_.get("short_strike"),
                "long_strike": (p or {}).get("long_strike") or s_.get("long_strike"),
                "credit_theo": (p or {}).get("credit_theo") or s_.get("credit_theo"),
                "stop_level": (p or {}).get("stop_level") or s_.get("stop_level"),
                "position_id": (p or {}).get("position_id"),
                "exit_reason": (p or {}).get("exit_reason") or "",
                "pnl_theo": (p or {}).get("pnl_actual") or (p or {}).get("pnl_theo") or "",
                "live": ({"status": live.get("status"),
                          "credit_fill": live.get("credit_fill"),
                          "close_fill": live.get("close_fill"),
                          "pnl_live": live.get("pnl_live"),
                          "note": live.get("note")} if live else None),
            })
    return jsonify({"date": ds, "rows": rows, "live": live_meic.sync_summary()})


@app.post("/api/live/arm")
def api_live_arm():
    j = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(live_meic.arm(j.get("account_tail", ""),
                                     j.get("confirm", ""),
                                     bool(j.get("dry_run"))))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/live/disarm")
def api_live_disarm():
    return jsonify(live_meic.disarm())


@app.post("/api/live/pause")
def api_live_pause():
    j = request.get_json(force=True, silent=True) or {}
    return jsonify(live_meic.set_paused(bool(j.get("on"))))


@app.post("/api/live/close")
def api_live_close():
    j = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(live_meic.close_now(j.get("position_id", "")))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/auth/start")
def api_auth_start():
    """Standalone-token mode only: returns the Schwab login URL. In shared
    mode this is refused — a new login would invalidate the refresh token
    Combo Trader is using."""
    if schwab_auth.shared_mode():
        return jsonify({"error": "shared-token mode: re-authenticate from "
                                 "Combo Trader, not here"}), 400
    try:
        return jsonify({"url": schwab_auth.build_auth_url()})
    except schwab_auth.AuthError as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/auth/complete")
def api_auth_complete():
    if schwab_auth.shared_mode():
        return jsonify({"error": "shared-token mode: re-authenticate from "
                                 "Combo Trader, not here"}), 400
    j = request.get_json(force=True, silent=True) or {}
    try:
        schwab_auth.exchange_redirect_url(j.get("redirect_url", ""))
    except schwab_auth.AuthError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "status": schwab_auth.token_status()})


def main():
    threading.Thread(target=_supervisor, daemon=True).start()
    threading.Thread(target=_live_loop, daemon=True).start()
    print(f"SPX Paper Trader dashboard: http://{HOST}:{PORT}/", flush=True)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
