"""
tests_stocks.py  —  Logicon Capital  ·  Stocks & ETF sandbox tests
==================================================================
Deploy gate (auto-update-paper.sh runs it next to tests_paper.py). Offline:
fixture bars, a fake data adapter and a fake clock — no Schwab, no Yahoo.

Two layers, per SANDBOX_PLAYBOOK §3 Phase 2:
  * truth tables on every pure function (indicators, candidates, sizing,
    ticks/fills/fees, split-aware campaign math, exits, store rails);
  * fake-clock multi-day sessions: a whole session in milliseconds,
    INCLUDING a mid-day crash + restart, asserting no duplicated or lost
    entry slots, campaigns, exits, marks or eod rows.
"""

import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import random

import stocks_backtest as bt
import stocks_engine as se
import stocks_report as sr
import stocks_store as st

PASS = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")


def fresh_store():
    st.DATA_DIR = Path(tempfile.mkdtemp(prefix="stocks_test_"))


def approx(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


def base_cfg(**over):
    cfg = se.load_config(path="/nonexistent")          # pure DEFAULTS
    cfg["universe"] = {"stocks": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF",
                                  "GGG", "HHH", "III", "JJJ"],
                       "etfs": ["SPY", "QQQ", "XLE"]}
    for k in ("mom", "pb90", "rsi2"):
        cfg[k] = dict(cfg[k], stage="paper")
    cfg.update(over)
    return cfg


# ── indicators ───────────────────────────────────────────────────────────────
def test_indicators():
    print("Indicators")
    assert se.sma([1, 2, 3, 4], 2) == 3.5 and se.sma([1], 2) is None
    ok("SMA over the last n; None when short")
    bars = [{"high": 11, "low": 9, "close": 10}] * 3 + [{"high": 14, "low": 10, "close": 13}]
    # TRs: 2, 2, max(4, 4, 0)=4 -> ATR(3) = 8/3
    assert approx(se.atr(bars, 3), 8 / 3)
    ok("ATR uses true range incl. gaps vs prior close")
    assert se.rsi([1, 2, 3, 4, 5], 2) == 100.0
    assert se.rsi([5, 4, 3, 2, 1], 2) == 0.0
    r = se.rsi([10, 11, 10, 11, 10], 2)
    assert 0 < r < 50, r
    ok("RSI(2): all-up 100, all-down 0, ends-down < 50 (Wilder)")
    assert approx(se.ret_pct([100, 110], 1), 10.0) and se.ret_pct([1], 3) is None
    assert se.pct_rank([1, 2, 3, 4], 4) == 100.0 and se.pct_rank([1, 2, 3, 4], 1) == 25.0
    ok("returns in %; percentile rank 100 = highest")


def trading_days_back(end: date, n: int) -> list:
    out, cur = [], end
    while len(out) < n:
        if se.is_trading_day(cur):
            out.append(cur.isoformat())
        cur -= timedelta(days=1)
    return list(reversed(out))


