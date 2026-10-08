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

Second factor (TOTP, RFC 6238 — stdlib only):
  - Enroll once on the hub:
        sudo python3 /opt/logicon/spx-paper-trader/gate.py --enroll
    Prints 8 single-use backup codes (save them!) and a 30-minute link to
    /gate/enroll that shows the QR code for Google Authenticator/1Password.
  - From then on the login page asks for the 6-digit code after the
    password. Enrolling bumps the cookie generation, signing out every
    existing session.
  - Lost the phone AND the backup codes:
        sudo python3 /opt/logicon/spx-paper-trader/gate.py --disable-totp

Credentials live in gate_credentials.json (PBKDF2-SHA256 password, TOTP
secret, hashed backup codes — written by the setup script / --enroll); the
cookie-signing secret in gate_secret (both chmod 600, never in git). Runs
on 127.0.0.1:5260 — nothing here is internet-facing except through nginx.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import time
from pathlib import Path

from flask import Flask, Response, make_response, redirect, request

BASE_DIR = Path(__file__).resolve().parent
CRED_FILE = Path(os.environ.get("GATE_CREDENTIALS", BASE_DIR / "gate_credentials.json"))
SECRET_FILE = Path(os.environ.get("GATE_SECRET_FILE", BASE_DIR / "gate_secret"))
HOST = os.environ.get("GATE_HOST", "127.0.0.1")
PORT = int(os.environ.get("GATE_PORT", "5260"))
COOKIE_NAME = "sahmi_gate"
COOKIE_DOMAIN = os.environ.get("GATE_COOKIE_DOMAIN", ".sahmi.ae")
SESSION_DAYS = 7        # was 30 — shortened once live order routing sat behind this gate
MAX_FAILS = 10          # per-IP lockout after this many bad attempts
LOCKOUT_S = 300
GLOBAL_MAX_FAILS = 50   # across ALL IPs per window — the per-IP key can be
                        # rotated (Cloudflare edges, forged headers on a
                        # direct-to-origin hit), this backstop cannot
TOTP_STEP = 30
TOTP_WINDOW = 1         # accept ±1 step of clock skew
ENROLL_TTL = 1800       # the --enroll QR link lives 30 minutes

app = Flask(__name__)
_fails = {}             # ip -> [count, first_ts]
_gfails = [0, 0.0]      # [count, window_start] across all IPs


# ── credential file (re-read on change; login + TOTP replay guard write it) ─
_cred_cache = {"mtime": None, "data": {}}


def _load_cred() -> dict:
    try:
        m = CRED_FILE.stat().st_mtime_ns
    except OSError:
        return {}
    if _cred_cache["mtime"] != m:
        try:
            _cred_cache["data"] = json.loads(CRED_FILE.read_text())
            _cred_cache["mtime"] = m
        except Exception:
            return {}
    return _cred_cache["data"]


def _save_cred(cred: dict) -> None:
    """Atomic rewrite preserving owner/mode — --enroll usually runs as root
    while the service runs (and keeps writing the TOTP replay counter) as
    the app user."""
    st = CRED_FILE.stat() if CRED_FILE.exists() else None
    tmp = CRED_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cred))
    os.chmod(tmp, 0o600)
    if st is not None:
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except (PermissionError, OSError):
            pass
    os.replace(tmp, CRED_FILE)


def _secret() -> bytes:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_bytes(secrets.token_bytes(32))
        SECRET_FILE.chmod(0o600)
    return SECRET_FILE.read_bytes()


# ── session cookie ──────────────────────────────────────────────────────────
def _gen(cred=None) -> int:
    """Cookie generation: bumped by --enroll / --disable-totp so every
    session issued before the change is signed out."""
    return int((cred if cred is not None else _load_cred()).get("gen") or 1)


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(user: str) -> str:
    payload = f"{user}|{int(time.time()) + SESSION_DAYS * 86400}|{_gen()}"
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + _sign(payload)


def _valid_token(tok: str) -> bool:
    try:
        b64, sig = tok.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
        if not hmac.compare_digest(sig, _sign(payload)):
            return False
        parts = payload.split("|")
        exp = int(parts[1])
        gen = int(parts[2]) if len(parts) > 2 else 1   # pre-TOTP cookies
        return exp > time.time() and gen == _gen()
    except Exception:
        return False


# ── password ────────────────────────────────────────────────────────────────
def _check_password(user: str, password: str) -> bool:
    cred = _load_cred()
    if not cred or user != cred.get("user"):
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(),
                               bytes.fromhex(cred["salt"]), 200_000).hex()
    return hmac.compare_digest(calc, cred.get("hash", ""))


