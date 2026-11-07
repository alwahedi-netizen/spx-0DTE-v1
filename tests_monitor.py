"""Tests for live_monitor.py (cost analysis + drift). python3 tests_monitor.py"""
import live_monitor as lm

L = lambda pid, cf, xf, pnl, status="CLOSED", oid="1", cid="2", q="1": {
    "position_id": pid, "credit_fill": cf, "close_fill": xf, "pnl_live": pnl, "status": status,
    "order_id": oid, "close_order_id": cid, "qty": q}
P = lambda pid, ct, ev, pnl: {"position_id": pid, "credit_theo": ct, "exit_value_theo": ev, "pnl_theo": pnl, "contracts": "1"}

# pnl_live is NET of fees, as live_meic writes it (gross - $1.18/leg)
live = [L("2026-11-02-MEIC-12:00-PUT", "1.90", "0.10", "175.28"),           # 10c worse in, 5c worse out
        L("2026-11-02-MEIC-12:30-PUT", "2.00", "", "197.64", status="EXPIRED", cid=""),
        L("2026-11-02-MEIC-13:00-PUT", "2.00", "", "200.00", oid="dry-1"),    # rehearsal: ignored
        L("2026-11-03-ORB-PUT", "-9.30", "-4.40", "-494.72")]               # debit: paid 5c more, got 13c less
paper = [P("2026-11-02-MEIC-12:00-PUT", "2.00", "0.05", "195.00"),
         P("2026-11-02-MEIC-12:30-PUT", "2.00", "0.00", "200.00"),
         P("2026-11-02-MEIC-13:00-PUT", "2.00", "0.00", "200.00"),
         P("2026-11-03-ORB-PUT", "-9.25", "-4.53", "-472.00")]
rows = lm.pairs(live, paper)
assert len(rows) == 3, "dry-run rows excluded"
m = rows[0]
assert m["entry_slip"] == 10.0 and m["exit_slip"] == 5.0 and m["fees"] == 4.72
assert m["shortfall"] == round(195.0 - 175.28, 2) and m["live_net"] == 175.28   # fees counted once
o = [r for r in rows if r["strategy"] == "ORB"][0]
assert o["entry_slip"] == 5.0 and o["exit_slip"] == 13.0, o        # debit trades: + is still cost
e = rows[1]
assert e["exit_slip"] is None and e["fees"] == 2.36
print("  ✓ slippage signs (credit and debit), fees by legs, dry runs excluded")

drift_live = [L(f"2026-11-{d:02d}-MEIC-12:00-PUT", "1.50", "1.00", "-60.00") for d in range(1, 21)]
drift_paper = [P(f"2026-11-{d:02d}-MEIC-12:00-PUT", "2.00", "0.00", "200.00") for d in range(1, 21)]
rep = lm.summarize(lm.pairs(drift_live, drift_paper))
assert any("DRIFT" in f for f in rep["MEIC"]["flags"]) and rep["MEIC"]["recent"]["capture"] < 0.5
ok_live = [L(f"2026-11-{d:02d}-MEIC-12:00-PUT", "2.00", "", "200.00", status="EXPIRED", cid="") for d in range(1, 21)]
assert lm.summarize(lm.pairs(ok_live, drift_paper))["MEIC"]["flags"] == []
print("  ✓ drift flagged when live keeps < 50% of the paper edge; clean when it tracks")

rep = lm.build()
assert "MEIC" in rep and rep["MEIC"]["all"]["trades"] > 100
print("  ✓ runs on the real ledger:", rep["MEIC"]["all"]["trades"], "MEIC trades")
print("\nALL MONITOR CHECKS PASSED")
