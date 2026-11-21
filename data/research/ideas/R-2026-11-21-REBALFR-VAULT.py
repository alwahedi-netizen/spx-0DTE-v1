"""ONE-TIME VAULT TEST of R-2026-11-21-REBALFR (family R-2026-11-21-REBALFR),
per RESEARCH.md §2b, after the lead's red team returned "SURVIVES WITH CAVEATS"
(2026-11-21; scratchpad league2/redteam/REBALFR_redteam.md).

PASS CRITERION (pre-registered 2026-11-21 by the lead BEFORE this file ran,
copied from the red team's proposal):
  (a) vault-only (2024-11-01 -> latest) Sharpe vs T-bills > 0 at the harness's
      3bp/side bond cost, AND
  (b) positive excess return over T-bills over 2025-04-01..2025-04-30 (the
      tariff-shock stress month).
Failing either kills it. Same rule, same parameters, same variants as the
development run; the harness logs the family in results/vault_log.json so it
can never run twice.
DATA-TIMING: unchanged from R-2026-11-21-REBALFR (signal from closes through i,
weights decided at close i earn i -> i+1; requires market-on-close execution).
"""
import importlib.util, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb
spec = importlib.util.spec_from_file_location("rbf", HERE / "R-2026-11-21-REBALFR.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
if __name__ == "__main__":
    r = rb.evaluate(m.ID + "-VAULT", m.weights, [m.EQ, m.BD], None, start="2002-08-01",
                    asset_class="bonds", trials=5, family=m.ID, vault=True,
                    variants={"DELTA_0_20": m.make(deltas=[k / 1000 for k in range(0, 21)]),
                              "DELTA_01_25": m.make(deltas=[k / 1000 for k in range(1, 26)]),
                              "WEEK_LAST4": m.make(week_n=4),
                              "THR_SCALE_2": m.make(scale=0.02)},
                    notes="VAULT TEST (one-time) of REBALFR; criterion: vault Sharpe vs T-bills > 0 at 3bp "
                          "AND positive excess over T-bills in April 2025")
    dates, px = rb.prices([m.EQ, m.BD], "2002-08-01")
    rf = rb.tbill(dates)
    rets, _ = rb.simulate(m.weights, dates, px, rf, rb.COST_BPS.get("bonds", 3.0))
    d1 = dates[1:]; rf1 = rf[1:]
    k = next(i for i, d in enumerate(d1) if d >= rb.VAULT_FROM)
    v, vrf = rets[k:], rf1[k:]
    eq = lambda x: __import__("functools").reduce(lambda a, b: a * (1 + b), x, 1.0) - 1
    apr = [(x, y) for d, x, y in zip(d1, rets, rf1) if "2025-04-01" <= d <= "2025-04-30"]
    apr_ex = eq([a for a, _ in apr]) - eq([b for _, b in apr])
    vs = rb.sharpe(v, vrf)
    out = {"vault_from": d1[k], "vault_to": d1[-1], "days": len(v),
           "idea_total": round(eq(v), 4), "tbill_total": round(eq(vrf), 4),
           "vault_sharpe_vs_tbills": round(vs, 3), "april_2025_excess": round(apr_ex, 4),
           "crit_a": vs > 0, "crit_b": apr_ex > 0, "criterion_pass": bool(vs > 0 and apr_ex > 0),
           "harness_verdict": r["verdict"], "harness_gates": r["gates"],
           "full_sharpe": r["idea_sharpe"], "full_cagr": r["idea_cagr"]}
    Path(HERE.parent / "results" / "R-2026-11-21-REBALFR-VAULT-stretch.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
