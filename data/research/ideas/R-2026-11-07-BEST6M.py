"""R-2026-11-07-BEST6M — "Best six months" (Hirsch 1986; Bouman & Jacobsen 2002
"Sell in May"). Source this week: Quantifiable Edges, 2026-11-02.
Rule fixed before the run (trials=1): hold the S&P 500 (VFINX, dividends) for
November-April, T-bills for May-October; switch at the last close of April /
October. Strict trading-signal bar vs VFINX buy & hold, 5bp, 1986+."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb


def weights(i, dates, px):
    nxt = dates[i + 1] if i + 1 < len(dates) else dates[i]   # calendar only, no prices
    m = int(nxt[5:7])
    return {"VFINX": 1.0} if (m >= 11 or m <= 4) else {}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate("R-2026-11-07-BEST6M", weights, ["VFINX"], "VFINX", start="1986-01-01",
                                 cost_bps=5.0, trials=1,
                                 notes="S&P 500 Nov-Apr, T-bills May-Oct; 1986+"), indent=1))
