"""
schwab_auth.py — minimal Schwab OAuth token handling for the paper logger
=========================================================================
Standalone extraction of the token flow from Logicon's platform
(schwab_trader.py), with one deliberate change: library functions raise
AuthError instead of sys.exit(1), so the unattended day loop can turn a dead
token into SKIP/DATA rows instead of dying.

Setup:
  1. Copy .env.example to .env and set SCHWAB_APP_KEY / SCHWAB_APP_SECRET
     (developer.schwab.com app credentials).
  2. Run:  python3 schwab_auth.py auth
     Log in at the printed URL, paste the full redirect URL back.
     Tokens land in tokens.json (git-ignored).
  3. The refresh token dies 7 days after auth (Schwab hard limit) — re-run
     `auth` weekly. `python3 schwab_auth.py status` shows the countdown.

If you already run the Logicon platform, you can instead point at its token
file:  export LOGICON_TOKENS_FILE=/path/to/combo-trader-tv/tokens.json
(read/refresh only — this module never changes the platform's files' logic).
"""

import base64
import json
import sys
import base64
import hashlib
import hmac
import os
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from logicon_env import get_secret

AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
TOKEN_FILE = Path(os.environ.get("LOGICON_TOKENS_FILE",
                                 Path(__file__).parent / "tokens.json"))
REFRESH_TOKEN_LIFE_DAYS = 7   # Schwab hard limit — refresh token dies 7 days after auth

# ── B4 edge custody (hubless program, owner-approved 2026-11-02) ─────────────
# SCHWAB_TOKEN_SOURCE=edge: the grant lives in the estate edge worker's
# Durable Object (the ONE refresher). This module then fetches short-lived
# access tokens from the edge (service pass signed with the sahmi gate
# secret) and refuses local refresh/auth so a competing grant can never be
# created. Flag unset (default): behavior unchanged.
EDGE_TOKEN_URL = os.environ.get(
    "LOGICON_EDGE_TOKEN_URL", "https://trader.sahmi.ae/api/schwab/token")


def _edge_mode() -> bool:
    return os.environ.get("SCHWAB_TOKEN_SOURCE", "").lower() == "edge"


def _svc_secret() -> bytes:
    b64 = os.environ.get("LOGICON_SVC_SECRET_B64", "")
    if b64:
        return base64.b64decode(b64)
    path = os.environ.get("LOGICON_SVC_SECRET_FILE",
                          "/opt/logicon/spx-paper-trader/gate_secret")
    return Path(path).read_bytes()


