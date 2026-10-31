"""R-2026-10-31-YCURVE — yield-curve inversion timing (scan of 2026-10-31).
Source: CXO Advisory "Yield Curve as a Stock Market Indicator" (2026-10-26;
rules paywalled) -> the standard published form (Estrella & Mishkin 1998
10y-minus-3m recession signal), fixed BEFORE the first run, trials=1:
  at each month's first close, hold the S&P 500 (VFINX, dividends included)
  unless the 10-year yield (^TNX) is below the 13-week T-bill (^IRX) at the
  previous close -> then hold T-bills (cash) for the month.
Strict trading-signal bar (RESEARCH.md §4), benchmark VFINX, 5bp costs, 1986+."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

state = {"w": None}


def weights(i, dates, px):
    if state["w"] is None or dates[i][:7] != dates[i - 1][:7]:
        tnx, irx = px["^TNX"][i], px["^IRX"][i]
        inverted = tnx is not None and irx is not None and tnx < irx
        state["w"] = {} if inverted else {"VFINX": 1.0}
    return state["w"]


if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-10-31-YCURVE", weights, ["VFINX", "^TNX", "^IRX"], "VFINX",
                    start="1986-01-01", cost_bps=5.0, trials=1,
                    notes="S&P 500 unless 10y < 3m T-bill at month start (then T-bills); monthly; 1986+")
    print(json.dumps(r, indent=1))
