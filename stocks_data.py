"""
stocks_data.py — the eyes of the Stocks & ETF sandbox
======================================================
Every network call of stocks_engine.py lives here, behind StocksDataError,
so a data problem becomes a SKIP/DATA journal row instead of a crash.

Sources (estate rules): Schwab market data through the ONE shared token
(schwab_auth, shared mode on the hub — never a second grant), with Yahoo as
the fallback so marks survive the weekly Schwab token lapses.

Daily bars are fetched once per session (premarket) for the whole universe
and cached in data/stocks/cache/ (git-ignored). Calls are self-paced at one
per second: the options engine and the platform share Schwab's ~120 req/min
ceiling on the same app.

Bars are dicts {date: 'YYYY-MM-DD', open, high, low, close}, oldest first,
split-adjusted (both Schwab and Yahoo chart closes are).
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import stocks_store as st

ET = ZoneInfo("America/New_York")
MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
UA = {"User-Agent": "Mozilla/5.0 (LogiconStocksLab)"}
MIN_CALL_GAP_S = 1.0
YAHOO_SYM = {"$VIX": "^VIX"}


class StocksDataError(RuntimeError):
    pass


_last_call = 0.0


def _pace():
    global _last_call
    wait = MIN_CALL_GAP_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _schwab_get(path: str, params: dict) -> dict:
    try:
        import schwab_auth
        tok = schwab_auth.get_access_token()
    except Exception as e:
        raise StocksDataError(f"Schwab auth: {e}") from e
    for attempt in (1, 2):
        _pace()
        try:
            r = requests.get(f"{MARKETDATA_BASE}{path}",
                             headers={"Authorization": f"Bearer {tok}",
                                      "Accept": "application/json"},
                             params=params, timeout=30)
        except requests.RequestException as e:
            if attempt == 1:
                time.sleep(2)
                continue
            raise StocksDataError(f"GET {path}: {e}") from e
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503) and attempt == 1:
            time.sleep(3)
            continue
        raise StocksDataError(f"GET {path}: HTTP {r.status_code}")
    raise StocksDataError(f"GET {path}: retries exhausted")


def _yahoo_chart(sym: str, rng: str, interval: str) -> dict:
    ys = YAHOO_SYM.get(sym, sym.replace(".", "-"))
    _pace()
    try:
        r = requests.get(YAHOO_CHART.format(sym=ys), headers=UA, timeout=20,
                         params={"range": rng, "interval": interval})
    except requests.RequestException as e:
        raise StocksDataError(f"yahoo {sym}: {e}") from e
    if r.status_code != 200:
        raise StocksDataError(f"yahoo {sym}: HTTP {r.status_code}")
    res = ((r.json().get("chart") or {}).get("result") or [None])[0]
    if not res:
        raise StocksDataError(f"yahoo {sym}: empty result")
    return res


# ── daily bars ───────────────────────────────────────────────────────────────

def _day(ms_or_s: float, ms=True) -> str:
    t = ms_or_s / 1000 if ms else ms_or_s
    return datetime.fromtimestamp(t, ET).date().isoformat()


def _schwab_bars(sym: str) -> list:
    j = _schwab_get("/pricehistory", {"symbol": sym, "periodType": "year",
                                      "period": 2, "frequencyType": "daily",
                                      "frequency": 1})
    out = []
    for c in j.get("candles") or []:
        if c.get("close") is None:
            continue
        out.append({"date": _day(c["datetime"]), "open": float(c["open"]),
                    "high": float(c["high"]), "low": float(c["low"]),
                    "close": float(c["close"])})
    if len(out) < 30:
        raise StocksDataError(f"schwab: only {len(out)} bars for {sym}")
    return out


def _yahoo_bars(sym: str) -> list:
    res = _yahoo_chart(sym, "2y", "1d")
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    out = []
    for i, t in enumerate(ts):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        except (KeyError, IndexError):
            continue
        if None in (o, h, l, c):
            continue
        out.append({"date": _day(t, ms=False), "open": float(o),
                    "high": float(h), "low": float(l), "close": float(c)})
    if len(out) < 30:
        raise StocksDataError(f"yahoo: only {len(out)} bars for {sym}")
    return out


def long_bars(sym: str, years: int = 10) -> list:
    """Long daily history for the backtester — Schwab, Yahoo fallback."""
    try:
        j = _schwab_get("/pricehistory", {"symbol": sym, "periodType": "year",
                                          "period": min(20, max(1, years)),
                                          "frequencyType": "daily", "frequency": 1})
        out = [{"date": _day(c["datetime"]), "open": float(c["open"]),
                "high": float(c["high"]), "low": float(c["low"]),
                "close": float(c["close"])}
               for c in j.get("candles") or [] if c.get("close") is not None]
        if len(out) >= 300:
            return out
    except StocksDataError:
        pass
    res = _yahoo_chart(sym, f"{years}y", "1d")
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    out = []
    for i, t in enumerate(ts):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        except (KeyError, IndexError):
            continue
        if None in (o, h, l, c):
            continue
        out.append({"date": _day(t, ms=False), "open": float(o), "high": float(h),
                    "low": float(l), "close": float(c)})
    if len(out) < 300:
        raise StocksDataError(f"{sym}: only {len(out)} long bars")
    return out


def bars_for(sym: str) -> tuple:
    """(bars, source) — Schwab first, Yahoo fallback."""
    try:
        return _schwab_bars(sym), "schwab"
    except StocksDataError as e1:
        try:
            return _yahoo_bars(sym), "yahoo"
        except StocksDataError as e2:
            raise StocksDataError(f"{sym}: {e1}; {e2}") from e2


def universe_bars(symbols: list, asof: str) -> tuple:
    """({sym: bars through the prior close}, {source: count}, [failed]).
    Cached per session date; bars dated >= asof (a partial today) are cut."""
    cache = Path(st.DATA_DIR) / "cache" / f"bars_{asof}.json"
    data = {}
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
        except ValueError:
            data = {}
    src, failed = {}, []
    for sym in symbols:
        if sym in data:
            src["cache"] = src.get("cache", 0) + 1
            continue
        try:
            bars, s = bars_for(sym)
        except StocksDataError as e:
            print(f"bars: {e}", flush=True)
            failed.append(sym)
            continue
        data[sym] = [b for b in bars if b["date"] < asof]
        src[s] = src.get(s, 0) + 1
    os.makedirs(cache.parent, exist_ok=True)
    cache.write_text(json.dumps(data))
    for old in sorted(cache.parent.glob("bars_*.json"))[:-5]:   # keep 5 sessions
        try:
            old.unlink()
        except OSError:
            pass
    return data, src, failed


# ── quotes ───────────────────────────────────────────────────────────────────

def _q_last(q: dict):
    qq = q.get("quote") or {}
    for k in ("lastPrice", "mark", "closePrice"):
        v = qq.get(k) or q.get(k)
        if v:
            return float(v)
    return None


def quotes(symbols: list) -> dict:
    """{sym: last} — Schwab batch, Yahoo per-symbol fallback for misses.
    Symbols with no price anywhere are simply absent."""
    out = {}
    syms = sorted(set(symbols))
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        try:
            j = _schwab_get("/quotes", {"symbols": ",".join(chunk)})
        except StocksDataError as e:
            print(f"quotes: schwab failed ({e}) — yahoo fallback", flush=True)
            j = {}
        for s in chunk:
            v = _q_last(j.get(s) or {})
            if v:
                out[s] = v
    for s in syms:
        if s in out:
            continue
        try:
            meta = _yahoo_chart(s, "1d", "1m").get("meta") or {}
            v = meta.get("regularMarketPrice")
            if v:
                out[s] = float(v)
        except StocksDataError:
            pass
    return out


def vix_last():
    return quotes(["$VIX"]).get("$VIX")
