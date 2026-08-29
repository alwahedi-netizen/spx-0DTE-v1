"""
paper_data.py — Schwab market-data adapter for the paper-mode logger
====================================================================
All network I/O for paper_engine.py lives here, behind PaperDataError, so a
data problem becomes a SKIP/DATA row instead of a crash.

Self-contained: auth via schwab_auth.py (raises AuthError, never exits), and
its own 0DTE SPXW chain fetcher (same index-symbol variants and parameters as
the Logicon platform's gex_engine.fetch_chain).

There is no shared rate limiter; this module paces its own calls with a
minimum gap. The 1-min tracking cadence is one chain call per cycle, well
under Schwab's ~120 req/min market-data ceiling.
"""

import time
from datetime import date, datetime, timedelta

import requests

MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
MIN_CALL_GAP_S = 0.5


class PaperDataError(RuntimeError):
    pass


_last_call = 0.0


def _pace():
    global _last_call
    wait = MIN_CALL_GAP_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _token() -> str:
    try:
        import schwab_auth
        return schwab_auth.get_access_token()
    except Exception as e:
        raise PaperDataError(f"Schwab auth failed: {e}") from e


def _get(path: str, params: dict) -> dict:
    for attempt in (1, 2):
        _pace()
        try:
            r = requests.get(f"{MARKETDATA_BASE}{path}",
                             headers={"Authorization": f"Bearer {_token()}",
                                      "Accept": "application/json"},
                             params=params, timeout=30)
        except requests.RequestException as e:
            if attempt == 1:
                time.sleep(2)
                continue
            raise PaperDataError(f"GET {path}: {e}") from e
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503) and attempt == 1:
            time.sleep(2)
            continue
        raise PaperDataError(f"GET {path}: HTTP {r.status_code}")
    raise PaperDataError(f"GET {path}: retries exhausted")


# ── bars / quotes ────────────────────────────────────────────────────────────

def minute_closes(symbol: str = "$SPX", count: int = 60, until: datetime = None) -> list:
    """Last `count` 1-min closes up to `until` (aware dt). Today's session only."""
    j = _get("/pricehistory", {"symbol": symbol, "periodType": "day", "period": 1,
                               "frequencyType": "minute", "frequency": 1,
                               "needExtendedHoursData": "false"})
    candles = j.get("candles") or []
    if until is not None:
        cutoff = until.timestamp() * 1000
        candles = [c for c in candles if c.get("datetime", 0) <= cutoff]
    closes = [float(c["close"]) for c in candles if c.get("close") is not None]
    if len(closes) < 5:
        raise PaperDataError(f"only {len(closes)} minute bars for {symbol}")
    return closes[-count:]


def daily_candles(symbol: str, n: int) -> list:
    """Last n daily candles (dicts with open/high/low/close/datetime)."""
    j = _get("/pricehistory", {"symbol": symbol, "periodType": "month", "period": 3,
                               "frequencyType": "daily", "frequency": 1})
    candles = j.get("candles") or []
    if not candles:
        raise PaperDataError(f"no daily candles for {symbol}")
    return candles[-n:]


def quote_last(symbol: str) -> float:
    j = _get("/quotes", {"symbols": symbol})
    q = (j.get(symbol) or {})
    v = (q.get("quote") or {}).get("lastPrice") or q.get("lastPrice") \
        or (q.get("quote") or {}).get("mark")
    if not v:
        raise PaperDataError(f"no quote for {symbol}")
    return float(v)


def vix_snapshot() -> tuple:
    """(vix_last, vix_5d_change). 5d change from daily closes; None if short."""
    last = quote_last("$VIX")
    chg = None
    try:
        closes = [float(c["close"]) for c in daily_candles("$VIX", 7)]
        # last daily candle may or may not include today; reference 5 sessions back
        ref = closes[-6] if len(closes) >= 6 else None
        if ref:
            chg = last - ref
    except PaperDataError:
        pass
    return last, chg


def spx_daily_stats() -> tuple:
    """(prior_close, atr20) from SPX daily candles."""
    candles = daily_candles("$SPX", 25)
    today = date.today()
    hist = [c for c in candles
            if date.fromtimestamp(c["datetime"] / 1000).isoformat() < today.isoformat()]
    if len(hist) < 2:
        raise PaperDataError("not enough SPX daily history")
    prior_close = float(hist[-1]["close"])
    trs = []
    for i in range(1, len(hist)):
        h, l, pc = float(hist[i]["high"]), float(hist[i]["low"]), float(hist[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr20 = sum(trs[-20:]) / min(20, len(trs)) if trs else None
    return prior_close, atr20


def spx_last() -> float:
    return quote_last("$SPX")


# ── 0DTE chain ───────────────────────────────────────────────────────────────

def fetch_chain(symbol: str = "$SPX", strike_count: int = 160) -> dict:
    """Today's chain. Index symbols get a .X fallback ($SPX -> $SPX.X)."""
    lo = date.today()
    hi = lo + timedelta(days=3)
    variants = [symbol] + ([symbol + ".X"] if symbol.startswith("$") else [])
    last_err = None
    for sym in variants:
        try:
            data = _get("/chains", {"symbol": sym, "contractType": "ALL",
                                    "strikeCount": strike_count,
                                    "includeUnderlyingQuote": "true",
                                    "fromDate": lo.isoformat(),
                                    "toDate": hi.isoformat()})
        except PaperDataError as e:
            last_err = e
            continue
        if data.get("callExpDateMap") or data.get("putExpDateMap"):
            return data
    raise last_err or PaperDataError(f"empty chain for {symbol} (tried {variants})")


def chain_0dte() -> tuple:
    """(chain, expiry) for today's SPXW 0DTE."""
    chain = fetch_chain("$SPX")
    dtes = {}
    for m in ("callExpDateMap", "putExpDateMap"):
        for exp_key in (chain.get(m) or {}):
            d, _, s = exp_key.partition(":")
            try:
                dtes[d] = int(s)
            except ValueError:
                pass
    zero = [d for d, n in dtes.items() if n == 0]
    if not zero:
        raise PaperDataError(f"no 0DTE SPX expiry listed today (listed: {sorted(dtes)[:3]})")
    return chain, min(zero)


# ── GEX sign (tag only — never an entry condition here) ──────────────────────

def gex_sign() -> str:
    """'positive' / 'negative' / 'unknown'. If the Logicon platform repo is on
    PYTHONPATH, its gex_bridge supplies the regime; otherwise 'unknown'.
    The platform repo is only imported, never modified."""
    try:
        from gex_bridge import get_gex
        g = get_gex("SPX") or {}
        regime = str(g.get("regime") or "")
    except BaseException:
        return "unknown"
    if "positive" in regime:
        return "positive"
    if "negative" in regime:
        return "negative"
    return "unknown"
