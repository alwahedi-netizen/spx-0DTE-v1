"""R-2026-10-28-HFEA (allocation track) — Hedgefundie 55/45 re-judged on
rolling 10- and 20-year windows (owner 2026-10-28). Same published rules as
R-2026-10-28-HFEA.py; longer history so 20-year windows exist:
  3x S&P 500 simulated from VFINX (Vanguard 500, total return, 1985+)
  3x long Treasuries simulated from VUSTX (Vanguard Long-Term Treasury, 1986+;
  duration ~15y vs TMF's ~17y, a slightly milder stand-in)
  daily 3x return - 2x T-bill financing - 0.95%/yr expense; quarterly 55/45.
Benchmark: VFINX (S&P 500 with dividends). Rules unchanged, trials=1."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ER = 0.0095
BASE = {"UPRO_SIM": "VFINX", "TMF_SIM": "VUSTX"}


def synth_fetch(sym):
    if sym not in BASE:
        return rb._fetch(sym)
    base, irx = rb._fetch(BASE[sym]), rb._fetch("^IRX")
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
    if px["TMF_SIM"][i] is None or px["UPRO_SIM"][i] is None:
        return {}
    q = lambda d: (d[:4], (int(d[5:7]) - 1) // 3)
    if state["w"] is None or q(dates[i]) != q(dates[i - 1]):
        state["w"], state["i"] = dict(TARGET), i
        return dict(TARGET)
    i0 = state["i"]
    v = {s: w * px[s][i] / px[s][i0] for s, w in state["w"].items()}
    tot = sum(v.values())
    return {s: x / tot for s, x in v.items()}


if __name__ == "__main__":
    import json
    r = rb.evaluate_allocation("R-2026-10-28-HFEA-ALLOC", weights, list(TARGET), "VFINX",
                               start="1986-06-02", cost_bps=5.0, trials=1, fetch=synth_fetch,
                               notes="Allocation track: 55% sim-3x S&P / 45% sim-3x long Treasuries (VFINX/VUSTX), quarterly, 1986+")
    r.pop("calendar_years")
    print(json.dumps(r, indent=1))
