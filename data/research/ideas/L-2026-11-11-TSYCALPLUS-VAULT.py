"""ONE-TIME VAULT TEST of L-2026-11-11-TSYCALPLUS (family L-TSYCAL), per
RESEARCH.md §2b after a red-team "survives with caveats" (2026-11-11).
Criterion pre-registered in L-2026-11-11-TSYCALPLUS.py's header before this
ran: vault-only (2024-11-01 -> latest) active return vs IEF > 0, net of
financing and costs. Same rule, same parameters, same variants; the harness
logs the family in results/vault_log.json so it can never run twice."""
import importlib.util, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import research_bt as rb
spec = importlib.util.spec_from_file_location("tcp", HERE / "L-2026-11-11-TSYCALPLUS.py")
tcp = importlib.util.module_from_spec(spec); spec.loader.exec_module(tcp)
if __name__ == "__main__":
    rb.simulate = tcp.spread_simulate
    try:
        r = rb.evaluate(tcp.ID + "-VAULT", tcp.weights, [tcp.SYM], tcp.SYM, start="2002-08-01",
                        asset_class="bonds", trials=20, family="L-TSYCAL", vault=True,
                        variants={"OV050": tcp.make(0.5, 3), "OV150": tcp.make(1.5, 3),
                                  "EOM2": tcp.make(1.0, 2), "EOM4": tcp.make(1.0, 4)},
                        notes="VAULT TEST (one-time) of TSYCALPLUS; criterion: vault-only active return vs IEF > 0")
        # vault-only stretch, same simulation
        dates, px = rb.prices([tcp.SYM], "2002-08-01")
        rf = rb.tbill(dates)
        rets, _ = rb.simulate(tcp.make(1.0, 3), dates, px, rf, rb.COST_BPS.get("bonds", 5.0))
    finally:
        rb.simulate = tcp._ORIG_SIM
    bret = rb.bench_returns(tcp.SYM, dates, px, rf)
    k = next(i for i, d in enumerate(dates[1:]) if d >= rb.VAULT_FROM)
    v, vb, vrf = rets[k:], bret[k:], rf[1:][k:]
    eq = lambda x: __import__("functools").reduce(lambda a, b: a * (1 + b), x, 1.0) - 1
    out = {"vault_from": dates[1:][k], "vault_to": dates[-1], "days": len(v),
           "idea_total": round(eq(v), 4), "ief_total": round(eq(vb), 4),
           "active_total": round(eq(v) - eq(vb), 4),
           "idea_sharpe": round(rb.sharpe(v, vrf), 3), "ief_sharpe": round(rb.sharpe(vb, vrf), 3),
           "criterion_pass": eq(v) > eq(vb), "harness_verdict": r["verdict"],
           "harness_gates": r["gates"], "full_cagr": r["idea_cagr"], "full_bench_cagr": r["bench_cagr"]}
    Path(HERE.parent / "results" / "L-2026-11-11-TSYCALPLUS-VAULT-stretch.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
