"""R-2026-11-07-TOY — turn-of-the-year small-cap effect (Keim 1983; Reinganum).
Source this week: CXO Advisory 2026-11-03 (Russell 2000 vs S&P 500, +-20 days).
Rule fixed before the run (trials=1): from 20 trading days before the last
trading day of December to 20 trading days after it, long Russell 2000 (^RUT)
and short S&P 500 (^GSPC), equal dollars; otherwise flat (T-bills). Both are
price indices (no dividends) so the spread is like-for-like. Market-neutral:
benchmark T-bills; 5bp per leg; 1988+."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_win = {}


def _windows(dates):
    if not _win:
        last_dec = [k for k in range(len(dates) - 1)
                    if dates[k][5:7] == "12" and dates[k + 1][:4] != dates[k][:4]]
        for k in last_dec:
            for j in range(max(0, k - 20), min(len(dates), k + 21)):
                _win[j] = True
    return _win


def weights(i, dates, px):
    # decided at close i for the move i -> i+1: in the window if day i+1 is
    return {"^RUT": 1.0, "^GSPC": -1.0} if _windows(dates).get(i + 1) else {}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate("R-2026-11-07-TOY", weights, ["^RUT", "^GSPC"], None, start="1988-01-01",
                                 cost_bps=5.0, trials=1,
                                 notes="long Russell 2000 / short S&P 500, 20 days either side of year-end; 1988+"), indent=1))
