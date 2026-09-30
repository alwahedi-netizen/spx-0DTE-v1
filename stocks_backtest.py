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

def load_history(symbols: list, years: int = 10, max_age_h: float = 20) -> dict:
    """{sym: bars} — long daily history, cached per symbol (git-ignored)."""
    import stocks_data as sd
    cache = Path(st.DATA_DIR) / "history"
    os.makedirs(cache, exist_ok=True)
    out = {}
    for s in symbols:
        f = cache / f"{s}.json"
        if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
            out[s] = json.loads(f.read_text())
            continue
        try:
            bars = sd.long_bars(s, years)
        except sd.StocksDataError as e:
            print(f"history: {e}", flush=True)
            if f.exists():
                out[s] = json.loads(f.read_text())
            continue
        f.write_text(json.dumps(bars))
        out[s] = bars
    return out


# ── simulation ───────────────────────────────────────────────────────────────

def _pos(pid, strat, sym, tier, d, qty, entry, stop, tgt, risk, fill):
    return {"position_id": pid, "strategy": strat, "symbol": sym, "side": "LONG",
            "tier": tier, "entry_ts": d, "qty": qty, "entry_px_theo": entry,
            "stop_px_initial": stop, "target_px": tgt, "risk_usd": risk,
            "stop_px": stop, "peak_px": entry, "phase": "1", "split_factor": 1,
            "entry_px_actual": fill, "entry_i": None}


def simulate(cfg: dict, bars: dict, strategy: str, start: str, end: str) -> dict:
    """Replay one strategy in isolation over [start, end]. Pure: no I/O."""
    key = strategy.lower()
    c = cfg[key]
    group = cfg["universe"]["etfs"] if strategy == "RSI2" else cfg["universe"]["stocks"]
    group = [s for s in group if s in bars]
    cal = [b["date"] for b in bars["SPY"] if start <= b["date"] <= end]
    idx = {s: {b["date"]: i for i, b in enumerate(bars[s])} for s in group}
    cand_fn = {"MOM": se.mom_candidates, "PB90": se.pb90_candidates,
               "RSI2": se.rsi2_candidates}[strategy]
    eq0 = float(cfg["account_equity"])
    opens, trades, curve = [], [], []
    realized = 0.0
    last_close = {}

    def today_bar(s, d):
        i = idx[s].get(d)
        return bars[s][i] if i is not None else None

    for di, d in enumerate(cal):
        # features from bars strictly before d (what the premarket step sees)
        feats_in = {}
        for s in group:
            i = idx[s].get(d)
            if i is None or i < 30:
                continue
            feats_in[s] = bars[s][max(0, i - WINDOW):i]
        fe = se.universe_features(feats_in, list(feats_in))
        q_open = {s: b["open"] for s in group if (b := today_bar(s, d))}
        new_risk = 0.0

        def book(ref):
            heat = sum(se.open_risk(p, ref.get(p["symbol"], se.avg_cost(p))) for p in opens)
            notional = sum(se.eff_qty(p) * ref.get(p["symbol"], se.avg_cost(p)) for p in opens)
            return heat, notional

        # 1. adds (MOM double-down) then entries, at the open
        if strategy == "MOM":
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
        for sym in cand_fn(fe, c):
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
            qty, risk, why = se.size_position(last, stop, cfg, heat, new_risk, notional)
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
                                   b["close"], d, cfg, held=di - p["entry_i"])
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

def curve_metrics(curve: list, eq0: float) -> dict:
    if len(curve) < 2:
        return {}
    eqs = [c["equity"] for c in curve]
    rets = [eqs[i] / eqs[i - 1] - 1 for i in range(1, len(eqs)) if eqs[i - 1] > 0]
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
            "avg_exposure": round(sum(c.get("exposure", 1) for c in curve) / len(curve), 3)}


def benchmark(bars: dict, symbols: list, cal: list, eq0: float) -> dict:
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
    return curve_metrics(curve, eq0)


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


