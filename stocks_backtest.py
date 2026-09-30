"""
stocks_backtest.py — historical replay of the stocks sandbox rules
==================================================================
Pipeline (STOCKS_SPEC.md §9):  BACKTEST ─pass─▶ PAPER ─gate─▶ LIVE PILOT.
A strategy only reaches the paper engine after it passes the backtest bar
below and the owner sets `stage: paper` in stocks_config.yaml.

Same brain, no copy: candidates, stops, targets, the MOM double-down,
two-phase trailing, rule exits, sizing, heat/budget/cash rails, penny-grid
slippage and sell fees are the SAME functions stocks_engine.py trades with.
Only the clock and the price feed differ:

  09:45 entry quote     -> the day's OPEN (signals from bars before that day)
  intraday stop/target  -> the day's LOW / HIGH; a gap through the level
                           fills at the open; stop AND target the same day
                           counts as the stop (conservative)
  15:50 rule exits      -> the day's CLOSE
  16:10 mark / trail    -> the day's CLOSE

Known biases, stated rather than hidden:
  * SURVIVORSHIP — the universe is TODAY's large caps, so history flatters
    any long strategy. That's why a strategy must beat buy-and-hold of the
    SAME universe (which carries the same bias), not just SPY.
  * Price-only (split-adjusted, no dividends) for strategies AND benchmarks.
  * Daily bars can't see the intraday path: stop fills are approximations.

Every run is appended to data/stocks/backtests/runs.csv with a hash of the
strategy's parameters: the number of variants tried stays visible (the
anti-p-hacking record). Latest result per strategy: latest_<STRAT>.json.

CLI:
    python3 stocks_backtest.py                     # all strategies, 10y
    python3 stocks_backtest.py --strategy MOM --start 2016-01-01
"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import stocks_engine as se
import stocks_report as sr
import stocks_store as st

WINDOW = 260          # bars fed to features(): SMA200, r252, hi63, RSI warm-up
IS_FRACTION = 0.7     # in-sample / out-of-sample split of the window

GATE_DEFAULTS = {"min_trades": 50, "min_pf": 1.3, "min_confidence": 0.90,
                 "oos_min_pf": 1.1, "max_dd_pct": 0.15, "beat_benchmark_sharpe": True}


def bt_dir() -> Path:
    return Path(st.DATA_DIR) / "backtests"


# ── history ──────────────────────────────────────────────────────────────────

def load_history(symbols: list, years: int = 10, max_age_h: float = 20,
                 total_return: bool = False) -> dict:
    """{sym: bars} — long daily history, cached per symbol (git-ignored).
    total_return: dividend-adjusted bars (Yahoo adjclose) in history_tr/."""
    import stocks_data as sd
    cache = Path(st.DATA_DIR) / ("history_tr" if total_return else "history")
    os.makedirs(cache, exist_ok=True)
    out = {}
    for s in symbols:
        f = cache / f"{s}.json"
        if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
            out[s] = json.loads(f.read_text())
            continue
        try:
            bars = sd.total_return_bars(s, years) if total_return else sd.long_bars(s, years)
        except sd.StocksDataError as e:
            print(f"history: {e}", flush=True)
            if f.exists():
                out[s] = json.loads(f.read_text())
            continue
        f.write_text(json.dumps(bars))
        out[s] = bars
    return out


def load_rates(years: int = 10, max_age_h: float = 20) -> dict:
    """{date: daily risk-free rate} from the 13-week T-bill, forward-filled
    by callers (rates are annual %, /252 per session)."""
    import stocks_data as sd
    f = Path(st.DATA_DIR) / "history_tr" / "_IRX.json"
    os.makedirs(f.parent, exist_ok=True)
    if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
        rows = json.loads(f.read_text())
    else:
        rows = sd.tbill_rates(years)
        f.write_text(json.dumps(rows))
    return {d: r / 100 / 252 for d, r in rows}


def rf_series(rf: dict, cal: list) -> list:
    """Daily risk-free rates aligned to the calendar (forward-filled)."""
    out, last = [], 0.0
    keys = sorted(rf)
    import bisect
    for d in cal:
        i = bisect.bisect_right(keys, d) - 1
        last = rf[keys[i]] if i >= 0 else last
        out.append(last)
    return out


def apply_cash_yield(curve: list, rf: dict, eq0: float) -> tuple:
    """Credit T-bill interest on idle cash (equity − invested notional) each
    session. Returns (new curve, total interest)."""
    if not curve:
        return curve, 0.0
    rates = rf_series(rf, [c["date"] for c in curve])
    out, interest = [], 0.0
    for i, c in enumerate(curve):
        if i:
            prev = out[-1]
            cash = prev["equity"] - curve[i - 1].get("exposure", 0) * eq0
            interest += max(0.0, cash) * rates[i]
        out.append({**c, "equity": round(c["equity"] + interest, 2)})
    return out, round(interest, 2)


# ── simulation ───────────────────────────────────────────────────────────────

def _pos(pid, strat, sym, tier, d, qty, entry, stop, tgt, risk, fill):
    return {"position_id": pid, "strategy": strat, "symbol": sym, "side": "LONG",
            "tier": tier, "entry_ts": d, "qty": qty, "entry_px_theo": entry,
            "stop_px_initial": stop, "target_px": tgt, "risk_usd": risk,
            "stop_px": stop, "peak_px": entry, "phase": "1", "split_factor": 1,
            "entry_px_actual": fill, "entry_i": None}


# ── point-in-time S&P 500 membership (survivorship control) ────────────────
# reference/sp500_pit.csv: the full member list on its first date, then one
# row per change (added / removed tickers). Source: fja05680/sp500 (Andreas
# Clenow's list from 'Trading Evolved', maintained from Wikipedia changes).
PIT_FILE = Path(__file__).resolve().parent / "reference" / "sp500_pit.csv"


def load_pit(path=None):
    """[(date, frozenset(members))] in date order."""
    snaps, cur = [], set()
    with open(path or PIT_FILE, newline="") as f:
        for r in csv.DictReader(f):
            cur = (cur | set(r["added"].split())) - set(r["removed"].split())
            snaps.append((r["date"], frozenset(cur)))
    return snaps


def members_fn(snaps):
    """d -> the index members on d (the latest snapshot dated <= d)."""
    import bisect
    dates = [d for d, _ in snaps]

    def members(d):
        i = bisect.bisect_right(dates, d) - 1
        return snaps[i][1] if i >= 0 else frozenset()
    return members


def pit_tickers(snaps, start: str) -> set:
    out = set()
    for d, m in snaps:
        out |= m
    return out


def simulate(cfg: dict, bars: dict, strategy: str, start: str, end: str,
             members=None) -> dict:
    """Replay one strategy in isolation over [start, end]. Pure: no I/O.
    members: optional d -> set of tickers — the point-in-time stock universe
    (stock lanes only); names that later left the index are included."""
    key = strategy.lower()
    c = cfg[key]
    pit = members is not None and strategy not in se.ETF_STRATEGIES
    group = [s for s in se.group_of(strategy, cfg) if s in bars]
    stocks = [s for s in cfg["universe"]["stocks"] if s in bars]
    etfs = [s for s in cfg["universe"]["etfs"] if s in bars]
    cal = [b["date"] for b in bars["SPY"] if start <= b["date"] <= end]
    idx = {s: {b["date"]: i for i, b in enumerate(v)} for s, v in bars.items()}
    last_day = {s: v[-1]["date"] for s, v in bars.items() if v}
    cand_fn = se.CANDIDATES[strategy]
    need_ctx = (strategy in ("MOMR", "SECROT", "TOM") or strategy in se.ROTATION
                or strategy in se.WEIGHTED)
    eq0 = float(cfg["account_equity"])
    opens, trades, curve = [], [], []
    realized = 0.0
    last_close = {}

    def today_bar(s, d):
        i = idx[s].get(d)
        return bars[s][i] if i is not None else None

    som = 0
    for di, d in enumerate(cal):
        som = 1 if di == 0 or cal[di - 1][:7] != d[:7] else som + 1

        def feats_for(syms):
            fi = {}
            for s in syms:
                i = idx[s].get(d)
                if i is None or i < 30:
                    continue
                fi[s] = bars[s][max(0, i - WINDOW):i]
            return se.universe_features(fi, list(fi))
        if pit:
            group = [s for s in members(d) if s in bars]
        # features from bars strictly before d (what the premarket step sees)
        fe = feats_for(group)
        ctx = None
        if need_ctx:
            etf_strat = strategy in se.ETF_STRATEGIES
            fe_all = {"stocks": {} if etf_strat else fe,       # breadth: stock lanes only
                      "etfs": fe if etf_strat else
                      feats_for(etfs if strategy == "MOMR" else ["SPY"])}
            eom = di + 1 < len(cal) and cal[di + 1][:7] != d[:7]
            ctx = se.session_ctx(fe_all, d, som=som, eom=eom)
        q_open = {s: b["open"] for s in group if (b := today_bar(s, d))}
        new_risk = 0.0

        def book(ref):
            heat = sum(se.open_risk(p, ref.get(p["symbol"], se.avg_cost(p))) for p in opens)
            notional = sum(se.eff_qty(p) * ref.get(p["symbol"], se.avg_cost(p)) for p in opens)
            return heat, notional

        # 1. adds (MOM double-down) then entries, at the open
        if se.family(strategy) == "MOM":
            for p in opens:
                last = q_open.get(p["symbol"])
                if not p.get("add_ts") and se.mom_add_ok(p, fe.get(p["symbol"]), last, c):
                    stop_now = round(max(p["peak_px"], last) * c["ph2_trail"], 2)
                    qty_now = int(round(se.eff_qty(p)))
                    risk = round(qty_now * max(0.0, last - stop_now), 2)
                    heat, notional = book(last_close)
                    if (new_risk + risk <= eq0 * cfg["daily_new_risk_pct"]
                            and notional + qty_now * last <= eq0):
                        bps = cfg["slippage_bps"][p["tier"]]
                        p.update(add_ts=d, add_qty=qty_now, add_px_theo=last,
                                 add_px_actual=se.sim_buy(last, bps), phase="2",
                                 stop_px=stop_now)
                        new_risk += risk
        held = {p["symbol"] for p in opens}
        n_new = 0
        for sym in cand_fn(fe, c, ctx):
            if sym in held:
                continue
            if n_new >= c["max_new_per_day"] or len(opens) >= c["max_open"]:
                break
            last = q_open.get(sym)
            if not last:
                continue
            f = fe[sym]
            stop = se.initial_stop(strategy, last, f, cfg)
            tgt = se.initial_target(strategy, last, f)
            heat, notional = book(last_close)
            w_ = se.lane_weights(strategy, fe, c).get(sym) if strategy in se.WEIGHTED else None
            qty, risk, why = se.size_for(strategy, last, stop, cfg, heat, new_risk, notional,
                                         weight=w_)
            if why:
                continue
            tier = se.tier_of(sym, cfg)
            p = _pos(f"{d}-{strategy}-{sym}", strategy, sym, tier, d, qty, last,
                     stop, tgt, risk, se.sim_buy(last, cfg["slippage_bps"][tier]))
            p["entry_i"] = di
            opens.append(p)
            held.add(sym)
            new_risk += risk
            n_new += 1

        # 2. intraday stop / target on the day's range; 3. rule exits at close
        still = []
        for p in opens:
            b = today_bar(p["symbol"], d)
            if not b:
                if last_day.get(p["symbol"], d) < d:    # delisted / acquired
                    px = last_close.get(p["symbol"], se.avg_cost(p))
                    pnl = se.campaign_pnl(p, px, cfg, actual=True)
                    realized += pnl
                    trades.append({"symbol": p["symbol"], "entry": p["entry_ts"], "exit": d,
                                   "reason": "DELISTED", "held": di - p["entry_i"],
                                   "qty": se.eff_qty(p), "avg_cost": round(se.avg_cost(p, True), 4),
                                   "exit_px": px, "pnl": pnl, "added": bool(p.get("add_ts"))})
                    continue
                still.append(p)
                continue
            stop, tgt = p["stop_px"], p.get("target_px")
            fresh = p["entry_i"] == di
            exit_ = None
            if stop is not None and b["low"] <= stop:
                exit_ = ("STOPPED", stop if fresh else min(b["open"], stop))
            elif tgt is not None and b["high"] >= tgt:
                exit_ = ("TARGET", tgt if fresh else max(b["open"], tgt))
            else:
                why = se.rule_exit(p, fe.get(p["symbol"]) or _feat_now(bars, idx, p["symbol"], d),
                                   b["close"], d, cfg, held=di - p["entry_i"], ctx=ctx)
                if why:
                    exit_ = (why, b["close"])
            if not exit_:
                still.append(p)
                continue
            theo = exit_[1]
            fill = se.sim_sell(theo, cfg["slippage_bps"][p["tier"]])
            pnl = se.campaign_pnl(p, fill, cfg, actual=True)
            realized += pnl
            trades.append({"symbol": p["symbol"], "entry": p["entry_ts"], "exit": d,
                           "reason": exit_[0], "held": di - p["entry_i"],
                           "qty": se.eff_qty(p), "avg_cost": round(se.avg_cost(p, True), 4),
                           "exit_px": fill, "pnl": pnl, "added": bool(p.get("add_ts"))})
        opens = still

        # 4. mark at the close, trail stops
        unreal = 0.0
        for p in opens:
            b = today_bar(p["symbol"], d)
            close = b["close"] if b else last_close.get(p["symbol"], se.avg_cost(p))
            last_close[p["symbol"]] = close
            p["peak_px"] = max(p["peak_px"], close)
            p["stop_px"] = se.trail_stop(p, p["peak_px"], cfg)
            unreal += (close - se.avg_cost(p, True)) * se.eff_qty(p)
        for s in group:
            b = today_bar(s, d)
            if b:
                last_close[s] = b["close"]
        exposure = sum(se.eff_qty(p) * last_close.get(p["symbol"], 0) for p in opens)
        curve.append({"date": d, "equity": round(eq0 + realized + unreal, 2),
                      "exposure": round(exposure / eq0, 4)})
    return {"trades": trades, "curve": curve, "open_at_end": len(opens)}


def _feat_now(bars, idx, sym, d):
    i = idx.get(sym, {}).get(d)
    return se.features(bars[sym][max(0, i - WINDOW):i]) if i else None


# ── metrics ──────────────────────────────────────────────────────────────────

def _octane(m: dict) -> dict:
    if m.get("avg_exposure"):
        m["cagr_on_exposure"] = round(m["cagr"] / m["avg_exposure"], 4)
    return m


def curve_metrics(curve: list, eq0: float, rf: dict = None) -> dict:
    """rf given → Sharpe on EXCESS returns over the T-bill (textbook)."""
    if len(curve) < 2:
        return {}
    eqs = [c["equity"] for c in curve]
    rates = rf_series(rf, [c["date"] for c in curve]) if rf else [0.0] * len(curve)
    rets = [eqs[i] / eqs[i - 1] - 1 - rates[i] for i in range(1, len(eqs)) if eqs[i - 1] > 0]
    yrs = len(curve) / 252
    peak, dd = eqs[0], 0.0
    for e in eqs:
        peak = max(peak, e)
        dd = min(dd, e / peak - 1)
    mu = sum(rets) / len(rets) if rets else 0
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    return {"cagr": round(((eqs[-1] / eq0) ** (1 / yrs) - 1) if yrs > 0 and eqs[-1] > 0 else 0, 4),
            "total_return": round(eqs[-1] / eq0 - 1, 4),
            "max_dd_pct": round(dd, 4),
            "sharpe": round(mu / sd * math.sqrt(252), 2) if sd > 0 else None,
            "avg_exposure": round(sum(c.get("exposure", 1) for c in curve) / len(curve), 3),
            # "octane": return per unit of capital actually deployed
            "cagr_on_exposure": None}


def benchmark_curve(bars: dict, symbols: list, cal: list, eq0: float) -> list:
    """Equal-weight buy-and-hold equity values (one per calendar day with data)."""
    per = [s for s in symbols if s in bars]
    pxs = {s: {b["date"]: b["close"] for b in bars[s]} for s in per}
    first, out = {}, []
    for d in cal:
        vals = []
        for s in per:
            v = pxs[s].get(d)
            if v is None:
                continue
            first.setdefault(s, v)
            vals.append(v / first[s])
        if vals:
            out.append(eq0 * sum(vals) / len(vals))
    return out


def pit_index_curve(bars: dict, members, cal: list, eq0: float) -> tuple:
    """Equal-weight, daily-rebalanced index of the point-in-time members that
    have prices ([equity...], coverage = share of member-days with data)."""
    px = {s: {b["date"]: b["close"] for b in v} for s, v in bars.items()}
    eq, out, have, total = eq0, [], 0, 0
    for i, d in enumerate(cal):
        if i == 0:
            out.append(eq)
            continue
        prev = cal[i - 1]
        rets = []
        m = members(d)
        total += len(m)
        for s in m:
            a, b = px.get(s, {}).get(prev), px.get(s, {}).get(d)
            if a and b:
                rets.append(b / a - 1)
        have += len(rets)
        if rets:
            eq *= 1 + sum(rets) / len(rets)
        out.append(eq)
    return out, (have / total if total else None)


def benchmark(bars: dict, symbols: list, cal: list, eq0: float, rf: dict = None) -> dict:
    """Equal-weight buy-and-hold of `symbols` from the first to last day."""
    per = [s for s in symbols if s in bars]
    if not per:
        return {}
    pxs = {s: {b["date"]: b["close"] for b in bars[s]} for s in per}
    first = {}
    curve = []
    for d in cal:
        vals = []
        for s in per:
            v = pxs[s].get(d)
            if v is None:
                continue
            first.setdefault(s, v)
            vals.append(v / first[s])
        if vals:
            curve.append({"date": d, "equity": eq0 * sum(vals) / len(vals)})
    return curve_metrics(curve, eq0, rf)


STRESS = {"2018 Q4 selloff": ("2018-10-01", "2018-12-24"),
          "2020 COVID crash": ("2020-02-19", "2020-03-23"),
          "2022 bear market": ("2022-01-03", "2022-10-12")}


def _window_dd(pts):
    peak, dd = None, 0.0
    for v in pts:
        peak = v if peak is None else max(peak, v)
        dd = min(dd, v / peak - 1)
    return dd


def stress(curve: list, bars: dict, group: list, eq0: float) -> dict:
    """Strategy vs same-universe hold inside each named crisis window."""
    out = {}
    for name, (a, b) in STRESS.items():
        pts = [c["equity"] for c in curve if a <= c["date"] <= b]
        if len(pts) < 5:
            continue
        cal = [c["date"] for c in curve if a <= c["date"] <= b]
        bm = benchmark_curve(bars, group, cal, eq0)
        out[name] = {"strategy_pct": round(pts[-1] / pts[0] - 1, 4),
                     "strategy_dd": round(_window_dd(pts), 4),
                     "hold_pct": round(bm[-1] / bm[0] - 1, 4) if bm else None}
    return out


def by_year(trades: list) -> dict:
    out = {}
    for t in trades:
        y = t["exit"][:4]
        r = out.setdefault(y, {"n": 0, "pnl": 0.0, "wins": 0})
        r["n"] += 1
        r["pnl"] = round(r["pnl"] + t["pnl"], 2)
        r["wins"] += t["pnl"] > 0
    return out


def params_hash(cfg: dict, strategy: str) -> str:
    blob = json.dumps({"s": cfg[strategy.lower()],
                       "sizing": {k: cfg[k] for k in ("account_equity", "risk_per_trade_pct",
                                                      "max_notional_pct", "heat_cap_pct",
                                                      "daily_new_risk_pct", "slippage_bps")}},
                      sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


def verdict(res: dict, gate: dict, eq0: float) -> dict:
    s, isr, oos = res["stats"], res["in_sample"], res["out_of_sample"]
    bench = res["benchmark_universe"]
    checks = [
        ("trades", s["n"] >= gate["min_trades"], f"{s['n']} ≥ {gate['min_trades']}"),
        ("expectancy", (s.get("expectancy") or 0) > 0 and (s.get("confidence") or 0) >= gate["min_confidence"],
         f"${s.get('expectancy')} at {round(100 * (s.get('confidence') or 0))}% conf (≥ {round(100 * gate['min_confidence'])}%)"),
        ("profit factor", (s.get("pf") or 0) >= gate["min_pf"], f"{s.get('pf')} ≥ {gate['min_pf']}"),
        ("out-of-sample", (oos.get("expectancy") or 0) > 0 and (oos.get("pf") or 0) >= gate["oos_min_pf"],
         f"last {round(100 * (1 - IS_FRACTION))}%: n={oos.get('n')} PF {oos.get('pf')} (≥ {gate['oos_min_pf']})"),
        ("drawdown", abs(res["metrics"].get("max_dd_pct") or 0) <= gate["max_dd_pct"],
         f"{round(100 * (res['metrics'].get('max_dd_pct') or 0), 1)}% (limit −{round(100 * gate['max_dd_pct'])}%)"),
    ]
    if gate.get("beat_benchmark_sharpe"):
        ms, bs = res["metrics"].get("sharpe"), bench.get("sharpe")
        checks.append(("beats buy-and-hold", ms is not None and bs is not None and ms >= bs,
                       f"Sharpe {ms} vs {bs} (same-universe buy-and-hold)"))
    passed = all(ok for _, ok, _ in checks)
    return {"pass": passed, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
            "label": "PASS — eligible for paper" if passed else "FAIL — stays out of paper"}


def combine(sims: list) -> dict:
    """One $-account running several lanes: P&L streams add, exposures add.
    Valid while the combined exposure stays <= 100% (reported, checked)."""
    by = {}
    for sim in sims:
        for c in sim["curve"]:
            r = by.setdefault(c["date"], {"pnl": 0.0, "exposure": 0.0, "n": 0})
            r["pnl"] += c["equity"]
            r["exposure"] += c.get("exposure", 0)
            r["n"] += 1
    k = len(sims)
    curve = []
    for d in sorted(by):
        r = by[d]
        if r["n"] != k:
            continue
        # sum of (equity_i − eq0) + eq0, with every lane starting at eq0
        curve.append({"date": d, "equity": round(r["pnl"] - (k - 1) * sims[0]["eq0"], 2),
                      "exposure": round(r["exposure"], 4)})
    trades = sorted((t for sim in sims for t in sim["trades"]), key=lambda t: t["exit"])
    return {"trades": trades, "curve": curve,
            "open_at_end": sum(sim["open_at_end"] for sim in sims),
            "max_exposure": max((c["exposure"] for c in curve), default=0)}


def run(cfg: dict, bars: dict, strategy: str, start: str, end: str, members=None,
        total_return: bool = False, rf: dict = None) -> dict:
    eq0 = float(cfg["account_equity"])
    if strategy == "STACK":
        comps = cfg["stack"]["components"]
        sims = []
        for cs in comps:
            sim_ = simulate(cfg, bars, cs, start, end)
            sim_["eq0"] = eq0
            sims.append(sim_)
        sim = combine(sims)
        group = sorted({s for cs in comps for s in se.group_of(cs, cfg)})
        pit = False
    else:
        pit = members is not None and strategy not in se.ETF_STRATEGIES
        sim = simulate(cfg, bars, strategy, start, end, members=members if pit else None)
        group = se.group_of(strategy, cfg)
    interest = 0.0
    if rf:
        sim["curve"], interest = apply_cash_yield(sim["curve"], rf, eq0)
    cal = [c["date"] for c in sim["curve"]]
    trades = sim["trades"]
    split = cal[int(len(cal) * IS_FRACTION)] if cal else end
    res = {
        "strategy": strategy, "start": cal[0] if cal else start, "end": cal[-1] if cal else end,
        "sessions": len(cal), "params_hash": params_hash(cfg, strategy),
        "params": cfg[strategy.lower()], "ran_at": datetime.now().isoformat(timespec="seconds"),
        "stats": sr.stats([t["pnl"] for t in trades]),
        "in_sample": sr.stats([t["pnl"] for t in trades if t["exit"] < split]),
        "out_of_sample": sr.stats([t["pnl"] for t in trades if t["exit"] >= split]),
        "oos_from": split,
        "metrics": _octane(curve_metrics(sim["curve"], eq0, rf)),
        "benchmark_spy": benchmark(bars, ["SPY"], cal, eq0, rf),
        "benchmark_universe": benchmark(bars, group, cal, eq0, rf),
        "cash_yield": bool(rf), "interest": interest,
        "max_exposure": sim.get("max_exposure"),
        "universe_mode": "pit_sp500" if pit else "fixed_today",
        "total_return": total_return,
        "by_year": by_year(trades),
        "stress": stress(sim["curve"], bars, group, eq0),
        "exit_reasons": {r: sum(1 for t in trades if t["reason"] == r)
                         for r in sorted({t["reason"] for t in trades})},
        "avg_hold": round(sum(t["held"] for t in trades) / len(trades), 1) if trades else None,
        "open_at_end": sim["open_at_end"],
        "curve": sim["curve"][::5],                       # weekly-ish, for the chart
        "trades_tail": trades[-40:],
        "universe_size": len([s for s in group if s in bars]),
    }
    if pit:
        ic, cov = pit_index_curve(bars, members, cal, eq0)
        res["benchmark_universe"] = curve_metrics(
            [{"date": d, "equity": e} for d, e in zip(cal, ic)], eq0, rf)
        res["pit_coverage"] = round(cov, 4) if cov is not None else None
        res["universe_size"] = len({s for d in cal[::21] for s in members(d)})
        res["stress"] = stress(sim["curve"], bars, [], eq0)
        for k, (a, b) in STRESS.items():
            w = [e for d, e in zip(cal, ic) if a <= d <= b]
            if k in res["stress"] and len(w) > 1:
                res["stress"][k]["hold_pct"] = round(w[-1] / w[0] - 1, 4)
    gate = dict(GATE_DEFAULTS, **(cfg.get("backtest_gate") or {}))
    res["gate"] = gate
    res["verdict"] = verdict(res, gate, eq0)
    if strategy == "STACK":                    # a shared account can't exceed its cash
        ok_ = (res["max_exposure"] or 0) <= 1.0
        res["verdict"]["checks"].append({"name": "fits one account", "ok": ok_,
                                         "detail": f"peak combined exposure {round(100 * (res['max_exposure'] or 0))}% (≤ 100%)"})
        res["verdict"]["pass"] = res["verdict"]["pass"] and ok_
        res["verdict"]["label"] = ("PASS — eligible for paper" if res["verdict"]["pass"]
                                   else "FAIL — stays out of paper")
    return res


def save(res: dict):
    d = bt_dir()
    os.makedirs(d, exist_ok=True)
    tag = ("_pit" if res.get("universe_mode") == "pit_sp500" else "") + \
        ("_tr" if res.get("total_return") else "") + ("_rf" if res.get("cash_yield") else "")
    (d / f"latest_{res['strategy']}{tag}.json").write_text(json.dumps(res))
    path = d / "runs.csv"
    cols = ["ran_at", "strategy", "universe_mode", "total_return", "cash_yield", "params_hash", "start", "end", "trades", "expectancy",
            "pf", "confidence", "max_dd_pct", "sharpe", "bench_sharpe", "verdict"]
    if path.exists():                     # upgrade a pre-universe_mode file in place
        with open(path, newline="") as f:
            old = list(csv.DictReader(f))
        if old and "cash_yield" not in old[0]:
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                for r in old:
                    w.writerow({**{c: r.get(c, "") for c in cols},
                                "universe_mode": r.get("universe_mode") or "fixed_today"})
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        s = res["stats"]
        w.writerow({"ran_at": res["ran_at"], "strategy": res["strategy"],
                    "universe_mode": res.get("universe_mode", "fixed_today"),
                    "total_return": "1" if res.get("total_return") else "",
                    "cash_yield": "1" if res.get("cash_yield") else "",
                    "params_hash": res["params_hash"], "start": res["start"], "end": res["end"],
                    "trades": s["n"], "expectancy": s.get("expectancy"), "pf": s.get("pf"),
                    "confidence": s.get("confidence"), "max_dd_pct": res["metrics"].get("max_dd_pct"),
                    "sharpe": res["metrics"].get("sharpe"),
                    "bench_sharpe": res["benchmark_universe"].get("sharpe"),
                    "verdict": "PASS" if res["verdict"]["pass"] else "FAIL"})


SHIPPED_DIR = Path(__file__).resolve().parent / "reference" / "backtests"


RIGOR = ("_pit_tr_rf", "_pit_tr", "_pit", "_tr_rf", "_tr", "_rf", "")   # most rigorous first
BT_ONLY = ("STACK",)          # backtest-only books (combinations of lanes)


def load_best() -> dict:
    """Per strategy, the most rigorous result available: point-in-time +
    dividends, then point-in-time, then dividends, then the basic run."""
    out = {}
    for strat in se.STRATEGIES + BT_ONLY:
        for tag in RIGOR:
            for d in (bt_dir(), SHIPPED_DIR):
                f = d / f"latest_{strat}{tag}.json"
                if f.exists() and strat not in out:
                    try:
                        out[strat] = json.loads(f.read_text())
                    except ValueError:
                        pass
    return out


def load_latest(pit: bool = False) -> dict:
    """Latest result per strategy. Point-in-time runs are heavy (~750 symbols),
    so they are run offline and SHIPPED with the code in reference/backtests/
    (the hub's deploy never copies data/); a local run in data/ wins."""
    out = {}
    for strat in se.STRATEGIES:
        name = f"latest_{strat}{'_pit' if pit else ''}.json"
        f = bt_dir() / name
        if not f.exists() and pit:
            f = SHIPPED_DIR / name
        if f.exists():
            try:
                out[strat] = json.loads(f.read_text())
            except ValueError:
                pass
    return out


def variants_tried() -> dict:
    f = bt_dir() / "runs.csv"
    if not f.exists():
        return {}
    out = {}
    with open(f, newline="") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["strategy"], set()).add(r["params_hash"])
    return {k: len(v) for k, v in out.items()}


