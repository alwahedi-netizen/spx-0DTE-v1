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


def test_real_config():
    print("Shipped config")
    cfg = se.load_config()
    u = se.universe(cfg)
    assert len(u) == 100 and len(set(u)) == 100
    assert set(cfg["gates"]) == set(se.STRATEGIES)
    ok("stocks_config.yaml: 100 unique symbols, a gate per strategy")


if __name__ == "__main__":
    for t in (test_indicators, test_calendar_and_regime, test_candidates,
              test_sizing_fills_fees, test_campaign_math, test_store_rails, test_mom_add,
              test_session_with_crash, test_missed_and_holiday, test_real_config):
        t()
    print(f"\nALL {PASS} CHECKS PASSED")
    sys.exit(0)
