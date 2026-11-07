"""
portfolio.py — combine building blocks into one book (owner 2026-11-07,
shortfall #3: "portfolio construction — judge what an idea ADDS to the whole").

Every Phase-1 run of research_bt saves the idea's MONTHLY returns for any
idea with suggested potential >= 3 (data/research/series/<id>.json, small).
This module turns those into a portfolio view:

  correlation(series)          pairwise correlation of monthly returns
  inverse_vol_weights(series)  equal-RISK weights (each sleeve contributes
                               the same volatility) — the robust default
  combine(series, weights)     the combined monthly return stream
  stats(rets)                  annual return, vol, Sharpe, worst drawdown
  marginal(base, name, cand)   does adding `cand` at 10% raise the book's
                               Sharpe? (the question top shops ask of a new
                               signal — an uncorrelated small edge beats a
                               correlated big one)

Stdlib only. Monthly data, aligned on common months.
"""

import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent
SERIES = BASE / "data" / "research" / "series"


def monthly(dates, rets):
    """Daily (date, return) -> {YYYY-MM: compounded monthly return}."""
    out, cur, acc = {}, None, 1.0
    for d, r in zip(dates, rets):
        m = d[:7]
        if m != cur:
            if cur is not None:
                out[cur] = acc - 1
            cur, acc = m, 1.0
        acc *= 1 + r
    if cur is not None:
        out[cur] = acc - 1
    return out


def save_series(idea_id, series, meta=None):
    SERIES.mkdir(parents=True, exist_ok=True)
    (SERIES / f"{idea_id}.json").write_text(json.dumps(
        {"idea": idea_id, "monthly": {k: round(v, 6) for k, v in series.items()}, **(meta or {})}))


def load(ids=None):
    out = {}
    for f in sorted(SERIES.glob("*.json")) if SERIES.exists() else []:
        j = json.loads(f.read_text())
        if ids is None or j["idea"] in ids:
            out[j["idea"]] = j["monthly"]
    return out


def _common(series):
    months = None
    for s in series.values():
        months = set(s) if months is None else months & set(s)
    return sorted(months or [])


def _mean(x):
    return sum(x) / len(x) if x else 0.0


def _sd(x):
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else 0.0


def correlation(series):
    ms = _common(series)
    names = sorted(series)
    cols = {n: [series[n][m] for m in ms] for n in names}
    out = {}
    for a in names:
        for b in names:
            xa, xb = cols[a], cols[b]
            sa, sb = _sd(xa), _sd(xb)
            ma, mb = _mean(xa), _mean(xb)
            out[(a, b)] = (sum((u - ma) * (v - mb) for u, v in zip(xa, xb)) / ((len(ms) - 1) * sa * sb)
                           if sa and sb and len(ms) > 2 else 0.0)
    return out


def inverse_vol_weights(series):
    ms = _common(series)
    inv = {n: 1 / _sd([s[m] for m in ms]) for n, s in series.items() if _sd([s[m] for m in ms])}
    tot = sum(inv.values())
    return {n: v / tot for n, v in inv.items()}


def combine(series, weights):
    ms = _common(series)
    return {m: sum(w * series[n][m] for n, w in weights.items()) for m in ms}


def stats(rets):
    x = list(rets.values()) if isinstance(rets, dict) else list(rets)
    if len(x) < 12:
        return None
    eq = peak = 1.0
    dd = 0.0
    for r in x:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    sd = _sd(x)
    return {"months": len(x), "ann_return": round(eq ** (12 / len(x)) - 1, 4),
            "ann_vol": round(sd * math.sqrt(12), 4),
            "sharpe": round(_mean(x) / sd * math.sqrt(12), 3) if sd else 0.0,
            "max_dd": round(dd, 4)}


def marginal(base, name, cand, weight=0.10):
    """Book = inverse-vol mix of `base`; add `cand` at `weight`. Sharpe gain?"""
    w0 = inverse_vol_weights(base)
    allser = dict(base, **{name: cand})
    ms = _common(allser)
    trimmed = {n: {m: s[m] for m in ms} for n, s in allser.items()}
    book = combine({n: trimmed[n] for n in base}, w0)
    w1 = {n: w * (1 - weight) for n, w in w0.items()}
    w1[name] = weight
    new = combine(trimmed, w1)
    s0, s1 = stats(book), stats(new)
    cb = [book[m] for m in ms]
    cc = [trimmed[name][m] for m in ms]
    corr = correlation({"book": dict(zip(ms, cb)), "cand": dict(zip(ms, cc))})[("book", "cand")]
    return {"book": s0, "with_candidate": s1, "corr_to_book": round(corr, 2),
            "sharpe_gain": round(s1["sharpe"] - s0["sharpe"], 3) if s0 and s1 else None,
            "adds_value": bool(s0 and s1 and s1["sharpe"] > s0["sharpe"])}
