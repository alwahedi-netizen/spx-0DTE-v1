"""
gate.py — in-page sign-in for *.sahmi.ae (nginx auth_request backend)
=====================================================================
Replaces the browser's basic-auth popup with a proper login page, shared
across trader.sahmi.ae and paper.sahmi.ae (one sign-in covers both — the
session cookie is scoped to .sahmi.ae).

How it plugs in (see deploy/setup_sahmi_login.sh):
  - nginx `auth_request /gate/check` guards every request to the apps.
  - No/expired cookie -> nginx redirects to /gate/login (this page).
  - Successful POST sets an HMAC-signed, HttpOnly cookie and redirects back.

Credentials live in gate_credentials.json (PBKDF2-SHA256, written by the
setup script); the cookie-signing secret in gate_secret (both chmod 600,
never in git). Runs on 127.0.0.1:5260 — nothing here is internet-facing
except through nginx.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from flask import Flask, make_response, redirect, request

BASE_DIR = Path(__file__).resolve().parent
CRED_FILE = Path(os.environ.get("GATE_CREDENTIALS", BASE_DIR / "gate_credentials.json"))
SECRET_FILE = Path(os.environ.get("GATE_SECRET_FILE", BASE_DIR / "gate_secret"))
HOST = os.environ.get("GATE_HOST", "127.0.0.1")
PORT = int(os.environ.get("GATE_PORT", "5260"))
COOKIE_NAME = "sahmi_gate"
COOKIE_DOMAIN = os.environ.get("GATE_COOKIE_DOMAIN", ".sahmi.ae")
SESSION_DAYS = 30
MAX_FAILS = 10          # per-IP lockout after this many bad passwords
LOCKOUT_S = 300

app = Flask(__name__)
_fails = {}             # ip -> [count, first_ts]


def _secret() -> bytes:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_bytes(secrets.token_bytes(32))
        SECRET_FILE.chmod(0o600)
    return SECRET_FILE.read_bytes()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(user: str) -> str:
    payload = f"{user}|{int(time.time()) + SESSION_DAYS * 86400}"
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + _sign(payload)


def _valid_token(tok: str) -> bool:
    try:
        b64, sig = tok.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
        if not hmac.compare_digest(sig, _sign(payload)):
            return False
        _user, exp = payload.rsplit("|", 1)
        return int(exp) > time.time()
    except Exception:
        return False


def _check_password(user: str, password: str) -> bool:
    try:
        cred = json.loads(CRED_FILE.read_text())
    except Exception:
        return False
    if user != cred.get("user"):
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(),
                               bytes.fromhex(cred["salt"]), 200_000).hex()
    return hmac.compare_digest(calc, cred.get("hash", ""))


def _client_ip() -> str:
    return request.headers.get("X-Real-IP") or request.remote_addr or "?"


def _locked(ip: str) -> bool:
    rec = _fails.get(ip)
    if not rec:
        return False
    if time.time() - rec[1] > LOCKOUT_S:
        _fails.pop(ip, None)
        return False
    return rec[0] >= MAX_FAILS


def _safe_next() -> str:
    """Only same-host paths — never an absolute URL (open-redirect guard)."""
    nxt = request.values.get("next", "/")
    if not nxt.startswith("/") or nxt.startswith("//") or nxt.startswith("/gate"):
        return "/"
    return nxt


PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Logicon — Sign in</title><style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center;
        justify-content:center; background:#f6f4ef; color:#1e232b;
        font:15px/1.5 system-ui,"Segoe UI",sans-serif; }}
  .card {{ background:#fff; border:1px solid #e5e1d8; border-radius:14px;
         padding:36px 40px; width:340px; box-shadow:0 8px 30px rgba(30,35,43,.08); }}
  h1 {{ font-size:13px; letter-spacing:.28em; margin:0 0 4px; color:#a8700a;
      text-transform:uppercase; }}
  h2 {{ font-size:22px; margin:0 0 4px; }}
  p.sub {{ color:#6b7280; font-size:13px; margin:0 0 22px; }}
  label {{ display:block; font-size:11px; letter-spacing:.1em; color:#6b7280;
         text-transform:uppercase; margin:14px 0 5px; }}
  input {{ width:100%; box-sizing:border-box; padding:10px 12px; font:inherit;
         border:1px solid #ddd8cc; border-radius:8px; background:#fbfaf7; }}
  input:focus {{ outline:2px solid #2b5d8a33; border-color:#2b5d8a; }}
  button {{ width:100%; margin-top:22px; padding:11px; font:inherit; font-weight:600;
          color:#fff; background:#1a7f4b; border:0; border-radius:8px; cursor:pointer; }}
  button:hover {{ background:#166a3f; }}
  .err {{ background:#fbeae8; color:#b3372f; border:1px solid #eec7c3;
        border-radius:8px; padding:8px 12px; font-size:13px; margin-bottom:6px; }}
  footer {{ margin-top:22px; font-size:11px; color:#9aa0a8; text-align:center; }}
</style></head><body>
<form class="card" method="post" action="/gate/login">
  <h1>Logicon</h1>
  <h2>Sign in</h2>
  <p class="sub">Trading desk — {host}</p>
  {error}
  <input type="hidden" name="next" value="{nxt}">
  <label for="u">Username</label>
  <input id="u" name="username" autocomplete="username" autofocus required>
  <label for="p">Password</label>
  <input id="p" name="password" type="password" autocomplete="current-password" required>
  <button type="submit">Enter desk &rarr;</button>
  <footer>Encrypted &amp; access-controlled &middot; one sign-in covers trader &amp; paper</footer>
</form></body></html>"""


def _page(error: str = ""):
    err = f'<div class="err">{error}</div>' if error else ""
    html = PAGE.format(error=err, nxt=_safe_next(),
                       host=request.headers.get("Host", "sahmi.ae"))
    resp = make_response(html, 401 if error else 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/gate/check")
def check():
    tok = request.cookies.get(COOKIE_NAME, "")
    return ("", 204) if _valid_token(tok) else ("", 401)


@app.get("/gate/login")
def login_form():
    if _valid_token(request.cookies.get(COOKIE_NAME, "")):
        return redirect(_safe_next())
    return _page()


@app.post("/gate/login")
def login_post():
    ip = _client_ip()
    if _locked(ip):
        return _page("Too many attempts — try again in a few minutes.")
    user = (request.form.get("username") or "").strip()
    pw = request.form.get("password") or ""
    if not _check_password(user, pw):
        rec = _fails.setdefault(ip, [0, time.time()])
        rec[0] += 1
        return _page("Wrong username or password.")
    _fails.pop(ip, None)
    resp = redirect(_safe_next())
    resp.set_cookie(COOKIE_NAME, _make_token(user), max_age=SESSION_DAYS * 86400,
                    domain=COOKIE_DOMAIN, secure=True, httponly=True, samesite="Lax")
    return resp


@app.get("/gate/logout")
def logout():
    resp = redirect("/gate/login")
    resp.set_cookie(COOKIE_NAME, "", max_age=0, domain=COOKIE_DOMAIN,
                    secure=True, httponly=True, samesite="Lax")
    return resp


if __name__ == "__main__":
    if not CRED_FILE.exists():
        raise SystemExit(f"no credentials at {CRED_FILE} — run deploy/setup_sahmi_login.sh")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
