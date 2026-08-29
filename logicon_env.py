"""
logicon_env.py  —  Logicon Capital
==================================================================
Single source of truth for ALL credentials and secrets.

Nothing sensitive is hardcoded anywhere in the codebase anymore.
Secrets are loaded, in priority order, from:

    1. Real environment variables        (highest priority)
    2. A `.env` file next to this script (git-ignored)

Setup (once):
    cp .env.example .env
    # then edit .env and fill in your real keys

The `.env` file format is simple KEY=VALUE lines:

    SCHWAB_APP_KEY=xxxx
    SCHWAB_APP_SECRET=xxxx
    FMP_API_KEY=xxxx

No third-party dependency (no python-dotenv needed).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Shared-infra override: point several instances at one secrets file
# (e.g. LOGICON_ENV_FILE=/opt/logicon/infra/.env). Default: .env next to this file.
ENV_FILE = Path(os.environ.get("LOGICON_ENV_FILE", BASE_DIR / ".env"))

_cache: dict | None = None


def _parse_env_file(path: Path) -> dict:
    out = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if v.startswith("#"):     # `KEY=   # comment` — empty value, not the comment text
                v = ""
            if k:
                out[k] = v
    except Exception:
        pass
    return out


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = _parse_env_file(ENV_FILE) if ENV_FILE.exists() else {}
    return _cache


def get_secret(name: str, default: str | None = None, required: bool = False) -> str | None:
    """Environment variable wins; falls back to .env file; then default."""
    val = os.environ.get(name) or _load().get(name) or default
    if required and not val:
        raise RuntimeError(
            f"Missing required secret '{name}'.\n"
            f"  Fix: copy .env.example to .env next to logicon_env.py and set {name}=...\n"
            f"  (or export {name} as an environment variable)"
        )
    return val


def set_secrets(updates: dict) -> list:
    """Rotate keys in the .env file in place: managed lines are replaced,
    everything else (comments, unknown keys, ordering) is preserved.
    Returns the list of keys written. Values must be single-line."""
    changed = []
    clean = {}
    import re as _re
    for k, v in updates.items():
        k = str(k).strip()
        v = str(v).strip()
        if not k or not v or not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue
        if any(c in v for c in "\n\r"):
            continue
        clean[k] = v
    if not clean:
        return changed
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    seen = set()
    out = []
    for raw in lines:
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.partition("=")[0].strip()
            if key in clean:
                out.append(f"{key}={clean[key]}")
                seen.add(key); changed.append(key)
                continue
        out.append(raw)
    for k, v in clean.items():
        if k not in seen:
            out.append(f"{k}={v}")
            changed.append(k)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass
    reload()
    return changed


def reload():
    """Force re-read of .env (e.g. after the user edits it while running)."""
    global _cache
    _cache = None


# Convenience accessors used across the platform
def schwab_app_key(required=True):    return get_secret("SCHWAB_APP_KEY", required=required)
def schwab_app_secret(required=True): return get_secret("SCHWAB_APP_SECRET", required=required)
def fmp_api_key(required=False):      return get_secret("FMP_API_KEY", required=required)
def anthropic_api_key(required=False): return get_secret("ANTHROPIC_API_KEY", required=required)
def openai_api_key(required=False):    return get_secret("OPENAI_API_KEY", required=required)