def _svc_pass() -> str:
    ts = str(int(time.time()))
    sig = hmac.new(_svc_secret(), f"svc|{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


_edge_cache = {"token": None, "expires_at": 0.0, "fetched_at": 0.0}
_EDGE_RECHECK_S = int(os.environ.get("EDGE_TOKEN_RECHECK_S", "60"))
_edge_lock = threading.Lock()


def _edge_access_token() -> str:
    with _edge_lock:
        # Re-ask the edge at least every EDGE_TOKEN_RECHECK_S (default 60 s):
        # the edge answers from its own cache (no Schwab call), and a
        # re-auth at /reauth replaces the grant — Schwab then rejects the
        # old access token, so a long local cache would leave this process
        # "Disconnected" for up to 30 min after every re-login.
        now = time.time()
        if (_edge_cache["token"] and now < _edge_cache["expires_at"] - 60
                and now - _edge_cache.get("fetched_at", 0) < _EDGE_RECHECK_S):
            return _edge_cache["token"]
        resp = requests.post(EDGE_TOKEN_URL,
                             headers={"X-Logicon-Svc": _svc_pass()}, timeout=25)
        if resp.status_code != 200:
            raise AuthError(f"edge token endpoint HTTP {resp.status_code}"
                            " — check custody at https://trader.sahmi.ae/reauth2")
        data = resp.json()
        _edge_cache["token"] = data["access_token"]
        _edge_cache["fetched_at"] = time.time()
        _edge_cache["expires_at"] = datetime.fromisoformat(
            data["expires_at"].replace("Z", "+00:00")).timestamp()
        return _edge_cache["token"]


def shared_mode() -> bool:
    """True when LOGICON_TOKENS_FILE points at another app's token file
    (e.g. Combo Trader's). In shared mode this tool behaves exactly like one
    more platform process on the same file: it may refresh the access token
    (identical logic, refresh_auth_at preserved) but it must NEVER run a new
    OAuth login — a fresh Schwab authorization invalidates the refresh token
    every other app on this key is using."""
    return bool(os.environ.get("LOGICON_TOKENS_FILE"))


class AuthError(RuntimeError):
    pass


def _parse_env_file(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _app_creds():
    key = get_secret("SCHWAB_APP_KEY")
    secret = get_secret("SCHWAB_APP_SECRET")
    if (not key or not secret) and shared_mode():
        # Shared-token deployments (the hub) keep the platform's .env next to
        # the shared tokens.json (/opt/logicon/infra) — refreshing the access
        # token needs the app key, so fall back to that .env.
        vals = _parse_env_file(TOKEN_FILE.parent / ".env")
        key = key or vals.get("SCHWAB_APP_KEY")
        secret = secret or vals.get("SCHWAB_APP_SECRET")
    if not key or not secret:
        raise AuthError("SCHWAB_APP_KEY / SCHWAB_APP_SECRET not set — "
                        "copy .env.example to .env and fill them in")
    return key, secret


def _basic_auth_header() -> str:
    key, secret = _app_creds()
    return base64.b64encode(f"{key}:{secret}".encode()).decode()


def _callback_url() -> str:
    return get_secret("SCHWAB_CALLBACK_URL", default="https://127.0.0.1:8080")


def save_tokens(token_data: dict):
    """Timestamp is UTC and timezone-aware — machines in different timezones
    must agree on token age."""
    token_data["saved_at"] = datetime.now(timezone.utc).isoformat()
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))


def load_tokens() -> dict:
    if not TOKEN_FILE.exists():
        raise AuthError(f"no tokens at {TOKEN_FILE} — run `python3 schwab_auth.py auth`")
    return json.loads(TOKEN_FILE.read_text())


def is_token_expired(tokens: dict) -> bool:
    """Access token lifetime is 30 min. Naive legacy timestamps are treated
    as UTC; a timestamp from the future (clock skew) forces a refresh."""
    now = datetime.now(timezone.utc)
    try:
        saved_at = datetime.fromisoformat(tokens.get("saved_at", "2000-01-01"))
    except Exception:
        return True
    if saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    if saved_at > now + timedelta(minutes=2):
        return True
    expires_in = tokens.get("expires_in", 1800)
    return now > saved_at + timedelta(seconds=expires_in - 60)


def refresh_access_token(tokens: dict = None) -> dict:
    if _edge_mode():
        raise AuthError("edge custody active — this process must not refresh "
                        "(ONE-grant rule); tokens come from the edge worker")
    if tokens is None:
        tokens = load_tokens()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise AuthError("no refresh token — run `python3 schwab_auth.py auth`")
    resp = requests.post(TOKEN_URL,
                         headers={"Authorization": f"Basic {_basic_auth_header()}",
                                  "Content-Type": "application/x-www-form-urlencoded"},
                         data={"grant_type": "refresh_token",
                               "refresh_token": refresh_token},
                         timeout=30)
    if resp.status_code != 200:
        hint = " (refresh token expired — re-run auth)" if resp.status_code == 401 else ""
        raise AuthError(f"token refresh failed: HTTP {resp.status_code}{hint}")
    new_tokens = resp.json()
    if tokens.get("refresh_auth_at"):   # 30-min refresh does NOT reset the 7-day clock
        new_tokens["refresh_auth_at"] = tokens["refresh_auth_at"]
    save_tokens(new_tokens)
    return new_tokens


