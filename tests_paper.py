"""
tests_paper.py  —  Logicon Capital  ·  paper-mode signal logger tests
=====================================================================
Run before every push:   python3 tests_paper.py
Exits non-zero on any failure. Offline by design: fixture chains only, no
Schwab API, no engine secrets — paper_engine/paper_store/paper_report must
stay importable without .env (spec §9).
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

import paper_engine as pe
import paper_store as st
import paper_report as pr

PASS = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")


def c_(m, delta=None, wide=False):
    """Contract with mid m. wide=True fails the leg_ok quote rail."""
    if wide:
        return {"bid": 0.02, "ask": 2 * m - 0.02, "delta": delta}
    return {"bid": round(m - 0.05, 2), "ask": round(m + 0.05, 2), "delta": delta}


def put_cmap():
    """SPX puts, spot 6000. Credits for 30-wide verticals:
    5990:3.30  5980:2.30  5975:1.90  5970:1.65  5965:1.40  5960:1.20 ..."""
    mids = {5995: 6.0, 5990: 5.0, 5985: 4.2, 5980: 3.5, 5975: 2.9, 5970: 2.45,
            5965: 2.05, 5960: 1.7, 5955: 1.45, 5950: 1.2, 5945: 1.0, 5940: 0.8,
            5935: 0.65, 5930: 0.5, 5925: 0.4, 5920: 0.32, 5915: 0.25,
            5910: 0.2, 5905: 0.15, 5900: 0.12, 5895: 0.10, 5890: 0.08,
            5885: 0.06, 5880: 0.05, 5875: 0.04, 5870: 0.03}
    m = {float(k): c_(v, delta=-0.1) for k, v in mids.items()}
    return m


def call_cmap():
    mids = {6005: 6.0, 6010: 5.0, 6015: 4.2, 6020: 3.5, 6025: 2.9, 6030: 2.45,
            6035: 2.05, 6040: 1.7, 6045: 1.45, 6050: 1.2, 6055: 1.0, 6060: 0.8,
            6065: 0.65, 6070: 0.5, 6075: 0.4, 6080: 0.32, 6085: 0.25,
            6090: 0.2, 6095: 0.15, 6100: 0.12}
    return {float(k): c_(v, delta=0.1) for k, v in mids.items()}


# ── EMA state (§6.2) ─────────────────────────────────────────────────────────
def test_ema_state():
    print("EMA state")
    up = [5900 + i for i in range(60)]
    s, ef, es = pe.metf_state(up, 20, 40)
    assert s == "UP" and ef > es, (s, ef, es)
    assert pe.metf_side(s) == "PUT"
    ok("rising closes -> UP -> PUT vertical")

    down = [6000 - i for i in range(60)]
    s, ef, es = pe.metf_state(down, 20, 40)
    assert s == "DOWN" and pe.metf_side(s) == "CALL"
    ok("falling closes -> DOWN -> CALL vertical")

    flat = [6000.0] * 60
    s, ef, es = pe.metf_state(flat, 20, 40)
    assert ef == es and s == "DOWN", (s, ef, es)
    ok("EMA equality -> DOWN (conservative)")

    s, ef, es = pe.metf_state([6000.0] * 30, 20, 40)   # < slow period
    assert s is None
    ok("too few bars -> no state (DATA skip)")


# ── strike walk (§6.2) ───────────────────────────────────────────────────────
def test_strike_walk():
    print("Strike walk")
    pick, skip = pe.walk_strikes(put_cmap(), "PUT", 6000.0, 30, 1.50, 1.25)
    assert skip is None and pick["short_strike"] == 5970.0 \
        and pick["long_strike"] == 5940.0, pick
    assert abs(pick["credit"] - 1.65) < 1e-9
    ok("puts: furthest OTM with credit >= target (5970/5940 @ 1.65)")

    pick, skip = pe.walk_strikes(call_cmap(), "CALL", 6000.0, 30, 1.50, 1.25)
    assert skip is None and pick["short_strike"] == 6030.0 \
        and pick["long_strike"] == 6060.0, pick
    ok("calls: furthest OTM with credit >= target (6030/6060)")

    # nothing reaches target 5.00 -> best available (nearest OTM), >= min_credit
    pick, skip = pe.walk_strikes(put_cmap(), "PUT", 6000.0, 30, 5.00, 1.25)
    assert skip is None and pick["short_strike"] == 5995.0, pick
    ok("no strike at target -> best available credit")

    # best available below min_credit -> SKIP/CREDIT
    thin = {5990.0: c_(1.5), 5960.0: c_(0.6)}     # credit 0.90 < 1.25
    pick, skip = pe.walk_strikes(thin, "PUT", 6000.0, 30, 1.50, 1.25)
    assert pick is None and skip == "CREDIT"
    ok("best credit < min_credit -> SKIP/CREDIT")

    # junk quote (0.02 x wide) further OTM must be excluded by the leg_ok rail
    junk = put_cmap()
    junk[5900.0] = c_(1.60, wide=True)            # fictional 1.6 mid
    pick, skip = pe.walk_strikes(junk, "PUT", 6000.0, 30, 1.50, 1.25)
    assert pick["short_strike"] == 5970.0, pick
    ok("wide junk quote excluded from the walk")


# ── band math + skew branching (§6.3) ────────────────────────────────────────
def test_band():
    print("Band math / skew branching")
    em, lower, upper, skew = pe.band_metrics(6003.0, 40.0, 0.85)
    assert abs(em - 34.0) < 1e-9 and upper == 6040.0 and lower == 5965.0, \
        (em, lower, upper)
    assert abs(skew - 37.0 / 38.0) < 1e-9
    ok("expected move + 5-pt outward rounding + skew")

    assert pe.band_structure(1.5, 0.80, 1.25) == "CALL_VERTICAL"
    assert pe.band_structure(0.6, 0.80, 1.25) == "PUT_VERTICAL"
    assert pe.band_structure(1.0, 0.80, 1.25) == "IRON_CONDOR"
    assert pe.band_structure(1.25, 0.80, 1.25) == "IRON_CONDOR"   # bounds inclusive
    assert pe.band_structure(0.80, 0.80, 1.25) == "IRON_CONDOR"
    ok("skew 1.5 -> CALL_VERTICAL, 0.6 -> PUT_VERTICAL, 1.0/bounds -> IRON_CONDOR")

    legs = pe._band_side_legs("IRON_CONDOR", 5965.0, 6040.0, 30)
    assert legs == [("PUT", 5965.0, 5935.0), ("CALL", 6040.0, 6070.0)]
    legs = pe._band_side_legs("CALL_VERTICAL", 5965.0, 6040.0, 30)
    assert legs == [("CALL", 6040.0, 6070.0)]
    ok("structure -> legs (condor both sides, vertical cushioned side only)")


# ── containment sizing (§6.3) ────────────────────────────────────────────────
def test_containment():
    print("Containment sizing")
    size, rc, warm = pe.containment_size([1] * 19, 20, 0.70, 0.55)
    assert size == 1.0 and warm is True
    ok("warmup: <20 days history -> size 1.0, flagged")
    size, rc, warm = pe.containment_size([1] * 15 + [0] * 5, 20, 0.70, 0.55)
    assert size == 1.0 and rc == 0.75 and warm is False
    ok("rc 0.75 -> full size")
    size, rc, warm = pe.containment_size([1] * 12 + [0] * 8, 20, 0.70, 0.55)
    assert size == 0.5 and rc == 0.60
    ok("rc 0.60 -> half size")
    size, rc, warm = pe.containment_size([1] * 8 + [0] * 12, 20, 0.70, 0.55)
    assert size is None and rc == 0.40
    ok("rc 0.40 -> SKIP_CONTAINMENT")


# ── stops, settlement, risk budget (§6.2/6.4) ────────────────────────────────
def test_risk_and_stops():
    print("Risk budget / stop / settlement")
    # METF: loss at stop == credit * stop_multiple * 100 * contracts
    credit, stop = 1.50, 1.50 * 2
    assert pe.stop_risk(credit, stop, 1) == 150.0
    ok("METF stop risk = credit * stop_multiple * 100")
    assert pe.risk_ok(1300.0, 150.0, 1500.0)
    assert not pe.risk_ok(1400.0, 150.0, 1500.0)
    ok("cumulative stop risk capped at daily budget -> SKIP/RISK")

    assert pe.stop_triggered(3.00, 3.00) and not pe.stop_triggered(2.99, 3.00)
    ok("stop at spread value >= stop_level")

    # condor side stops at total credit: risk/side = (total - side credit) * 100
    assert pe.stop_risk(1.2, 2.5, 1) == 130.0
    ok("band side stop risk = (total credit - side credit) * 100")

    assert pe.settle_value("PUT", 5970, 5940, 5950.0) == 20.0
    assert pe.settle_value("PUT", 5970, 5940, 5930.0) == 30.0    # capped at width
    assert pe.settle_value("CALL", 6030, 6060, 6000.0) == 0.0
    ok("settlement at intrinsic vs close")
    assert abs(pe.vertical_pnl(1.65, 0.0, 1) - 165.0) < 1e-6
    assert abs(pe.vertical_pnl(1.65, 20.0, 1) + 1835.0) < 1e-6
    ok("pnl = (credit - exit) * 100 * contracts")


# ── simulated execution ──────────────────────────────────────────────────────
def test_sim_execution():
    print("Simulated execution")
    assert pe.sim_cfg({"execution": {"mode": "simulated"}}) is not None
    assert pe.sim_cfg({"execution": {"mode": "off"}}) is None
    assert pe.sim_cfg({}) is None
    ok("execution.mode gates the simulator")
    assert abs(pe.sim_entry_credit(1.65, 0.05) - 1.60) < 1e-9
    assert pe.sim_entry_credit(0.03, 0.05) == 0.0
    ok("entry fill = theo credit - slippage (floored at 0)")
    assert abs(pe.sim_exit_value(3.35, "STOPPED", 0.05) - 3.40) < 1e-9
    assert abs(pe.sim_exit_value(0.05, "TP", 0.05) - 0.10) < 1e-9
    assert pe.sim_exit_value(20.0, "EXPIRED", 0.05) == 20.0
    ok("stop/TP exits pay slippage; expiry settles at intrinsic")


# ── MEIC + ORB (parallel strategies) ─────────────────────────────────────────
def test_meic_orb():
    print("MEIC / ORB")
    cfg = pe.load_config(path="/nonexistent")
    assert cfg["meic"]["enabled"] and cfg["orb"]["enabled"]
    ok("both strategies enabled in defaults")

    assert pe.orb_signal(6010.0, 6005.0, 5990.0) == "CALL"
    assert pe.orb_signal(5980.0, 6005.0, 5990.0) == "PUT"
    assert pe.orb_signal(6000.0, 6005.0, 5990.0) is None
    assert pe.orb_signal(6005.0, 6005.0, 5990.0) is None    # touch is not a break
    ok("ORB: breakout above -> CALL, below -> PUT, inside -> no trigger")

    pick = pe.pick_debit_vertical(call_cmap(), "CALL", 6003.0, 30)
    assert pick["buy"] == 6005.0 and pick["sell"] == 6035.0
    assert abs(pick["debit"] - (6.0 - 2.05)) < 1e-9
    ok("ORB: nearest-the-money debit vertical in breakout direction")

    # debit sign convention: credit=-debit, stop=-debit*(1-frac); the credit
    # engine's stop/pnl/risk math must come out right unchanged
    debit = 3.95
    credit, stop = -debit, -debit * 0.5
    assert abs(pe.stop_risk(credit, stop, 1) - debit * 0.5 * 100) < 1e-6
    assert pe.stop_triggered(-1.90, stop) and not pe.stop_triggered(-2.10, stop)
    # winning to expiry: spread worth 30 -> stored -30
    assert abs(pe.vertical_pnl(credit, -30.0, 1) - (30.0 - debit) * 100) < 1e-6
    # settlement of a call debit stored short=far/long=near comes out negative
    assert pe.settle_value("CALL", 6035.0, 6005.0, 6050.0) == -30.0
    ok("debit sign convention: stop, risk and P/L all correct")

    assert abs(pe.sim_entry_credit(-3.95, 0.05) + 4.00) < 1e-9
    ok("simulated debit fill pays debit + slippage")


# ── FLY + LATE (premium-selling additions) ───────────────────────────────────
def test_fly_late():
    print("FLY / LATE")
    cfg = pe.load_config(path="/nonexistent")
    assert cfg["fly"]["enabled"] and cfg["late"]["enabled"]
    ok("both enabled in defaults")

    assert pe.fly_group_action(36.0, 36.0, 0.25, 0.25) is None
    assert pe.fly_group_action(26.9, 36.0, 0.25, 0.25) == "TP"      # <= 27.0
    assert pe.fly_group_action(45.1, 36.0, 0.25, 0.25) == "STOPPED" # >= 45.0
    ok("fly managed as one structure: TP at -25% value, stop at +25%")

    # per-side stop_level credit*(1+sl) makes open risk sum to total*sl*100
    r = pe.stop_risk(18.3, 18.3 * 1.25, 1) + pe.stop_risk(17.7, 17.7 * 1.25, 1)
    assert abs(r - 36.0 * 0.25 * 100) < 1e-6
    ok("fly risk accounting = sl_frac of total credit")


# ── FLYR (reload fly) ────────────────────────────────────────────────────────
def test_flyr():
    print("FLYR reload fly")
    cfg = pe.load_config(path="/nonexistent")
    assert cfg["flyr"]["enabled"] and cfg["flyr"]["max_reloads"] == 2
    ok("enabled in defaults, 2 reloads max")

    def pair(strat, ts, r1=None, r2=None):
        return [{"strategy": strat, "signal_ts": ts, "side": s,
                 "exit_ts": ts if r else "", "exit_reason": r or ""}
                for s, r in (("PUT", r1), ("CALL", r2))]

    # chain-state parsing: order, openness, group exit reason
    rows = pair("FLY", "2026-09-21T13:00:00-04:00", "TP", "TP") + \
        pair("FLYR", "2026-09-21T13:41:00-04:00")
    groups, n_flyr = pe.fly_chain_state(rows)
    assert [g["strategy"] for g in groups] == ["FLY", "FLYR"] and n_flyr == 1
    assert groups[0]["exit_reason"] == "TP" and not groups[0]["open"]
    assert groups[1]["open"] and groups[1]["exit_reason"] == ""
    ok("fly chain groups by (ts, strategy) in entry order")

    act = pe.flyr_reload_action
    tp = [{"strategy": "FLY", "open": False, "exit_reason": "TP"}]
    assert act(tp, 0, 2, "13:41", "14:45") is True
    ok("reload fires after a TP inside the window")
    assert act([], 0, 2, "13:41", "14:45") is False           # no fly today
    assert act(tp, 2, 2, "13:41", "14:45") is False           # budget spent
    assert act(tp, 0, 2, "14:46", "14:45") is False           # too late
    stopped = [{"strategy": "FLY", "open": False, "exit_reason": "STOPPED"}]
    assert act(stopped, 0, 2, "13:41", "14:45") is False      # never chase
    open_ = [{"strategy": "FLY", "open": True, "exit_reason": ""}]
    assert act(open_, 0, 2, "13:41", "14:45") is False        # still working
    mixed = [{"strategy": "FLY", "open": False, "exit_reason": "TP"},
             {"strategy": "FLYR", "open": False, "exit_reason": "EXPIRED"}]
    assert act(mixed, 1, 2, "14:00", "14:45") is False        # last not TP
    ok("no reload without a fresh TP: empty/spent/late/stopped/open/expired")

    # a TP'd reload chains once more while budget and clock allow
    chain2 = [{"strategy": "FLY", "open": False, "exit_reason": "TP"},
              {"strategy": "FLYR", "open": False, "exit_reason": "TP"}]
    assert act(chain2, 1, 2, "14:20", "14:45") is True
    assert act(chain2, 2, 2, "14:20", "14:45") is False
    ok("chain continues on TP up to max_reloads, then stops")


# ── multi-strategy live mirror (order builders + mirror logic; offline) ─────
def test_live_meic():
    print("Live mirror (multi-strategy)")
    import live_meic as lm

    assert lm.strat_of("2026-09-29-MEIC-12:00-PUT") == "MEIC"
    assert lm.strat_of("2026-09-29-FLYR1-CALL") == "FLYR"
    assert lm.strat_of("2026-09-29-ORB-CALL") == "ORB"
    ok("strategy parsed from position ids (FLYR1 -> FLYR)")

    # SPX tick grid: 0.05 below $3.00, 0.10 at/above (off-tick = REJECTED)
    assert lm.spx_tick(1.72, up=False) == 1.70
    assert lm.spx_tick(1.72, up=True) == 1.75
    assert lm.spx_tick(4.48, up=True) == 4.50
    assert lm.spx_tick(2.98, up=True) == 3.00
    ok("limits snap to the SPX 0.05/0.10 tick grid")

    # signed limits: credit spreads concede down, debit spreads pay up
    assert lm.entry_limit(1.90) == 1.85
    assert lm.entry_limit(-8.28) == -8.40         # pay more, tick-legal
    assert lm.reprice_entry(-8.28) == -8.50
    assert lm.close_limit(3.40, 0, True) == 3.50  # pay up to exit a credit
    assert lm.close_limit(-4.10, 0, False) == -4.00  # receive less on debit
    assert lm.close_limit(-0.10, 2, False) == -0.05  # never flips sign
    ok("signed entry/close limits (ORB debit convention)")

    o = lm.vertical_order("PUT", 6600, 6570, "2026-09-29", 1, "OPEN", 1.85)
    assert o["orderType"] == "NET_CREDIT" and o["price"] == "1.85"
    assert [l["instruction"] for l in o["orderLegCollection"]] == \
        ["SELL_TO_OPEN", "BUY_TO_OPEN"]
    d = lm.vertical_order("CALL", 6650, 6620, "2026-09-29", 1, "OPEN", -8.40)
    assert d["orderType"] == "NET_DEBIT" and d["price"] == "8.40"
    dc = lm.vertical_order("CALL", 6650, 6620, "2026-09-29", 1, "CLOSE", -4.00)
    assert dc["orderType"] == "NET_CREDIT" and dc["price"] == "4.00"
    cc = lm.vertical_order("CALL", 6650, 6680, "2026-09-29", 1, "CLOSE", 3.40)
    assert cc["orderType"] == "NET_DEBIT" and \
        [l["instruction"] for l in cc["orderLegCollection"]] == \
        ["BUY_TO_CLOSE", "SELL_TO_CLOSE"]
    ok("credit orders NET_CREDIT/NET_DEBIT, debit orders mirrored (ORB)")

    filled = {"orderLegCollection": [
                 {"legId": 1, "instruction": "SELL_TO_OPEN"},
                 {"legId": 2, "instruction": "BUY_TO_OPEN"}],
              "orderActivityCollection": [{"executionLegs": [
                 {"legId": 1, "price": 2.10, "quantity": 1},
                 {"legId": 2, "price": 0.30, "quantity": 1}]}]}
    assert abs(lm.fill_price(filled) - 1.80) < 1e-9
    ok("net fill price = sells - buys")

    # fee model: pnl_live is net of ~$1.18/leg so it matches Schwab's cash
    assert lm.net_pnl(2.20, 0.00, 1, 2) == 217.64
    assert lm.net_pnl(1.60, 7.60, 1, 4) == -604.72
    assert lm.net_pnl(-8.40, -12.00, 1, 4) == 355.28   # debit spread winner
    ok("net_pnl deducts measured per-leg costs (debit sign too)")

    NOW = "2026-09-29T12:31:00-04:00"
    fresh = {"position_id": "2026-09-29-MEIC-12:30-PUT", "strategy": "MEIC",
             "side": "PUT", "short_strike": "6600", "long_strike": "6570",
             "credit_theo": "1.90", "stop_level": "3.40",
             "signal_ts": "2026-09-29T12:30:05-04:00", "exit_ts": "",
             "exit_reason": "", "exit_value_theo": ""}
    stale = dict(fresh, position_id="2026-09-29-MEIC-12:00-PUT",
                 signal_ts="2026-09-29T12:00:00-04:00")
    A = dict(armed_strats={"MEIC"}, paused=set(), halted=set())
    a = lm.plan_actions([fresh, stale], {}, NOW, **A)
    assert a == [("open", fresh)]
    ok("mirrors only FRESH signals of ARMED strategies")

    orb = dict(fresh, position_id="2026-09-29-ORB-CALL", strategy="ORB",
               signal_ts="2026-09-29T12:30:05-04:00")
    assert lm.plan_actions([orb], {}, NOW, **A) == []
    a = lm.plan_actions([orb], {}, NOW, armed_strats={"MEIC", "ORB"},
                        paused=set(), halted=set())
    assert a == [("open", orb)]
    ok("per-strategy arming: unarmed strategies never mirror")

    assert lm.plan_actions([fresh], {}, NOW, armed_strats={"MEIC"},
                           paused={"MEIC"}, halted=set()) == []
    assert lm.plan_actions([fresh], {}, NOW, armed_strats={"MEIC"},
                           paused=set(), halted={"MEIC"}) == []
    ok("paused / halted are per strategy")

    late_fly = dict(fresh, position_id="2026-09-29-FLY-PUT", strategy="FLY",
                    signal_ts="2026-09-29T13:20:30-04:00")
    assert lm.plan_actions([late_fly], {}, "2026-09-29T13:21:00-04:00",
                           armed_strats={"FLY"}, paused=set(),
                           halted=set()) == []          # after FLY entry_last
    cap_ledger = {f"2026-09-29-MEIC-{i:02d}:00-PUT": {"status": "OPEN"}
                  for i in range(lm.STRATS["MEIC"]["cap"])}
    assert lm.plan_actions([fresh], cap_ledger, NOW, **A) == []
    ok("per-strategy entry cutoffs and side caps")

    stopped = dict(fresh, exit_ts=NOW, exit_reason="STOPPED",
                   exit_value_theo="3.55")
    led = {fresh["position_id"]: {"status": "OPEN"}}
    a = lm.plan_actions([stopped], led, NOW, armed_strats={"MEIC"},
                        paused={"MEIC"}, halted={"MEIC"})
    assert a == [("close", fresh["position_id"], "STOPPED", 3.55)]
    ok("open live sides are managed even while paused/halted")

    # Schwab-sync audit: our ledger vs the account's real positions
    row = {"position_id": "2026-09-29-MEIC-12:00-PUT", "status": "OPEN",
           "side": "PUT", "qty": "1", "short_strike": "7695",
           "long_strike": "7665", "expiry": "2026-09-29"}
    sym = lm.osi_symbol("SPXW", "2026-09-29", "P", 7695)
    pos_ok = [{"instrument": {"symbol": sym}, "shortQuantity": 1,
               "currentDayProfitLoss": 123.4}]
    a = lm.schwab_audit([row], pos_ok, "2026-09-29")
    assert a["ok"] and abs(a["day_pl"] - 123.4) < 1e-9
    a = lm.schwab_audit([row], [], "2026-09-29")
    assert not a["ok"] and a["missing"] == [row["position_id"]]
    other_exp = [{"instrument": {"symbol": lm.osi_symbol("SPXW", "2026-10-17", "C", 7770)},
                  "shortQuantity": 1, "currentDayProfitLoss": 0}]
    assert lm.schwab_audit([], other_exp, "2026-09-29")["ok"]
    ok("audit: match / missing / other-expiry positions untouched")


# ── shared .env fallback for token refresh ───────────────────────────────────
def test_env_fallback():
    print("Shared .env fallback")
    import tempfile
    import schwab_auth as sa
    d = Path(tempfile.mkdtemp(prefix="envtest_"))
    (d / ".env").write_text('# comment\nSCHWAB_APP_KEY="k123"\nSCHWAB_APP_SECRET=s456\nOTHER=x\n')
    vals = sa._parse_env_file(d / ".env")
    assert vals["SCHWAB_APP_KEY"] == "k123" and vals["SCHWAB_APP_SECRET"] == "s456"
    assert sa._parse_env_file(d / "missing.env") == {}
    ok("app key falls back to the .env beside the shared tokens.json")


# ── store: idempotent slots, immutable theo columns (§9) ─────────────────────
def test_store():
    print("Store idempotency / immutability")
    st.DATA_DIR = Path(tempfile.mkdtemp(prefix="paper_test_"))
    cfg = pe.load_config(path="/nonexistent")           # pure defaults
    d = date.today().isoformat()

    assert pe.pending_metf_slots(cfg, d) == cfg["metf"]["slots"]
    st.append("signals", {"ts": f"{d}T10:00:05-04:00", "date": d,
                          "slot": "10:00", "strategy": "METF", "action": "SKIP",
                          "skip_reason": "CREDIT"})
    assert pe.pending_metf_slots(cfg, d) == cfg["metf"]["slots"][1:]
    st.append("signals", {"ts": f"{d}T10:00:06-04:00", "date": d,
                          "slot": "10:00", "strategy": "METF", "action": "SKIP",
                          "skip_reason": "CREDIT"})
    assert pe.pending_metf_slots(cfg, d) == cfg["metf"]["slots"][1:]
    ok("a logged slot never re-runs (restart-safe)")

    assert pe.pending_meic_slots(cfg, d) == cfg["meic"]["slots"]
    st.append("signals", {"ts": f"{d}T12:00:03-04:00", "date": d, "slot": "12:00",
                          "strategy": "MEIC", "action": "SELL_CONDOR"})
    assert pe.pending_meic_slots(cfg, d) == cfg["meic"]["slots"][1:]
    assert pe.pending_orb_slots(cfg, d) == cfg["orb"]["check_slots"]
    st.append("signals", {"ts": f"{d}T10:30:03-04:00", "date": d, "slot": "10:30",
                          "strategy": "ORB", "action": "SKIP", "skip_reason": "TRIGGER"})
    assert pe.pending_orb_slots(cfg, d) == cfg["orb"]["check_slots"][1:]
    st.append("signals", {"ts": f"{d}T11:30:03-04:00", "date": d, "slot": "11:30",
                          "strategy": "ORB", "action": "BUY_VERTICAL"})
    assert pe.pending_orb_slots(cfg, d) == []    # traded once -> done for the day
    assert pe.pending_condor_slots(cfg, d, "LATE") == cfg["late"]["slots"]
    assert pe.fly_pending(d)
    st.append("signals", {"ts": f"{d}T13:00:03-04:00", "date": d, "slot": "13:00",
                          "strategy": "FLY", "action": "SELL_CONDOR"})
    assert not pe.fly_pending(d)
    ok("MEIC/LATE slots idempotent; ORB and FLY at most once per day")

    assert pe.band_signal_pending(cfg, d)
    st.append("signals", {"ts": f"{d}T10:35:02-04:00", "date": d, "slot": "10:35",
                          "strategy": "BAND", "action": "SELL_CONDOR"})
    assert not pe.band_signal_pending(cfg, d)
    ok("band entry emitted once per day")

    assert st.rows_for_date("day", d) == []
    st.append("day", {"date": d, "status": "OK", "risk_budget": "1500.00"})
    assert len(st.rows_for_date("day", d)) == 1
    ok("day row lookup keyed by date")

    pid = f"{d}-METF-10:45-PUT"
    st.append("positions", {"position_id": pid, "signal_ts": f"{d}T10:45:03-04:00",
                            "strategy": "METF", "side": "PUT", "contracts": 1,
                            "short_strike": 5970.0, "long_strike": 5940.0,
                            "credit_theo": "1.65", "stop_level": "3.30"})
    assert len(st.open_positions()) == 1
    assert abs(pe.open_stop_risk() - 165.0) < 1e-9
    ok("open positions feed the cumulative risk check")

    try:
        st.update_position(pid, {"credit_theo": "9.99"}, allow=st.ACTUAL_COLS)
        raise AssertionError("theo column was writable via fill path")
    except ValueError:
        ok("fill can never touch theo columns")

    st.update_position(pid, {"credit_actual": "1.45", "fill_notes": "filled 10:46"},
                       allow=st.ACTUAL_COLS)
    row = st.read("positions")[0]
    assert row["credit_actual"] == "1.45" and row["credit_theo"] == "1.65"
    ok("fill updates only *_actual columns")

    st.update_position(pid, {"exit_ts": f"{d}T16:00:00-04:00",
                             "exit_value_theo": "0.00", "exit_reason": "EXPIRED",
                             "pnl_theo": "165.00"}, allow=st.EXIT_COLS)
    assert st.open_positions() == []
    ok("closed position leaves the open set")

    st.append("band", {"date": d, "spot_1030": "6003.00", "straddle_mid": "40.00",
                       "em": "34.00", "lower": "5965", "upper": "6040",
                       "skew": "0.974"})
    assert pe.band_row_for(d)["contained"] == ""
    st.update_band(d, {"spx_close": "6001.50", "contained": 1})
    assert pe.band_row_for(d)["contained"] == "1"
    try:
        st.update_band(d, {"skew": "2.0"})
        raise AssertionError("band theo column was writable")
    except ValueError:
        ok("band settlement fills contained; other columns append-only")

    # daily/weekly P&L rollup (dashboard card + report line)
    st.append("positions", {"position_id": f"{d}-BAND-CALL", "signal_ts": f"{d}T10:35:02-04:00",
                            "strategy": "BAND", "side": "CALL", "contracts": 1,
                            "short_strike": 6040.0, "long_strike": 6070.0,
                            "credit_theo": "1.40", "stop_level": "2.80",
                            "exit_ts": f"{d}T14:00:00-04:00", "exit_value_theo": "2.85",
                            "exit_reason": "STOPPED", "pnl_theo": "-145.00",
                            "pnl_actual": "-155.00"})
    ps = pr.pnl_summary(today=d, week_start=d)
    # METF closed row has pnl_theo 165 (no pnl_actual), BAND has pnl_actual -155
    assert ps["today"]["METF"] == 165.0 and ps["today"]["BAND"] == -155.0
    assert ps["today"]["TOTAL"] == 10.0 and ps["week"]["TOTAL"] == 10.0
    assert ps["days"][0]["date"] == d and ps["days"][0]["TOTAL"] == 10.0
    ok("daily/weekly P&L per strategy (actual first, theo fallback)")

    # report runs on the CSVs alone (no API) — §9
    pr.run_report(weeks=1)
    ok("report runs offline on the journal CSVs")


if __name__ == "__main__":
    for t in (test_ema_state, test_strike_walk, test_band, test_containment,
              test_risk_and_stops, test_sim_execution, test_meic_orb, test_fly_late,
              test_flyr, test_live_meic, test_env_fallback, test_store):
        t()
    print(f"\nALL {PASS} CHECKS PASSED")
    sys.exit(0)
