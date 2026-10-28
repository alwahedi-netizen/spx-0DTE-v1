"""R-2026-10-28-HFEA — "Hedgefundie's Excellent Adventure", as published:
55% UPRO (3x S&P 500) / 45% TMF (3x 20+yr Treasuries), rebalanced quarterly.
Source: Bogleheads 2019 thread; retested by Quanter Lab 2026-10-18.
Rules fixed BEFORE the run from the published config (no tuning, trials=1).
The 3x funds are SIMULATED from SPY/TLT so the test covers 2002+ incl. 2008:
daily 3x return - 2x T-bill financing - 0.95%/yr expense ratio. The harness
holds the two simulated funds and rebalances to 55/45 on the first trading
day of each quarter (weights drift in between: no daily turnover)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ER = 0.0095


def synth_fetch(sym):
    if sym not in ("UPRO_SIM", "TMF_SIM"):
        return rb._fetch(sym)
    base = rb._fetch("SPY" if sym == "UPRO_SIM" else "TLT")
    irx = rb._fetch("^IRX")
    out, lvl, prev, last_rf = {}, 100.0, None, 0.0
    for d in sorted(base):
        if irx.get(d) is not None:
            last_rf = irx[d] / 100 / 252
        if prev is not None:
            lvl *= 1 + 3 * (base[d] / prev - 1) - 2 * last_rf - ER / 252
        out[d] = lvl
        prev = base[d]
    return out


TARGET = {"UPRO_SIM": 0.55, "TMF_SIM": 0.45}
state = {"w": None, "i": None}


def weights(i, dates, px):
    q = lambda d: (d[:4], (int(d[5:7]) - 1) // 3)
    if state["w"] is None or q(dates[i]) != q(dates[i - 1]):
        state["w"], state["i"] = dict(TARGET), i
        return dict(TARGET)
    i0 = state["i"]            # drift the quarter's weights with prices
    v = {s: w * px[s][i] / px[s][i0] for s, w in state["w"].items()}
    tot = sum(v.values())
    return {s: x / tot for s, x in v.items()}


if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-10-28-HFEA", weights, list(TARGET), "SPY", start="2002-08-01",
                    cost_bps=5.0, trials=1, fetch=synth_fetch,
                    notes="55% sim-UPRO / 45% sim-TMF, quarterly rebalance, 2002+ incl. 2008 and 2022")
    print(json.dumps(r, indent=1))