def summary_text(res: dict) -> str:
    s, m, b, u = res["stats"], res["metrics"], res["benchmark_spy"], res["benchmark_universe"]
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"
    L = [f"{res['strategy']}  [{res.get('universe_mode', 'fixed_today')}"
         f"{' + dividends' if res.get('total_return') else ''}"
         f"{' + T-bill cash, excess Sharpe' if res.get('cash_yield') else ''}"
         f"{', data coverage ' + pct(res.get('pit_coverage')) if res.get('pit_coverage') else ''}]"
         f"  {res['start']} → {res['end']}  ({res['sessions']} sessions, "
         f"{res['universe_size']} symbols, params {res['params_hash']})",
         f"  trades {s['n']} | win {pct(s.get('win_rate'))} | expectancy ${s.get('expectancy')} "
         f"± {s.get('se')} | conf {pct(s.get('confidence'))} | PF {s.get('pf')} | "
         f"avg hold {res['avg_hold']} sessions",
         f"  CAGR {pct(m.get('cagr'))} | maxDD {pct(m.get('max_dd_pct'))} | Sharpe {m.get('sharpe')} | "
         f"avg exposure {pct(m.get('avg_exposure'))}",
         f"  SPY buy&hold: CAGR {pct(b.get('cagr'))} maxDD {pct(b.get('max_dd_pct'))} Sharpe {b.get('sharpe')}",
         f"  universe buy&hold: CAGR {pct(u.get('cagr'))} maxDD {pct(u.get('max_dd_pct'))} Sharpe {u.get('sharpe')}",
         f"  in-sample n={res['in_sample']['n']} PF {res['in_sample'].get('pf')} | out-of-sample "
         f"(from {res['oos_from']}) n={res['out_of_sample']['n']} PF {res['out_of_sample'].get('pf')} "
         f"exp ${res['out_of_sample'].get('expectancy')}",
         "  by year: " + ", ".join(f"{y} n={v['n']} ${v['pnl']:,.0f}" for y, v in sorted(res['by_year'].items())),
         f"  exits {res['exit_reasons']} | CAGR on exposure {pct(res['metrics'].get('cagr_on_exposure'))}"
         f" | cash interest ${res.get('interest', 0):,.0f}"
         f"{' | peak exposure ' + pct(res.get('max_exposure')) if res.get('max_exposure') is not None else ''}",
         "  stress: " + "; ".join(f"{k}: {pct(v['strategy_pct'])} (DD {pct(v['strategy_dd'])}) vs hold {pct(v['hold_pct'])}"
                                   for k, v in (res.get('stress') or {}).items()),
         f"  VERDICT: {res['verdict']['label']}"]
    for c in res["verdict"]["checks"]:
        L.append(f"    [{'✓' if c['ok'] else '✗'}] {c['name']}: {c['detail']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest the stocks sandbox rules")
    ap.add_argument("--strategy", choices=list(se.STRATEGIES) + list(BT_ONLY))
    ap.add_argument("--cash-yield", action="store_true",
                    help="pay T-bill interest on idle cash; Sharpe on excess returns")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--start")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--total-return", action="store_true",
                    help="dividend-adjusted prices for strategies AND benchmarks (Yahoo)")
    ap.add_argument("--pit", action="store_true",
                    help="point-in-time S&P 500 universe (survivorship control; ~750 "
                         "symbols to download, several minutes per stock strategy)")
    a = ap.parse_args(argv)
    cfg = se.load_config()
    members = None
    syms = se.universe(cfg)
    if a.pit:
        snaps = load_pit()
        members = members_fn(snaps)
        syms = sorted(set(syms) | pit_tickers(snaps, ""))
    bars = load_history(syms, years=a.years, total_return=a.total_return)
    if "SPY" not in bars:
        print("no SPY history — cannot build the calendar", flush=True)
        return 1
    # first tradable day: one WINDOW of warm-up after the start of history
    start = a.start or bars["SPY"][min(WINDOW, len(bars["SPY"]) - 1)]["date"]
    rf = load_rates(a.years) if a.cash_yield else None
    for strat in ([a.strategy] if a.strategy else se.STRATEGIES):
        t0 = time.time()
        if a.pit and strat in se.ETF_STRATEGIES:
            continue                       # ETF lanes have no stock-survivorship issue
        res = run(cfg, bars, strat, start, a.end, members=members,
                  total_return=a.total_return, rf=rf)
        save(res)
        print(summary_text(res), flush=True)
        print(f"  ({time.time() - t0:.0f}s)\n", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