# ── TOTP second factor (RFC 6238, SHA-1/6 digits/30 s — stdlib only) ────────
def _hotp(key: bytes, counter: int) -> str:
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((int.from_bytes(h[o:o + 4], "big") & 0x7FFFFFFF) % 1_000_000).zfill(6)


def _totp_key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def _check_totp(cred: dict, code: str) -> bool:
    """±TOTP_WINDOW steps; each counter accepted only once (replay guard
    persisted in the cred file, so a shoulder-surfed code can't be resent)."""
    totp = cred.get("totp") or {}
    try:
        key = _totp_key(totp["secret"])
    except Exception:
        return False
    now = int(time.time()) // TOTP_STEP
    last = int(totp.get("last") or 0)
    for ctr in range(now - TOTP_WINDOW, now + TOTP_WINDOW + 1):
        if ctr > last and hmac.compare_digest(_hotp(key, ctr), code):
            totp["last"] = ctr
            cred["totp"] = totp
            _save_cred(cred)
            return True
    return False


def _check_backup(cred: dict, code: str) -> bool:
    """Single-use recovery code (dashes/spaces/case ignored)."""
    norm = code.replace("-", "").replace(" ", "").upper()
    if len(norm) < 8:
        return False
    h = hashlib.sha256(norm.encode()).hexdigest()
    codes = cred.get("backup") or []
    if h not in codes:
        return False
    codes.remove(h)
    cred["backup"] = codes
    _save_cred(cred)
    return True


def _check_second_factor(cred: dict, raw: str) -> bool:
    raw = (raw or "").strip()
    cleaned = raw.replace(" ", "")
    if len(cleaned) == 6 and cleaned.isdigit():
        return _check_totp(cred, cleaned)
    return _check_backup(cred, raw)


# ── brute-force limits ──────────────────────────────────────────────────────
def _client_ip() -> str:
    # Behind Cloudflare, X-Real-IP is the *edge* IP (rotates freely between
    # requests), so the per-IP lockout keys on CF-Connecting-IP — the actual
    # visitor. A direct-to-origin caller can forge that header, which is why
    # the global backstop below exists.
    return (request.headers.get("CF-Connecting-IP")
            or request.headers.get("X-Real-IP")
            or request.remote_addr or "?")


def _locked(ip: str) -> bool:
    rec = _fails.get(ip)
    if not rec:
        return False
    if time.time() - rec[1] > LOCKOUT_S:
        _fails.pop(ip, None)
        return False
    return rec[0] >= MAX_FAILS


def _glocked() -> bool:
    if time.time() - _gfails[1] > LOCKOUT_S:
        _gfails[0], _gfails[1] = 0, time.time()
    return _gfails[0] >= GLOBAL_MAX_FAILS


def _fail(ip: str) -> None:
    _fails.setdefault(ip, [0, time.time()])[0] += 1
    if time.time() - _gfails[1] > LOCKOUT_S:
        _gfails[0], _gfails[1] = 0, time.time()
    _gfails[0] += 1


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
  {totp}
  <button type="submit">Enter desk &rarr;</button>
  <footer>Encrypted &amp; access-controlled &middot; one sign-in covers trader &amp; paper</footer>
</form></body></html>"""

TOTP_FIELD = """<label for="c">Authenticator code</label>
  <input id="c" name="code" inputmode="numeric" autocomplete="one-time-code"
         placeholder="6-digit code (or a backup code)" required>"""


def _page(error: str = ""):
    err = f'<div class="err">{error}</div>' if error else ""
    totp = TOTP_FIELD if _load_cred().get("totp") else ""
    html = PAGE.format(error=err, nxt=_safe_next(), totp=totp,
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
    if _locked(ip) or _glocked():
        return _page("Too many attempts — try again in a few minutes.")
    user = (request.form.get("username") or "").strip()
    pw = request.form.get("password") or ""
    if not _check_password(user, pw):
        _fail(ip)
        return _page("Wrong username or password.")
    cred = _load_cred()
    if cred.get("totp") and not _check_second_factor(cred, request.form.get("code", "")):
        _fail(ip)
        return _page("Wrong authenticator code.")
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


# ── enrollment page: QR for the authenticator app (one-time link) ──────────
# The QR is drawn client-side (qrcodejs from cdnjs) so the secret never
# touches a third-party server; it appears only in this expiring page.
ENROLL_PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Logicon — Authenticator setup</title><style>
  body { margin:0; min-height:100vh; display:flex; align-items:center;
        justify-content:center; background:#f6f4ef; color:#1e232b;
        font:15px/1.5 system-ui,"Segoe UI",sans-serif; }
  .card { background:#fff; border:1px solid #e5e1d8; border-radius:14px;
         padding:36px 40px; width:380px; box-shadow:0 8px 30px rgba(30,35,43,.08); }
  h1 { font-size:13px; letter-spacing:.28em; margin:0 0 4px; color:#a8700a;
      text-transform:uppercase; }
  h2 { font-size:22px; margin:0 0 14px; }
  ol { padding-left:20px; color:#374151; font-size:14px; }
  #qr { display:flex; justify-content:center; margin:18px 0; }
  code { display:block; background:#fbfaf7; border:1px solid #ddd8cc;
        border-radius:8px; padding:10px 12px; font-size:14px; letter-spacing:.08em;
        text-align:center; word-break:break-all; }
  p.note { font-size:12px; color:#6b7280; }
</style></head><body>
<div class="card">
  <h1>Logicon</h1>
  <h2>Authenticator setup</h2>
  <ol>
    <li>Open Google Authenticator / 1Password / Apple Passwords</li>
    <li>Add account &rarr; scan this QR code</li>
    <li>Next sign-in asks for the 6-digit code</li>
  </ol>
  <div id="qr"></div>
  <p class="note">Can't scan? Enter this setup key manually (time-based, 6 digits):</p>
  <code>__KEY__</code>
  <p class="note">Backup codes were printed in the terminal that ran
  <b>--enroll</b> — store them somewhere safe. This link expires 30 minutes
  after enrollment.</p>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script>new QRCode(document.getElementById("qr"),
  {text: "__URI__", width: 220, height: 220, correctLevel: QRCode.CorrectLevel.M});</script>
</body></html>"""