def get_access_token() -> str:
    """Valid access token, refreshing if needed. Raises AuthError, never exits."""
    if _edge_mode():
        return _edge_access_token()
    tokens = load_tokens()
    if is_token_expired(tokens):
        tokens = refresh_access_token(tokens)
    return tokens["access_token"]


# ── interactive auth flow ────────────────────────────────────────────────────

def build_auth_url() -> str:
    key, _ = _app_creds()
    return (f"{AUTH_URL}?client_id={key}"
            f"&redirect_uri={urllib.parse.quote(_callback_url(), safe='')}")


def exchange_redirect_url(redirect_url: str) -> dict:
    if _edge_mode():
        raise AuthError("edge custody active — re-authenticate at "
                        "https://trader.sahmi.ae/reauth2 (ONE-grant rule)")
    parsed = urllib.parse.urlparse(redirect_url.strip())
    params = urllib.parse.parse_qs(parsed.query)
    auth_code = params.get("code", [None])[0]
    if not auth_code:
        raise AuthError("no 'code' parameter in that URL — paste the FULL address bar URL")
    auth_code = urllib.parse.unquote(auth_code)
    resp = requests.post(TOKEN_URL,
                         headers={"Authorization": f"Basic {_basic_auth_header()}",
                                  "Content-Type": "application/x-www-form-urlencoded"},
                         data={"grant_type": "authorization_code", "code": auth_code,
                               "redirect_uri": _callback_url()},
                         timeout=30)
    if resp.status_code != 200:
        raise AuthError(f"token exchange failed ({resp.status_code}): {resp.text[:200]}")
    token_data = resp.json()
    token_data["refresh_auth_at"] = datetime.now(timezone.utc).isoformat()  # 7-day clock starts now
    save_tokens(token_data)
    return token_data


def token_status() -> str:
    if not TOKEN_FILE.exists():
        return "not authenticated — run `python3 schwab_auth.py auth`"
    try:
        tokens = json.loads(TOKEN_FILE.read_text())
    except Exception:
        return "tokens.json unreadable"
    anchor = tokens.get("refresh_auth_at")
    if not anchor:
        return "auth age unknown — re-authenticate once to start the 7-day countdown"
    auth_at = datetime.fromisoformat(anchor)
    if auth_at.tzinfo is None:
        auth_at = auth_at.replace(tzinfo=timezone.utc)
    left = (auth_at + timedelta(days=REFRESH_TOKEN_LIFE_DAYS)
            - datetime.now(timezone.utc)).total_seconds() / 86400
    if left <= 0:
        return "EXPIRED — re-authenticate now (`python3 schwab_auth.py auth`)"
    return f"{left:.1f} days left on the refresh token" + (" — renew soon!" if left <= 2 else "")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(token_status())
        return
    if cmd != "auth":
        print(f"usage: {sys.argv[0]} [auth|status]", file=sys.stderr)
        sys.exit(2)
    if shared_mode():
        print("REFUSED: LOGICON_TOKENS_FILE is set (shared-token mode).\n"
              "Running a new Schwab login here would invalidate the refresh "
              "token the other app (Combo Trader) is using.\n"
              "Re-authenticate from that app instead; this tool will pick up "
              "the shared tokens automatically.", file=sys.stderr)
        sys.exit(1)
    try:
        print("1. Open this URL, log in to Schwab, approve access:\n")
        print(f"   {build_auth_url()}\n")
        print("2. You'll land on a (probably broken) 127.0.0.1 page — that's fine.")
        redirect = input("   Paste the FULL redirect URL here: ").strip()
        token_data = exchange_redirect_url(redirect)
        print(f"\nAuthenticated. Access token expires in "
              f"{token_data.get('expires_in', '?')}s; 7-day countdown restarted.")
    except AuthError as e:
        print(f"auth failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