def mk_bars(closes, end: date):
    days = trading_days_back(end, len(closes))
    return [{"date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c}
            for d, c in zip(days, closes)]


def test_calendar_and_regime():
    print("Calendar / regime")
    assert not se.is_trading_day(date(2026, 11, 26))       # Thanksgiving
    assert not se.is_trading_day(date(2026, 10, 3))        # Saturday
    assert se.session_times(date(2026, 11, 27))["mark"] == "13:10"
    assert se.session_times(date(2026, 10, 5))["mark"] == "16:10"
    ok("NYSE holidays + half-day session times")
    assert se.sessions_between("2026-10-02", "2026-10-05") == 1    # Fri -> Mon
    assert se.sessions_between("2026-11-25", "2026-11-27") == 1    # skips Thanksgiving
    ok("session counting skips weekends and holidays")
    # 12 flat months at 100, the last completed month at 200
    bars = []
    for m in range(1, 13):
        for dd in (5, 20):
            bars.append({"date": f"2025-{m:02d}-{dd:02d}", "close": 100.0,
                         "high": 100, "low": 100})
    bars.append({"date": "2026-01-30", "close": 200.0, "high": 200, "low": 200})
    # last bar is Fri 2026-01-30; next session is Feb 2 -> January is complete
    assert approx(se.spy_sma10m(bars), (9 * 100 + 200) / 10)
    bars.append({"date": "2026-02-03", "close": 300.0, "high": 300, "low": 300})
    assert approx(se.spy_sma10m(bars), (9 * 100 + 200) / 10)   # Feb still running
    ok("10-month SMA uses completed month-end closes only")


# ── strategies ───────────────────────────────────────────────────────────────
def universe_fixture(end: date) -> dict:
    """10 stocks + 3 ETFs, 260 bars. AAA/BBB = strongest steady uptrends
    (MOM), CCC = strong trend with a 6% pullback that has turned up (PB90),
    SPY = uptrend with a 3-day dip (RSI2), XLE = downtrend (never RSI2)."""
    n = 260
    b = {}
    for i, s in enumerate(["DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]):
        b[s] = [50 * (1 + 0.0002 * (i - 3)) ** k for k in range(n)]
    b["AAA"] = [50 * 1.004 ** k for k in range(n)]
    b["BBB"] = [50 * 1.0035 ** k for k in range(n)]
    c = [50 * 1.0038 ** k for k in range(n - 8)]
    top = c[-1]
    c += [top * 0.98, top * 0.96, top * 0.94, top * 0.92, top * 0.90,
          top * 0.915, top * 0.925, top * 0.94]
    b["CCC"] = c
    spy = [400 * 1.001 ** k for k in range(n - 3)]
    spy += [spy[-1] * 0.99, spy[-1] * 0.98, spy[-1] * 0.97]
    b["SPY"] = spy
    b["QQQ"] = [300 * 1.0005 ** k for k in range(n)]
    b["XLE"] = [90 * 0.999 ** k for k in range(n)]
    return {s: mk_bars(v, end) for s, v in b.items()}


def test_candidates():
    print("Strategy candidates")
    cfg = base_cfg()
    bars = universe_fixture(date(2026, 10, 2))
    fe = se.build_features(cfg, bars)
    mom = se.mom_candidates(fe["stocks"], cfg["mom"])
    assert mom[:2] == ["AAA", "BBB"] or set(mom) <= {"AAA", "BBB", "CCC"}, mom
    assert "AAA" in mom and "DDD" not in mom
    ok(f"MOM: top-decile EXPL in a stacked uptrend → {mom}")
    pb = se.pb90_candidates(fe["stocks"], cfg["pb90"])
    assert pb == ["CCC"], pb
    ok("PB90: 2–12% under the 63d high, bounce started, elite trend → CCC only")
    r2 = se.rsi2_candidates(fe["etfs"], cfg["rsi2"])
    assert r2 == ["SPY"], r2
    ok("RSI2: above SMA200 and RSI(2) < 10 → SPY; downtrend XLE excluded")
    f = fe["stocks"]["CCC"]
    assert se.initial_stop("MOM", 100.0, f, cfg) == 85.0
    assert approx(se.initial_stop("PB90", 100.0, f, cfg), round(100 - 2 * f["atr20"], 2))
    assert se.initial_target("PB90", 100.0, {"hi63": 110.0}) == 110.0
    assert se.initial_target("PB90", 100.0, {"hi63": 100.2}) is None
    ok("stops: MOM −15%, PB90 2×ATR; PB90 target = 63d-high retest")


def test_new_candidates():
    print("Candidate lanes (MOMR / BRK55 / HI52 / QBO / SECROT)")
    cfg = base_cfg()
    F = lambda **k: dict({"close": 100.0, "sma50": 90.0, "sma200": 80.0, "r63": 20.0,
                          "expl_rank": 95.0, "r63_rank": 95.0, "hi55": 100.0,
                          "hi252": 101.0, "box_hi": 98.0, "box_rng": 6.0, "sma10": 97.0,
                          "sma20": 95.0, "r3d": 1.0, "r126": 10.0}, **k)
    on = {"spy": {"close": 500, "sma200": 450}, "breadth": 60}
    assert se.regime_ok(on)
    assert not se.regime_ok({**on, "breadth": 40})
    assert not se.regime_ok({**on, "spy": {"close": 400, "sma200": 450}})
    feats = {"A": F()}
    assert se.momr_candidates(feats, cfg["momr"], on) == se.mom_candidates(feats, cfg["mom"]) == ["A"]
    assert se.momr_candidates(feats, cfg["momr"], {**on, "breadth": 30}) == []
    ok("MOMR = MOM entries only when SPY > SMA200 and breadth ≥ 50%")
    assert se.brk55_candidates({"A": F(), "B": F(close=99.0), "C": F(sma200=120.0)},
                               cfg["brk55"]) == ["A"]
    ok("BRK55: close at the 55-day high and above SMA200")
    assert se.hi52_candidates({"A": F(), "B": F(close=97.0), "C": F(expl_rank=70.0)},
                              cfg["hi52"]) == ["A"]
    ok("HI52: within 2% of the 52-week high, EXPL ≥ 80, stacked trend")
    q = {"A": F(r63=40.0), "B": F(r63=40.0, box_rng=15.0), "C": F(r63=10.0),
         "D": F(r63=40.0, close=97.5)}
    assert se.qbo_candidates(q, cfg["qbo"]) == ["A"]
    ok("QBO: +25% 3-month mover breaking out of a ≤10% box on rising short MAs")
    etf = {"SPY": F(r63=5.0, r126=5.0), "QQQ": F(r63=9.0, r126=9.0), "XLE": F(r63=-3.0, r126=-3.0),
           "GLD": F(r63=7.0, r126=7.0), "TLT": F(r63=8.0, r126=8.0, sma200=120.0)}
    assert se.secrot_top(etf, cfg["secrot"]) == ["QQQ", "GLD", "SPY"]
    assert se.secrot_candidates(etf, cfg["secrot"], {"som": 2}) == ["QQQ", "GLD", "SPY"]
    assert se.secrot_candidates(etf, cfg["secrot"], {"som": 5}) == []
    ok("SECROT: top 3 by 3m+6m momentum, positive and above SMA200; month-start only")
    assert se.session_of_month("2026-10-01") == 1 and se.session_of_month("2026-09-08") == 5
    assert se.session_of_month("2026-10-05") == 3
    ok("session-of-month counts NYSE sessions (Labor Day skipped)")

    P = lambda st_, **k: pos(strategy=st_, **k)
    d = "2026-10-20"
    assert se.rule_exit(P("BRK55"), {"lo20": 95.0}, 94.0, d, cfg, held=3) == "TRAIL"
    assert se.rule_exit(P("BRK55"), {"lo20": 95.0}, 96.0, d, cfg, held=3) is None
    assert se.rule_exit(P("HI52"), {"sma50": 95.0}, 94.0, d, cfg, held=3) == "TREND"
    assert se.rule_exit(P("QBO"), {"sma10": 95.0}, 94.0, d, cfg, held=0) is None
    assert se.rule_exit(P("QBO"), {"sma10": 95.0}, 94.0, d, cfg, held=2) == "TRAIL"
    assert se.rule_exit(P("QBO"), {"sma10": 95.0}, 99.0, d, cfg, held=40) == "TIME"
    r = P("SECROT", symbol="XLE")
    assert se.rule_exit(r, {}, 50.0, d, cfg, held=20, ctx={"som": 1, "etfs": etf}) == "ROTATE"
    assert se.rule_exit(r, {}, 50.0, d, cfg, held=20, ctx={"som": 2, "etfs": etf}) is None
    assert se.rule_exit(P("SECROT", symbol="QQQ"), {}, 50.0, d, cfg, held=20,
                        ctx={"som": 1, "etfs": etf}) is None
    ok("exits: BRK55 20-day low, HI52 < SMA50, QBO < SMA10 / 40 sessions, SECROT rotates out month-start")
    assert se.initial_stop("HI52", 100.0, {}, cfg) == 88.0
    assert se.initial_stop("MOMR", 100.0, {}, cfg) == 85.0
    assert se.initial_stop("QBO", 100.0, {"atr20": 2.0}, cfg) == 97.0
    assert se.trail_stop(P("MOMR", phase="2"), 130.0, cfg) == 110.5
    ok("stops: HI52 −12%, MOMR −15% + phase-2 trail, QBO 1.5×ATR")


def test_rotation_lanes():
    print("Rotation lanes (LOWVOL / MOM12 / LVMOM / ETFTREND) + RSI2S")
    cfg = base_cfg()
    F = lambda **k: dict({"close": 100.0, "sma200": 90.0, "r126": 5.0,
                          "vol252": 25.0, "r12_1": 10.0}, **k)
    feats = {"A": F(vol252=15.0, r12_1=5.0), "B": F(vol252=30.0, r12_1=40.0),
             "C": F(vol252=20.0, r12_1=45.0), "D": F(vol252=45.0, r12_1=-10.0)}
    c = dict(cfg["lowvol"], top_n=2, hold_rank=3)
    assert [s_ for s_, _ in se.rotation_scores(feats, "LOWVOL", c)] == ["A", "C", "B", "D"]
    assert [s_ for s_, _ in se.rotation_scores(feats, "MOM12", c)] == ["C", "B", "A", "D"]
    assert [s_ for s_, _ in se.rotation_scores(feats, "LVMOM", c)][:1] == ["C"]
    ok("scores: LOWVOL calmest first, MOM12 strongest 12-1, LVMOM best blend (C)")
    fn = se.CANDIDATES["LOWVOL"]
    assert fn(feats, c, {"som": 1}) == ["A", "C"] and fn(feats, c, {"som": 4}) == []
    ok("entries only in the month's first sessions, top_n names")
    m = dict(cfg["mom12"], top_n=2, hold_rank=3)
    down = {"som": 1, "spy": {"close": 400, "sma200": 450}, "stocks": feats}
    up = {**down, "spy": {"close": 500, "sma200": 450}}
    assert se.CANDIDATES["MOM12"](feats, m, down) == [] and se.CANDIDATES["MOM12"](feats, m, up) == ["C", "B"]
    ok("MOM12 buys nothing when SPY is below its 200-day average")
    cfg2 = dict(cfg, lowvol=c, mom12=m)
    P = lambda st_, sym: pos(strategy=st_, symbol=sym)
    ctx = {"som": 1, "stocks": feats}
    assert se.rule_exit(P("LOWVOL", "B"), {}, 100, "2026-10-01", cfg2, held=20, ctx=ctx) is None
    assert se.rule_exit(P("LOWVOL", "D"), {}, 100, "2026-10-01", cfg2, held=20, ctx=ctx) == "ROTATE"
    assert se.rule_exit(P("LOWVOL", "D"), {}, 100, "2026-10-02", cfg2, held=20,
                        ctx={**ctx, "som": 2}) is None
    assert se.rule_exit(P("MOM12", "C"), {}, 100, "2026-10-01", cfg2, held=20, ctx=down) == "REGIME"
    ok("month-start exits: rank beyond hold_rank rotates out (buffer keeps #3); regime-off sells all")
    q, r, why = se.size_for("LOWVOL", 50.0, 35.0, cfg2, 1e9, 1e9, 0)
    assert why == "" and q == int(100000 * 0.98 / 2 // 50.0)
    assert se.size_for("LOWVOL", 50.0, 35.0, cfg2, 0, 0, 99000)[2] == "CASH"
    ok("rotation sizing: equal-weight slots, only cash-limited (heat/budget don't apply)")
    e = {"SPY": F(r126=8.0), "XLE": F(close=80.0), "GLD": F(r126=12.0)}
    assert se.CANDIDATES["ETFTREND"](e, cfg["etftrend"], {"som": 2}) == ["GLD", "SPY"]
    assert se.family("RSI2S") == "RSI2" and se.initial_stop("RSI2S", 100.0, {"atr20": 2.0}, cfg) == 94.0
    assert se.rule_exit(pos(strategy="RSI2S"), {"last4": [100] * 4}, 101.0, "2026-10-06", cfg) == "RULE"
    ok("ETFTREND holds every ETF above its SMA200; RSI2S = RSI2 mechanics on stocks")


def test_market_effect_lanes():
    print("Market-effect lanes (TOM / IBS)")
    cfg = base_cfg()
    assert se.group_of("TOM", cfg) == ["SPY", "QQQ", "IWM", "DIA"]
    assert se.is_month_end_session("2026-09-30") and not se.is_month_end_session("2026-09-29")
    assert se.is_month_end_session("2026-07-31")          # a Friday
    assert not se.is_month_end_session("2026-12-30") and se.is_month_end_session("2026-12-31")
    ok("month-end session detection (weekends/holidays aware)")
    feats = {"SPY": {}, "QQQ": {}}
    assert se.tom_candidates(feats, cfg["tom"], {"eom": True}) == ["QQQ", "SPY"]
    assert se.tom_candidates(feats, cfg["tom"], {"eom": False}) == []
    P = pos(strategy="TOM", symbol="SPY")
    assert se.rule_exit(P, {}, 100, "2026-10-05", cfg, held=3, ctx={"som": 3}) == "CALENDAR"
    assert se.rule_exit(P, {}, 100, "2026-10-02", cfg, held=2, ctx={"som": 2}) is None
    ok("TOM: buy all four on the month's last session, sell at the 3rd session's close")
    F = lambda **k: dict({"close": 100.0, "sma200": 90.0, "ibs": 0.1, "hi1": 101.0}, **k)
    f3 = {"SPY": F(ibs=0.15), "QQQ": F(ibs=0.05), "IWM": F(ibs=0.5), "DIA": F(sma200=110.0)}
    assert se.ibs_candidates(f3, cfg["ibs"]) == ["QQQ", "SPY"]
    I = pos(strategy="IBS", symbol="SPY")
    assert se.rule_exit(I, {"hi1": 101.0}, 101.5, "2026-10-06", cfg, held=1) == "RULE"
    assert se.rule_exit(I, {"hi1": 101.0}, 100.5, "2026-10-06", cfg, held=1) is None
    assert se.rule_exit(I, {"hi1": 101.0}, 100.5, "2026-10-12", cfg, held=5) == "TIME"
    ok("IBS: bottom-20% close in an uptrend; exit above yesterday's high or after 5 sessions")
    b = mk_bars([100.0, 101.0], date(2026, 9, 29))
    b[-1].update(high=104.0, low=100.0, close=101.0)
    assert approx(se.features(b * 20)["ibs"], 0.25)
    ok("IBS feature = (close − low) / (high − low) of the last bar")


def test_weighted_lanes():
    print("Weighted lanes (vol target / risk parity)")
    cfg = base_cfg()
    F = lambda **k: dict({"close": 100.0, "sma200": 90.0, "vol21": 15.0, "vol63": 20.0}, **k)
    w = se.lane_weights("VTSPY", {"SPY": F(vol21=30.0)}, cfg["vtspy"])
    assert approx(w["SPY"], 0.5)
    assert approx(se.lane_weights("VTSPY", {"SPY": F(vol21=10.0)}, cfg["vtspy"])["SPY"], 1.0)
    ok("vol target: 30% realized vol → half size; calm markets capped at 100% (no leverage)")
    w4 = se.lane_weights("VT4", {s_: F(vol21=15.0) for s_ in ("SPY", "QQQ", "IWM", "DIA")}, cfg["vt4"])
    assert all(approx(v, 0.25) for v in w4.values())
    ok("VT4: four quarter-slots, each vol-targeted")
    rp = se.lane_weights("RPAR", {"SPY": F(vol63=20.0), "TLT": F(vol63=10.0), "GLD": F(vol63=20.0)},
                         cfg["rpar"])
    assert approx(rp["TLT"], 0.5) and approx(rp["SPY"], 0.25) and approx(sum(rp.values()), 1.0)
    ok("risk parity: weight ∝ 1/vol, fully invested")
    f5 = {s_: F(vol63=20.0) for s_ in ("SPY", "EFA", "EEM", "TLT", "GLD")}
    f5["EEM"] = F(vol63=20.0, close=80.0)                       # below SMA200
    rt = se.lane_weights("RPTREND", f5, cfg["rptrend"])
    assert "EEM" not in rt and approx(sum(rt.values()), 0.8)
    ok("trend filter: an asset below SMA200 drops out and its share stays in cash")
    q, _, why = se.size_for("RPAR", 50.0, 35.0, cfg, 0, 0, 0, weight=0.5)
    assert why == "" and q == int(100000 * 0.98 * 0.5 // 50.0)
    P = pos(strategy="RPAR", symbol="TLT")
    assert se.rule_exit(P, {}, 100, "2026-09-30", cfg, held=20, ctx={"eom": True}) == "REBAL"
    assert se.rule_exit(P, {}, 100, "2026-09-29", cfg, held=20, ctx={"eom": False}) is None
    ok("sized by weight; sold at the month's last close, re-bought next open")


def test_round7_lanes():
    print("Round 7 lanes (TSMOM / GAPFADE / OVN) + strict bar")
    cfg = base_cfg()
    c = dict(cfg["tsmom"], symbols=["A", "B", "C", "D"])
    F = lambda **k: dict({"close": 100.0, "sma200": 90.0, "vol63": 15.0, "r252": 10.0}, **k)
    w = se.lane_weights("TSMOM", {"A": F(), "B": F(vol63=30.0), "C": F(r252=-5.0), "D": F()}, c)
    assert approx(w["A"], 0.25) and approx(w["B"], 0.125) and "C" not in w
    ok("TSMOM: long only while 12m return > 0, each quarter-slot vol-scaled")
    g = {"SPY": F(), "QQQ": F(), "IWM": F(sma200=120.0)}
    ctx = {"open": {"SPY": 99.0, "QQQ": 99.5, "IWM": 98.0}}
    assert se.gapfade_candidates(g, cfg["gapfade"], ctx) == ["SPY"]
    assert se.gapfade_candidates(g, cfg["gapfade"], {}) == []
    assert se.rule_exit(pos(strategy="GAPFADE"), {}, 100, "2026-10-01", cfg, held=0) == "EOD"
    ok("GAPFADE: ≥0.75% gap-down open in an uptrend; always flat by the close")
    days = trading_days_back(date(2026, 9, 29), 3)
    bars = {"SPY": [{"date": d, "open": o, "high": 200, "low": 1, "close": cl}
                    for d, o, cl in zip(days, (100, 102, 101), (101, 100, 103))],
            "QQQ": [{"date": d, "open": 50, "high": 99, "low": 1, "close": 50} for d in days]}
    r = bt.simulate_overnight(dict(cfg, ovn=dict(cfg["ovn"], symbols=["SPY"])), bars, "OVN",
                              days[0], days[-1])
    q = int(100000 * 0.98 // 101)
    t1 = r["trades"][0]
    assert t1["entry"] == days[0] and t1["exit"] == days[1] and t1["qty"] == q
    assert approx(t1["pnl"], round((se.sim_sell(102, 2) - se.sim_buy(101, 2)) * q
                                   - se.sell_fees(se.sim_sell(102, 2), q, cfg), 2))
    ok("OVN: bought at the close, sold at the next open, slippage + fees charged")
    gate = dict(bt.GATE_DEFAULTS, min_confidence=0.99)
    good = {"stats": {"n": 80, "expectancy": 50, "confidence": 0.995, "pf": 1.5},
            "in_sample": {}, "out_of_sample": {"expectancy": 10, "pf": 1.2},
            "metrics": {"max_dd_pct": -0.10, "sharpe": 1.1}, "benchmark_universe": {"sharpe": 0.9},
            "strict": True, "oos_metrics": {"sharpe": 1.0}, "oos_benchmark": {"sharpe": 0.8}}
    assert bt.verdict(good, gate, 1e5)["pass"]
    assert not bt.verdict({**good, "oos_metrics": {"sharpe": 0.7}}, gate, 1e5)["pass"]
    assert not bt.verdict({**good, "stats": {**good["stats"], "confidence": 0.98}}, gate, 1e5)["pass"]
    ok("strict bar: 99% confidence and beating hold in the held-out window are both required")


def test_asian_methods():
    print("Asian methods (Ichimoku / Heikin-Ashi / engulfing / KDJ / MA alignment / Supertrend)")
    up = mk_bars([100 * 1.004 ** k for k in range(120)], date(2026, 9, 29))
    f = se.features(up, extra=True)
    assert f["ichi_ok"] and f["kijun"] < up[-1]["close"]
    assert f["maal"] and f["st_up"]
    ok("steady uptrend: above the Ichimoku cloud, MAs stacked, Supertrend up")
    dn = mk_bars([100 * 0.996 ** k for k in range(120)], date(2026, 9, 29))
    fd = se.features(dn, extra=True)
    assert not fd["ichi_ok"] and not fd["st_up"] and fd["kdj_j"] < 20
    ok("steady downtrend: below the cloud, Supertrend down, KDJ J deeply oversold")
    b = mk_bars([100.0] * 30, date(2026, 9, 29))
    for x in b[-12:-2]:
        x.update(open=100, high=101, low=99, close=100)
    b[-2].update(open=100, high=100.5, low=97, close=98)      # red day
    b[-1].update(open=97.5, high=101, low=96, close=100.5)    # engulfs it at a new 10-day low
    assert se.features(b, extra=True)["engulf"]
    b[-1].update(low=98.5)
    assert not se.features(b, extra=True)["engulf"]           # not at the 10-day low
    ok("bullish engulfing only counts at a 10-day low")
    flip = mk_bars([100 * 0.99 ** k for k in range(40)] + [67 * 1.03 ** k for k in range(1, 6)],
                   date(2026, 9, 29))
    for x in flip:
        x.update(open=x["close"] / (1.01 if x is flip[-1] else 0.995))
    ha = se.features(flip[:-5], extra=True)
    assert ha["ha_bear"]
    ok("Heikin-Ashi reads a falling market as bearish")
    cfg = base_cfg()
    assert se.family("STA") == "ST" and se.group_of("ICHIA", cfg)[0] == "FXI"
    P = lambda st_: pos(strategy=st_, symbol="SPY")
    assert se.rule_exit(P("ICHI"), {"kijun": 101.0}, 100.0, "2026-10-06", cfg, held=3) == "KIJUN"
    assert se.rule_exit(P("STA"), {"st_up": False}, 100.0, "2026-10-06", cfg, held=3) == "ST_FLIP"
    assert se.rule_exit(P("KDJA"), {"kdj_j": 105.0}, 100.0, "2026-10-06", cfg, held=3) == "RULE"
    assert se.rule_exit(P("MAAL"), {"sma20": 101.0}, 100.0, "2026-10-06", cfg, held=3) == "MA20"
    assert se.rule_exit(P("ENG"), {"hi1": 102.0}, 100.0, "2026-10-06", cfg, held=5) == "TIME"
    ok("exits: Kijun break, Supertrend flip, J > 100, MA20 break, engulf 5-day time stop")


def test_sizing_fills_fees():
    print("Sizing / ticks / fills / fees")
    cfg = base_cfg()
    q, r, why = se.size_position(100.0, 95.0, cfg, 0, 0, 0)
    assert (q, r, why) == (80, 400.0, ""), (q, r, why)       # 500/5=100 → notional cap 8000/100=80
    q, r, why = se.size_position(100.0, 85.0, cfg, 0, 0, 0)
    assert (q, r, why) == (33, 495.0, "")                    # 500/15 = 33
    ok("qty = risk unit / stop distance, capped at 8% notional")
    assert se.size_position(100.0, 100.0, cfg, 0, 0, 0)[2] == "QTY"
    assert se.size_position(9000.0, 10.0, cfg, 0, 0, 0)[2] == "QTY"   # 8000/9000 < 1 share
    assert se.size_position(100.0, 85.0, cfg, 0, 1800, 0)[2] == "BUDGET"
    assert se.size_position(100.0, 85.0, cfg, 7800, 0, 0)[2] == "HEAT"
    assert se.size_position(100.0, 85.0, cfg, 0, 0, 97000)[2] == "CASH"
    ok("skip reasons: QTY / BUDGET / HEAT / CASH")
    assert se.tick_up(10.001) == 10.01 and se.tick_down(10.009) == 10.0
    assert se.tick_up(10.00) == 10.0 and se.tick_up(0.12345) == 0.1235
    ok("penny grid ≥ $1, 0.0001 below; exact prices stay put")
    assert se.sim_buy(100.0, 5) == 100.05 and se.sim_sell(100.0, 5) == 99.95
    assert se.sim_buy(33.333, 2) == 33.34
    ok("sim fills pay slippage and round against us")
    assert se.sell_fees(100.0, 100, cfg) == round(10000 * 0.278e-4 + 0.0166, 2)
    assert se.sell_fees(100.0, 10 ** 6, cfg) == round(1e8 * 0.278e-4 + 8.30, 2)
    ok("sell fees: SEC bps + TAF with its cap")


def pos(**kw):
    p = {"position_id": "X", "strategy": "MOM", "symbol": "AAA", "tier": "large",
         "qty": "10", "entry_px_theo": "100", "entry_ts": "2026-10-05T09:45:00-04:00",
         "stop_px": "85", "peak_px": "100", "phase": "1", "split_factor": "1"}
    p.update(kw)
    return p


def test_campaign_math():
    print("Campaign math (adds, splits, exits)")
    cfg = base_cfg()
    p = pos()
    assert se.avg_cost(p) == 100.0 and se.eff_qty(p) == 10
    assert se.campaign_pnl(p, 110.0, cfg) == round(100 - se.sell_fees(110.0, 10, cfg), 2)
    ok("single-entry P&L = (exit − entry) × qty − sell fees")
    p2 = pos(add_qty="10", add_px_theo="120")
    assert se.avg_cost(p2) == 110.0 and se.eff_qty(p2) == 20
    ok("add → average cost over both buys")
    p3 = pos(split_factor="2", stop_px="42.5", peak_px="50")
    assert se.avg_cost(p3) == 50.0 and se.eff_qty(p3) == 20
    assert se.campaign_pnl(p3, 55.0, cfg) == round(100 - se.sell_fees(55.0, 20, cfg), 2)
    ok("2:1 split: theo stays immutable, P&L identical in today's terms")
    p4 = pos(entry_px_actual="100.05")
    assert approx(se.avg_cost(p4, actual=True), 100.05)
    ok("actual P&L uses actual fills when present")

    assert se.detect_split(200.0, 100.0) == 2 and se.detect_split(100.0, 99.0) is None
    assert se.detect_split(50.0, 150.0) == 1 / 3 and se.detect_split(303.0, 100.0) == 3
    ok("split detector: clean ratios within 3%, noise ignored")

    assert se.exit_check(pos(), 84.0) == ("STOPPED", 84.0)
    assert se.exit_check(pos(), 90.0) is None
    assert se.exit_check(pos(target_px="110"), 111.0) == ("TARGET", 110.0)
    assert se.exit_check(pos(target_px="110", split_factor="2", stop_px="40"), 56.0) \
        == ("TARGET", 55.0)
    ok("stop fills at the observed last (gap-aware); target is a resting limit")

    ph2 = pos(phase="2", stop_px="85")
    assert se.trail_stop(ph2, 130.0, cfg) == 110.5
    assert se.trail_stop(pos(phase="2", stop_px="120"), 130.0, cfg) == 120.0
    assert se.trail_stop(pos(), 130.0, cfg) == 85.0
    ok("MOM phase 2 trails 15% off the peak, never lowers; phase 1 stays put")

    c = cfg["mom"]
    f = {"r21": 12.0, "r3d": 0.5}
    assert se.mom_add_ok(pos(peak_px="110"), f, 108.0, c)
    assert not se.mom_add_ok(pos(peak_px="110"), f, 105.0, c)          # 4.5% off peak
    assert not se.mom_add_ok(pos(peak_px="110"), {"r21": 8, "r3d": 1}, 109.0, c)
    assert not se.mom_add_ok(pos(peak_px="110", add_ts="x"), f, 109.0, c)
    ok("double-down: 1M ≥ 10%, 3D ≥ 0, within 3% of peak, once per campaign")

    today = "2026-11-05"             # entry 10-05 → 31 days, 23 sessions
    assert se.rule_exit(pos(), None, 102.0, today, cfg) == "REVIEW"
    assert se.rule_exit(pos(), None, 110.0, today, cfg) is None
    assert se.rule_exit(pos(strategy="PB90"), None, 101.0, today, cfg) == "TIME"
    assert se.rule_exit(pos(strategy="PB90"), None, 101.0, "2026-10-20", cfg) is None
    r2 = pos(strategy="RSI2")
    f = {"last4": [100, 100, 100, 100]}
    assert se.rule_exit(r2, f, 101.0, "2026-10-06", cfg) == "RULE"
    assert se.rule_exit(r2, f, 99.0, "2026-10-06", cfg) is None
    assert se.rule_exit(r2, f, 99.0, "2026-10-19", cfg) == "TIME"
    ok("rule exits: MOM 28d going-nowhere review, PB90 20-session, RSI2 SMA5/10-session")


def test_store_rails():
    print("Store rails")
    fresh_store()
    row = {"position_id": "P1", "strategy": "MOM", "symbol": "AAA", "qty": 5,
           "entry_px_theo": "10.0000", "stop_px": "8.50"}
    assert st.add_position(row) and not st.add_position(row)
    assert len(st.read("positions")) == 1
    ok("deterministic campaign id: a second write is refused (crash rail)")
    try:
        st.update_position("P1", {"entry_px_theo": "11"}, allow=st.ACTUAL_COLS)
        raise AssertionError("theo writable")
    except ValueError:
        ok("theo columns immutable through every sanctioned path")
    st.update_position("P1", {"exit_ts": "T1", "exit_reason": "STOPPED"}, allow=st.WRITE_ONCE)
    st.update_position("P1", {"exit_ts": "T1"}, allow=st.WRITE_ONCE)   # same value: no-op
    try:
        st.update_position("P1", {"exit_ts": "T2"}, allow=st.WRITE_ONCE)
        raise AssertionError("write-once overwritten")
    except ValueError:
        ok("exit/add columns are write-once (no double exits)")
    st.update_position("P1", {"stop_px": "9.00"}, allow=st.TRACKER_COLS)
    st.update_position("P1", {"entry_px_actual": "10.02"}, allow=st.ACTUAL_COLS)
    st.update_position("P1", {"entry_px_actual": "10.01"}, allow=st.ACTUAL_COLS)
    p = st.get_position("P1")
    assert p["stop_px"] == "9.00" and p["entry_px_actual"] == "10.01"
    ok("tracker + actual columns stay mutable (trailing stops, manual fills)")


# ── fake-clock sessions ──────────────────────────────────────────────────────
class Crash(BaseException):
    """Simulated process death — BaseException so no engine handler eats it."""


class FakeClock:
    def __init__(self, start: datetime):
        self.t = start

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


class FakeData:
    """Bars sliced strictly before `asof`; quotes from a per-symbol function
    of time; an optional crash at a given instant."""

    def __init__(self, bars, clock, quote_fn=None, crash_at=None):
        self.bars, self.clock = bars, clock
        self.quote_fn = quote_fn or (lambda s, t: None)
        self.crash_at = crash_at
        self.calls = {"bars": 0, "quotes": 0}

    def universe_bars(self, symbols, asof):
        self.calls["bars"] += 1
        out = {s: [b for b in self.bars[s] if b["date"] < asof]
               for s in symbols if s in self.bars}
        return out, {"fake": len(out)}, [s for s in symbols if s not in self.bars]

    def quotes(self, symbols):
        self.calls["quotes"] += 1
        if self.crash_at and self.clock.now() >= self.crash_at:
            self.crash_at = None
            raise Crash()
        out = {}
        for s in symbols:
            v = self.quote_fn(s, self.clock.now())
            if v is None and s in self.bars:
                past = [b for b in self.bars[s] if b["date"] < self.clock.now().date().isoformat()]
                v = past[-1]["close"] if past else None
            if v:
                out[s] = v
        return out

    def vix_last(self):
        return 16.5


def ET(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=se.ET)


def test_session_with_crash():
    print("Fake-clock sessions (crash + restart)")
    fresh_store()
    cfg = base_cfg()
    bars = universe_fixture(date(2026, 10, 2))          # history through Fri 10-02
    d1 = date(2026, 10, 5)

    # Day 1 — crash on the first tracking pass after entries, then restart.
    clock = FakeClock(ET(2026, 10, 5, 9, 5))
    data = FakeData(bars, clock, crash_at=ET(2026, 10, 5, 9, 46))
    try:
        se.run_session(cfg, data, clock)
        raise AssertionError("crash not raised")
    except Crash:
        pass
    assert clock.now() >= ET(2026, 10, 5, 9, 45)
    buys1 = [r for r in st.signals_for("2026-10-05") if r["action"] == "BUY"]
    n_pos = len(st.read("positions"))
    assert n_pos == len(buys1) and n_pos >= 3, (n_pos, buys1)
    ok(f"entry slot ran at 09:45 → {n_pos} campaigns before the crash")

    clock.t = ET(2026, 10, 5, 10, 5)                   # supervisor relaunch
    out = se.run_session(cfg, data, clock)
    assert out == "done" and clock.now() >= ET(2026, 10, 5, 16, 10)
    assert len(st.read("positions")) == n_pos
    done = [r for r in st.signals_for("2026-10-05") if r["action"] == "DONE"]
    assert sorted(r["strategy"] for r in done) == ["MOM", "PB90", "RSI2"]
    assert len(st.rows_for_date("day", "2026-10-05")) == 1
    assert len(st.rows_for_date("eod", "2026-10-05")) == 1
    marks = st.rows_for_date("marks", "2026-10-05")
    assert len(marks) == n_pos == len({m["position_id"] for m in marks})
    ok("restart: no duplicated day/slot/campaign rows; one mark per campaign + one eod")

    held = {p["symbol"]: p for p in st.open_positions()}
    assert {"AAA", "CCC", "SPY"} <= set(held), held.keys()
    assert all(p["fill_notes"] == "simulated" and p["entry_px_actual"] for p in held.values())
    assert se.fnum(held["AAA"]["stop_px"]) == round(se.fnum(held["AAA"]["entry_px_theo"]) * 0.85, 2)
    ok("MOM/PB90/RSI2 each entered with simulated fills and their own stops")

    # Re-running a finished session is a no-op.
    assert se.run_session(cfg, data, FakeClock(ET(2026, 10, 5, 16, 30))) == "done"
    assert len(st.read("positions")) == n_pos
    ok("a finished session re-run does nothing")

    # Day 2 — AAA gaps −20% at 11:00 (MOM stop), SPY rallies (RSI2 rule exit
    # at 15:50), a 2:1 split of CCC is visible in the adjusted history.
    aaa_e = se.fnum(held["AAA"]["entry_px_theo"])
    spy_e = se.fnum(held["SPY"]["entry_px_theo"])
    ccc_mark = se.fnum([m for m in marks if m["symbol"] == "CCC"][0]["close"])
    bars2 = dict(bars)
    bars2["CCC"] = [dict(b, close=b["close"] / 2, high=b["high"] / 2, low=b["low"] / 2)
                    for b in bars["CCC"]] + [{"date": "2026-10-05", "open": ccc_mark / 2,
                                              "high": ccc_mark / 2, "low": ccc_mark / 2,
                                              "close": ccc_mark / 2}]
    for s in bars2:
        if s != "CCC":
            last = bars2[s][-1]["close"]
            bars2[s] = bars2[s] + [{"date": "2026-10-05", "open": last, "high": last,
                                    "low": last, "close": last}]

    def q2(s, t):
        if s == "AAA":
            return aaa_e * (0.80 if t >= ET(2026, 10, 6, 11, 0) else 1.0)
        if s == "SPY":
            return spy_e * 1.03
        if s == "CCC":
            return ccc_mark / 2
        return None

    clock2 = FakeClock(ET(2026, 10, 6, 9, 10))
    data2 = FakeData(bars2, clock2, quote_fn=q2, crash_at=ET(2026, 10, 6, 13, 0))
    try:
        se.run_session(cfg, data2, clock2)
        raise AssertionError("day-2 crash not raised")
    except Crash:
        pass
    assert data2.crash_at is None
    clock2.t = ET(2026, 10, 6, 13, 20)
    assert se.run_session(cfg, data2, clock2) == "done"
    aaa = [p for p in st.read("positions") if p["symbol"] == "AAA" and p["strategy"] == "MOM"][0]
    assert aaa["exit_reason"] == "STOPPED" and approx(se.fnum(aaa["exit_px_theo"]), aaa_e * 0.8, 1e-3)
    assert se.fnum(aaa["pnl_theo"]) < 0 and aaa["exit_ts"].startswith("2026-10-06T11:")
    ok("day 2: MOM stop hit on the gap, exit at the observed last, loss booked")
    spy = [p for p in st.read("positions") if p["symbol"] == "SPY"][0]
    assert spy["exit_reason"] == "RULE" and spy["exit_ts"][11:16] == "15:50", spy
    ok("day 2: RSI2 closed above its SMA5 at the 15:50 rule-exit window")
    ccc = [p for p in st.read("positions") if p["symbol"] == "CCC"][0]
    assert ccc["split_factor"] == "2" and st.is_open(ccc)
    splits = [e for e in st.read("events") if e["event"] == "SPLIT"]
    assert len(splits) == 1
    ccc_m2 = [m for m in st.rows_for_date("marks", "2026-10-06") if m["symbol"] == "CCC"][0]
    assert abs(se.fnum(ccc_m2["unrealized"])
               - float([m for m in marks if m["symbol"] == "CCC"][0]["unrealized"])) < 0.5
    ok("day 2: 2:1 split healed once — unrealized P&L continuous across it")
    exits = [e for e in st.read("events") if e["event"] == "EXIT"]
    assert len(exits) == len({e["position_id"] for e in exits})
    assert len(st.rows_for_date("eod", "2026-10-06")) == 1
    ok("day 2 crash/restart: every exit booked exactly once")

    eod = st.rows_for_date("eod", "2026-10-06")[0]
    closed = [p for p in st.read("positions") if not st.is_open(p)]
    assert approx(se.fnum(eod["realized_cum"]), round(sum(se.realized(p) for p in closed), 2), 0.011)
    ok("eod equity row = realized (actual-first) + unrealized marks")

    s = sr.summary(cfg)
    assert s["strategies"]["MOM"]["n"] >= 1 and s["strategies"]["RSI2"]["n"] == 1
    assert not s["strategies"]["MOM"]["gate"]["admissible"]
    txt = sr.text_report(cfg)
    assert "inadmissible" in txt
    ok("report runs offline on the journal; <20 closed flagged inadmissible")

    upd = se.apply_fill(cfg, spy["position_id"], exit_=round(spy_e * 1.02, 2), note="pm fill")
    spy = st.get_position(spy["position_id"])
    assert spy["pnl_theo"] and upd["pnl_actual"] == spy["pnl_actual"]
    assert se.fnum(spy["pnl_actual"]) < se.fnum(spy["pnl_theo"])
    ok("manual paperMoney exit fill overrides the simulated one; theo untouched")


def test_mom_add():
    print("MOM double-down (two-phase)")
    fresh_store()
    cfg = base_cfg()
    closes = [50 * 1.006 ** k for k in range(260)]        # r21 ≈ 13%
    bars = {"AAA": mk_bars(closes, date(2026, 10, 2))}
    for s_ in cfg["universe"]["stocks"][1:]:
        bars[s_] = mk_bars([40.0] * 260, date(2026, 10, 2))
    fe = se.build_features(cfg, bars)
    st.add_position({"position_id": "2026-09-01-MOM-AAA", "strategy": "MOM",
                     "symbol": "AAA", "side": "LONG", "tier": "large",
                     "signal_ts": "2026-09-01T09:45:00-04:00",
                     "entry_ts": "2026-09-01T09:45:00-04:00", "qty": "20",
                     "entry_px_theo": "200.0000", "stop_px_initial": "170.00",
                     "risk_usd": "600.00", "stop_px": "170.00",
                     "peak_px": f"{closes[-1]:.2f}", "phase": "1", "split_factor": "1",
                     "entry_px_actual": "200.1000"})
    last = round(closes[-1] * 0.99, 2)
    clock = FakeClock(ET(2026, 10, 5, 9, 45))
    data = FakeData(bars, clock, quote_fn=lambda s_, t: last if s_ == "AAA" else None)
    day = {"status": "OK"}
    se.do_entries(cfg, "2026-10-05", day, fe, data, clock, "MOM")
    p = st.get_position("2026-09-01-MOM-AAA")
    assert p["phase"] == "2" and p["add_qty"] == "20", p
    assert se.fnum(p["stop_px"]) == round(closes[-1] * 0.85, 2)
    assert approx(se.avg_cost(p), (200 + last) / 2, 1e-3)
    adds = [r for r in st.signals_for("2026-10-05") if r["action"] == "ADD"]
    assert len(adds) == 1 and se.fnum(adds[0]["risk_usd"]) > 0
    ok("add same qty at the 09:45 quote → phase 2, stop = peak × 0.85, avg cost blended")
    se.do_entries(cfg, "2026-10-05", day, fe, data, clock, "MOM")
    p = st.get_position("2026-09-01-MOM-AAA")
    assert p["add_qty"] == "20"
    assert len([r for r in st.signals_for("2026-10-05") if r["action"] == "ADD"]) == 1
    ok("a second pass never adds twice (write-once add columns)")


def test_missed_and_holiday():
    print("Freshness guard / holiday")
    fresh_store()
    cfg = base_cfg()
    bars = universe_fixture(date(2026, 10, 2))
    clock = FakeClock(ET(2026, 10, 5, 10, 40))           # engine was down all morning
    assert se.run_session(cfg, FakeData(bars, clock), clock) == "done"
    done = st.signals_for("2026-10-05")
    assert all(r["action"] == "DONE" and r["skip_reason"] == "MISSED" for r in done)
    assert len(done) == 3 and st.read("positions") == []
    ok("entry slot missed past the grace → SKIP/MISSED, never chased")
    clock = FakeClock(ET(2026, 11, 26, 9, 0))
    assert se.run_session(cfg, FakeData(bars, clock), clock) == "closed"
    assert st.rows_for_date("day", "2026-11-26")[0]["status"] == "SKIPPED_HOLIDAY"
    ok("NYSE holiday → SKIPPED_HOLIDAY day row, nothing else")


def rw_universe(n=520, seed=7):
    """Deterministic random walks with drift for the 10 stocks + 3 ETFs."""
    rnd = random.Random(seed)
    out = {}
    for i, sym in enumerate(base_cfg()["universe"]["stocks"] + ["SPY", "QQQ", "XLE"]):
        px, bars = 50.0 + i, []
        drift = 0.0002 * (i % 5)
        for _ in range(n):
            o = px * (1 + rnd.gauss(0, 0.004))
            c = o * (1 + drift + rnd.gauss(0, 0.015))
            bars.append((o, max(o, c) * (1 + abs(rnd.gauss(0, 0.004))),
                         min(o, c) * (1 - abs(rnd.gauss(0, 0.004))), c))
            px = c
        out[sym] = [{"date": d, "open": o, "high": h, "low": l, "close": c}
                    for d, (o, h, l, c) in zip(trading_days_back(date(2026, 9, 29), n), bars)]
    return out


def test_backtest():
    print("Backtester (same brain, no look-ahead)")
    cfg = base_cfg()
    bars = rw_universe()
    cal = [b["date"] for b in bars["SPY"]]
    start, cut = cal[bt.WINDOW], cal[430]
    base = {s_: bt.simulate(cfg, bars, s_, start, cal[-1]) for s_ in se.STRATEGIES}
    assert sum(len(r["trades"]) for r in base.values()) > 20, \
        {k: len(v["trades"]) for k, v in base.items()}
    ok("replays all three strategies on the engine's own functions → trades")
    fut = {s_: [dict(b, open=b["open"] * 0.5, high=b["high"] * 0.5, low=b["low"] * 0.5,
                     close=b["close"] * 0.5) if b["date"] >= cut else b for b in v]
           for s_, v in bars.items()}
    for s_ in se.STRATEGIES:
        a = [t for t in base[s_]["trades"] if t["exit"] < cut]
        b = [t for t in bt.simulate(cfg, fut, s_, start, cal[-1])["trades"] if t["exit"] < cut]
        assert a == b, s_
        ca = [c for c in base[s_]["curve"] if c["date"] < cut]
        cb = [c for c in bt.simulate(cfg, fut, s_, start, cal[-1])["curve"] if c["date"] < cut]
        assert ca == cb, s_
    ok("no look-ahead: rewriting the future never changes past trades or equity")

    # gap through the stop fills at the OPEN, not at the stop
    closes = [30 * 1.006 ** k for k in range(400)]
    g = {"AAA": mk_bars(closes, date(2026, 9, 29))}
    gap_day = g["AAA"][350]["date"]
    for i, b_ in enumerate(g["AAA"]):
        if i >= 350:
            px = closes[349] * 0.70 * 1.001 ** (i - 350)
            g["AAA"][i] = dict(b_, open=px, high=px * 1.01, low=px * 0.99, close=px)
    for s_ in cfg["universe"]["stocks"][1:] + ["SPY"]:
        g[s_] = mk_bars([40.0] * 400, date(2026, 9, 29))
    r = bt.simulate(cfg, g, "MOM", g["SPY"][300]["date"], g["SPY"][-1]["date"])
    t = [t_ for t_ in r["trades"] if t_["exit"] == gap_day]
    assert len(t) == 1 and t[0]["reason"] == "STOPPED", r["trades"]
    assert t[0]["exit_px"] == se.sim_sell(g["AAA"][350]["open"], 5) and t[0]["added"]
    ok("gap through a stop fills at the open (MOM phase 2 after its double-down)")

    m = bt.benchmark({"X": mk_bars([10, 15, 20], date(2026, 9, 29)),
                      "Y": mk_bars([10, 10, 20], date(2026, 9, 29))},
                     ["X", "Y"], trading_days_back(date(2026, 9, 29), 3), 100000)
    assert approx(m["total_return"], 1.0, 1e-9)
    ok("equal-weight buy-and-hold benchmark")

    gate = dict(bt.GATE_DEFAULTS)
    good = {"stats": {"n": 80, "expectancy": 50, "confidence": 0.95, "pf": 1.5},
            "in_sample": {}, "out_of_sample": {"expectancy": 10, "pf": 1.2},
            "metrics": {"max_dd_pct": -0.10, "sharpe": 1.1},
            "benchmark_universe": {"sharpe": 0.9}}
    assert bt.verdict(good, gate, 1e5)["pass"]
    for k, v in (("stats", {**good["stats"], "pf": 1.2}),
                 ("out_of_sample", {"expectancy": -5, "pf": 0.9}),
                 ("metrics", {"max_dd_pct": -0.2, "sharpe": 1.1}),
                 ("benchmark_universe", {"sharpe": 1.3})):
        assert not bt.verdict({**good, k: v}, gate, 1e5)["pass"], k
    ok("promotion verdict: every check can fail it (PF, OOS, drawdown, beat buy-and-hold)")

    c2 = base_cfg()
    c2["pb90"] = dict(c2["pb90"], stage="backtest")
    assert se.in_paper(c2, "MOM") and not se.in_paper(c2, "PB90")
    assert not se.in_paper(se.load_config("/nonexistent"), "MOM")
    ok("paper engine only enters strategies promoted to stage: paper (default: backtest)")


def test_cash_yield_and_stack():
    print("Cash yield (T-bill) + stacked book")
    days = trading_days_back(date(2026, 9, 29), 4)
    curve = [{"date": d, "equity": 100000.0, "exposure": 0.25} for d in days]
    rf = {days[0]: 0.0001}
    out, interest = bt.apply_cash_yield(curve, rf, 100000.0)
    # 3 accrual days on $75k idle cash at 1bp/day, compounding on the credited cash
    assert approx(interest, 75000 * 0.0001 + 75007.5 * 0.0001 + 75015.0008 * 0.0001, 0.02)
    assert out[-1]["equity"] == round(100000 + interest, 2)
    ok("idle cash (equity − invested) earns the day's T-bill rate")
    flat = [{"date": d, "equity": 100000 * 1.0001 ** i} for i, d in enumerate(days)]
    m0 = bt.curve_metrics(flat, 100000.0)
    m1 = bt.curve_metrics(flat, 100000.0, rf)
    assert m0["sharpe"] is None or m0["sharpe"] > 5            # riskless growth
    assert m1["sharpe"] is None                                  # zero excess, zero vol
    ok("Sharpe on excess returns: earning exactly the T-bill scores zero edge")
    a = {"trades": [{"exit": days[1], "pnl": 10}], "open_at_end": 0, "eq0": 100000.0,
         "curve": [{"date": d, "equity": 100000 + 10 * i, "exposure": 0.3} for i, d in enumerate(days)]}
    b = {"trades": [{"exit": days[2], "pnl": -5}], "open_at_end": 1, "eq0": 100000.0,
         "curve": [{"date": d, "equity": 100000 - 5 * i, "exposure": 0.5} for i, d in enumerate(days)]}
    c = bt.combine([a, b])
    assert [x["equity"] for x in c["curve"]] == [100000 + 5 * i for i in range(4)]
    assert c["max_exposure"] == 0.8 and len(c["trades"]) == 2 and c["open_at_end"] == 1
    ok("stacked book: P&L and exposure add on one account; peak exposure reported")


def test_pit_universe():
    print("Point-in-time universe (survivorship control)")
    snaps = bt.load_pit()
    m = bt.members_fn(snaps)
    assert 480 <= len(m("2020-06-01")) <= 520 and 480 <= len(m("2026-08-31")) <= 520
    assert "CELG" in m("2018-01-02") and "CELG" not in m("2026-08-31")   # acquired 2019
    assert "TSLA" not in m("2020-06-01") and "TSLA" in m("2021-01-04")   # added Dec 2020
    ok("S&P 500 membership replays: CELG out after its buyout, TSLA in from Dec 2020")

    cfg = base_cfg()
    bars = rw_universe()
    cal = [b["date"] for b in bars["SPY"]]
    join = cal[400]
    # AAA is the strongest name but only joins the index at `join`
    bars["AAA"] = mk_bars([30 * 1.006 ** k for k in range(520)], date(2026, 9, 29))
    others = set(cfg["universe"]["stocks"]) - {"AAA"}
    mem = lambda d: frozenset(others | ({"AAA"} if d >= join else set()))
    r = bt.simulate(cfg, bars, "MOM", cal[bt.WINDOW], cal[-1], members=mem)
    a = [t for t in r["trades"] if t["symbol"] == "AAA"]
    first = min((t["entry"] for t in a), default=None)
    assert first is None or first >= join, first
    ok("a stock is never bought before it joined the index")

    # a held name whose prices stop (buyout) is closed at its last close
    b2 = dict(bars)
    b2["AAA"] = bars["AAA"][:470]
    r = bt.simulate(cfg, b2, "MOM", cal[bt.WINDOW], cal[-1],
                    members=lambda d: frozenset(cfg["universe"]["stocks"]))
    dl = [t for t in r["trades"] if t["reason"] == "DELISTED"]
    assert len(dl) == 1 and dl[0]["symbol"] == "AAA", dl
    assert approx(dl[0]["exit_px"], b2["AAA"][-1]["close"], 1e-9)
    assert dl[0]["exit"] > b2["AAA"][-1]["date"]
    ok("delisted holdings close at their last price (no phantom positions)")

    ic, cov = bt.pit_index_curve({"X": mk_bars([10, 11, 12.1], date(2026, 9, 29)),
                                  "Y": mk_bars([10, 9, 8.1], date(2026, 9, 29))},
                                 lambda d: frozenset({"X", "Y", "Z"}),
                                 trading_days_back(date(2026, 9, 29), 3), 100.0)
    assert approx(ic[-1], 100.0) and approx(cov, 2 / 3)
    ok("equal-weight PIT index rebalances daily; coverage = member-days with prices")

    fresh_store()
    d = bt.bt_dir()
    d.mkdir(parents=True)
    (d / "runs.csv").write_text("ran_at,strategy,params_hash,start,end,trades,expectancy,pf,"
                                "confidence,max_dd_pct,sharpe,bench_sharpe,verdict\n"
                                "2026-09-30T09:11:23,MOM,abc,2017,2026,539,190,2.2,1.0,-0.12,0.98,1.0,FAIL\n")
    res = bt.run(cfg, rw_universe(), "RSI2", cal[bt.WINDOW], cal[-1])
    bt.save(res)
    import csv as _csv
    rows = list(_csv.DictReader(open(d / "runs.csv")))
    assert [r["universe_mode"] for r in rows] == ["fixed_today", "fixed_today"]
    assert rows[0]["pf"] == "2.2" and bt.load_latest()["RSI2"]["strategy"] == "RSI2"
    ok("run log upgrades an old-format runs.csv in place (hub compatibility)")


def test_observation_lanes_session():
    print("Paper engine runs the observation lanes (ICHI / ST / KDJA)")
    fresh_store()
    cfg = base_cfg()
    for k in ("mom", "pb90", "rsi2"):
        cfg[k] = dict(cfg[k], stage="backtest")
    for k in ("ichi", "st", "kdja"):
        cfg[k] = dict(cfg[k], stage="paper")
    rnd = random.Random(11)
    syms = cfg["universe"]["stocks"] + cfg["universe"]["etfs"] + se.lane_symbols(cfg)
    bars = {}
    for i, sym in enumerate(syms):
        px, closes = 40.0 + i, []
        for _ in range(300):
            px *= 1 + 0.0004 + rnd.gauss(0, 0.012)
            closes.append(px)
        b = mk_bars(closes, date(2026, 10, 2))
        for x in b:
            x["open"] = x["close"] * (1 + rnd.gauss(0, 0.004))
        bars[sym] = b
    assert set(se.lane_symbols(cfg)) <= set(bars)
    for day in (5, 6, 7, 8, 9):
        clock = FakeClock(ET(2026, 10, day, 9, 5))
        assert se.run_session(cfg, FakeData(bars, clock), clock) == "done"
    done = {(r["date"], r["strategy"]) for r in st.read("signals") if r["action"] == "DONE"}
    for d in ("2026-10-05", "2026-10-09"):
        assert {(d, "ICHI"), (d, "ST"), (d, "KDJA")} <= done, done
    assert not any(r["strategy"] in ("MOM", "PB90", "RSI2") for r in st.read("signals"))
    pos_ = st.read("positions")
    assert all(p["strategy"] in ("ICHI", "ST", "KDJA") for p in pos_)
    assert all(p["symbol"] in cfg[p["strategy"].lower()]["symbols"] for p in pos_)
    ok(f"5 fake sessions: only ICHI/ST/KDJA trade, each in its own ETFs ({len(pos_)} campaigns)")


def test_real_config():
    print("Shipped config")
    cfg = se.load_config()
    base = cfg["universe"]["stocks"] + cfg["universe"]["etfs"]
    assert len(base) == 100 and len(set(base)) == 100
    u = se.universe(cfg)
    assert len(u) == len(set(u)) and set(se.lane_symbols(cfg)) == {
        "FXI", "MCHI", "ASHR", "INDA", "EPI", "EWJ", "DXJ"}
    assert set(cfg["gates"]) == set(se.STRATEGIES)
    ok("stocks_config.yaml: 100 unique base symbols (+ 7 Asia lane ETFs), a gate per strategy")


if __name__ == "__main__":
    for t in (test_indicators, test_calendar_and_regime, test_candidates, test_new_candidates, test_rotation_lanes,
              test_market_effect_lanes, test_weighted_lanes, test_round7_lanes,
              test_asian_methods,
              test_sizing_fills_fees, test_campaign_math, test_store_rails, test_mom_add,
              test_session_with_crash, test_missed_and_holiday, test_backtest, test_cash_yield_and_stack, test_pit_universe,
              test_observation_lanes_session, test_real_config):
        t()
    print(f"\nALL {PASS} CHECKS PASSED")
    sys.exit(0)