@app.get("/gate/enroll")
def enroll_page():
    cred = _load_cred()
    en = cred.get("enroll") or {}
    t = request.args.get("t", "")
    ok = (en and t and time.time() < en.get("exp", 0)
          and hmac.compare_digest(hashlib.sha256(t.encode()).hexdigest(),
                                  en.get("token", "")))
    if not ok or not (cred.get("totp") or {}).get("secret"):
        return Response("enrollment link expired — rerun gate.py --enroll on the hub", 403)
    secret = cred["totp"]["secret"]
    user = cred.get("user", "")
    uri = (f"otpauth://totp/Logicon%20Desk:{user}?secret={secret}"
           "&issuer=Logicon%20Desk&algorithm=SHA1&digits=6&period=30")
    pretty = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    html = ENROLL_PAGE.replace("__URI__", uri).replace("__KEY__", pretty)
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── CLI: --enroll / --disable-totp (run on the hub, sudo is fine) ──────────
BACKUP_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"   # no 0/O/1/I/L/U lookalikes


def _cli_enroll():
    cred = _load_cred()
    if not cred.get("user"):
        raise SystemExit(f"no credentials at {CRED_FILE} — run deploy/setup_sahmi_login.sh first")
    secret = base64.b32encode(secrets.token_bytes(20)).decode()   # 32 chars, no padding
    codes = ["".join(secrets.choice(BACKUP_ALPHABET) for _ in range(10)) for _ in range(8)]
    token = secrets.token_urlsafe(32)
    cred["totp"] = {"secret": secret, "last": 0}
    cred["backup"] = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    cred["gen"] = _gen(cred) + 1                      # sign out every existing session
    cred["enroll"] = {"token": hashlib.sha256(token.encode()).hexdigest(),
                      "exp": int(time.time()) + ENROLL_TTL}
    _save_cred(cred)
    host = "trader" + COOKIE_DOMAIN
    print("\nTOTP enrolled — the login page now requires an authenticator code.")
    print("Every existing session has been signed out.\n")
    print(f"1) Scan the QR within 30 minutes:\n   https://{host}/gate/enroll?t={token}\n")
    print("2) BACKUP CODES — each works once, store them safely:")
    for c in codes:
        print(f"      {c[:5]}-{c[5:]}")
    print("\n3) Same authenticator entry for shine.sahmi.ae (optional):")
    print(f"      sudo systemctl edit shine   ->  [Service] Environment=SHINE_TOTP_SECRET={secret}")
    print("      sudo systemctl restart shine\n")
    print("Lost phone + backup codes:  gate.py --disable-totp\n")


def _cli_disable():
    cred = _load_cred()
    if not cred.get("user"):
        raise SystemExit(f"no credentials at {CRED_FILE}")
    for k in ("totp", "backup", "enroll"):
        cred.pop(k, None)
    cred["gen"] = _gen(cred) + 1
    _save_cred(cred)
    print("TOTP disabled — password-only sign-in restored; all sessions signed out.")


if __name__ == "__main__":
    if "--enroll" in sys.argv:
        _cli_enroll()
    elif "--disable-totp" in sys.argv:
        _cli_disable()
    else:
        if not CRED_FILE.exists():
            raise SystemExit(f"no credentials at {CRED_FILE} — run deploy/setup_sahmi_login.sh")
        app.run(host=HOST, port=PORT, debug=False, threaded=True)
