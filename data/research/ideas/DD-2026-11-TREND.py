"""DD-2026-11-TREND — monthly deep dive #1 (RESEARCH.md §4c): time-series trend,
classic published forms, same rules on every asset class we have honest daily
data for. Fixed before the first run:
  SMA10 : at each month-end close, hold the asset next month if its close is
          above the average of the last 10 month-end closes; else T-bills
          (Faber 2007).
  MOM12 : hold next month if the return from 12 months ago to 1 month ago is
          positive; else T-bills (Moskowitz-Ooi-Pedersen 12-1).
Benchmark = buy & hold of the same asset; strict bar (§4); 5bp (10bp crypto).
trials = every (asset, rule) run. Caveats: futures (GC=F, CL=F) are front-month
continuous prices (roll yield not captured); FX is spot only (no interest carry)."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

CLASSES = {
    "equities": [("VFINX", "1986-01-01"), ("NAESX", "1987-01-01"), ("VGTSX", "1997-01-01"),
                 ("VEIEX", "1995-01-01"), ("QQQ", "2000-01-01")],
    "bonds": [("VUSTX", "1987-01-01"), ("VFITX", "1992-01-01")],
    "commodities": [("GC=F", "2001-01-01"), ("CL=F", "2001-01-01"), ("DBC", "2007-01-01")],
    "fx": [("EURUSD=X", "2004-01-01"), ("GBPUSD=X", "2004-01-01"), ("AUDUSD=X", "2007-01-01")],
    "crypto": [("BTC-USD", "2015-06-01"), ("ETH-USD", "2018-06-01")],
}


def make(rule, sym):
    st = {"w": None}

    def month_end_closes(i, dates, px):
        out = []
        for k in range(1, i + 1):
            if dates[k][:7] != dates[k - 1][:7] and px[sym][k - 1]:
                out.append(px[sym][k - 1])
        if px[sym][i]:
            out.append(px[sym][i])          # today is a month-end (caller checks)
        return out

    def weights(i, dates, px):
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            if rule == "SMA10":
                me = month_end_closes(i, dates, px)
                on = len(me) >= 10 and me[-1] > sum(me[-10:]) / 10
            else:
                on = (i >= 252 and px[sym][i - 252] and px[sym][i - 21]
                      and px[sym][i - 21] / px[sym][i - 252] - 1 > 0)
            st["w"] = {sym: 1.0} if on else {}
        return st["w"] if st["w"] is not None else {}
    return weights


if __name__ == "__main__":
    runs = [(c, s, start, r) for c, lst in CLASSES.items() for s, start in lst for r in ("SMA10", "MOM12")]
    out = {}
    for c, s, start, r in runs:
        res = rb.evaluate(f"DD-2026-11-TREND-{r}-{s}", make(r, s), [s], s, start=start,
                          cost_bps=10.0 if c == "crypto" else 5.0, trials=len(runs), save=False,
                          notes=f"{r} on {s} ({c})")
        out.setdefault(c, []).append(res)
        print(f"{c:11s} {s:9s} {r:5s} {res['period'][0][:4]}+ idea {res['idea_cagr']:+.1%} vs B&H {res['bench_cagr']:+.1%} | "
              f"DD {res['idea_maxdd']:.0%} vs {res['bench_maxdd']:.0%} | Sharpe {res['idea_sharpe']:.2f} vs {res['bench_sharpe']:.2f} | "
              f"conf {res['confidence']:.0%} | held-out {res['oos_idea_sharpe']:.2f} vs {res['oos_bench_sharpe']:.2f} | {res['verdict']}")
    rb.RESULTS.mkdir(parents=True, exist_ok=True)
    (rb.RESULTS / "DD-2026-11-TREND.json").write_text(json.dumps(
        {"idea": "DD-2026-11-TREND", "track": "deep-dive", "trials": len(runs), "classes": out}, indent=1))