def run(cfg: dict, bars: dict, strategy: str, start: str, end: str) -> dict:
    eq0 = float(cfg["account_equity"])
    sim = simulate(cfg, bars, strategy, start, end)
    cal = [c["date"] for c in sim["curve"]]
    trades = sim["trades"]
    split = cal[int(len(cal) * IS_FRACTION)] if cal else end
    group = cfg["universe"]["etfs"] if strategy == "RSI2" else cfg["universe"]["stocks"]
    res = {
        "strategy": strategy, "start": cal[0] if cal else start, "end": cal[-1] if cal else end,
        "sessions": len(cal), "params_hash": params_hash(cfg, strategy),
        "params": cfg[strategy.lower()], "ran_at": datetime.now().isoformat(timespec="seconds"),
        "stats": sr.stats([t["pnl"] for t in trades]),
        "in_sample": sr.stats([t["pnl"] for t in trades if t["exit"] < split]),
        "out_of_sample": sr.stats([t["pnl"] for t in trades if t["exit"] >= split]),
        "oos_from": split,
        "metrics": curve_metrics(sim["curve"], eq0),
        "benchmark_spy": benchmark(bars, ["SPY"], cal, eq0),
        "benchmark_universe": benchmark(bars, group, cal, eq0),
        "by_year": by_year(trades),
        "exit_reasons": {r: sum(1 for t in trades if t["reason"] == r)
                         for r in sorted({t["reason"] for t in trades})},
        "avg_hold": round(sum(t["held"] for t in trades) / len(trades), 1) if trades else None,
        "open_at_end": sim["open_at_end"],
        "curve": sim["curve"][::5],                       # weekly-ish, for the chart
        "trades_tail": trades[-40:],
        "universe_size": len([s for s in group if s in bars]),
    }
    gate = dict(GATE_DEFAULTS, **(cfg.get("backtest_gate") or {}))
    res["gate"] = gate
    res["verdict"] = verdict(res, gate, eq0)
    return res


def save(res: dict):
    d = bt_dir()
    os.makedirs(d, exist_ok=True)
    (d / f"latest_{res['strategy']}.json").write_text(json.dumps(res))
    path = d / "runs.csv"
    cols = ["ran_at", "strategy", "params_hash", "start", "end", "trades", "expectancy",
            "pf", "confidence", "max_dd_pct", "sharpe", "bench_sharpe", "verdict"]
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        s = res["stats"]
        w.writerow({"ran_at": res["ran_at"], "strategy": res["strategy"],
                    "params_hash": res["params_hash"], "start": res["start"], "end": res["end"],
                    "trades": s["n"], "expectancy": s.get("expectancy"), "pf": s.get("pf"),
                    "confidence": s.get("confidence"), "max_dd_pct": res["metrics"].get("max_dd_pct"),
                    "sharpe": res["metrics"].get("sharpe"),
                    "bench_sharpe": res["benchmark_universe"].get("sharpe"),
                    "verdict": "PASS" if res["verdict"]["pass"] else "FAIL"})


def load_latest() -> dict:
    out = {}
    for strat in se.STRATEGIES:
        f = bt_dir() / f"latest_{strat}.json"
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
    L = [f"{res['strategy']}  {res['start']} → {res['end']}  ({res['sessions']} sessions, "
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
         f"  exits {res['exit_reasons']}",
         f"  VERDICT: {res['verdict']['label']}"]
    for c in res["verdict"]["checks"]:
        L.append(f"    [{'✓' if c['ok'] else '✗'}] {c['name']}: {c['detail']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest the stocks sandbox rules")
    ap.add_argument("--strategy", choices=list(se.STRATEGIES))
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--start")
    ap.add_argument("--end", default=date.today().isoformat())
    a = ap.parse_args(argv)
    cfg = se.load_config()
    bars = load_history(se.universe(cfg), years=a.years)
    if "SPY" not in bars:
        print("no SPY history — cannot build the calendar", flush=True)
        return 1
    # first tradable day: one WINDOW of warm-up after the start of history
    start = a.start or bars["SPY"][min(WINDOW, len(bars["SPY"]) - 1)]["date"]
    for strat in ([a.strategy] if a.strategy else se.STRATEGIES):
        t0 = time.time()
        res = run(cfg, bars, strat, start, a.end)
        save(res)
        print(summary_text(res), flush=True)
        print(f"  ({time.time() - t0:.0f}s)\n", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
