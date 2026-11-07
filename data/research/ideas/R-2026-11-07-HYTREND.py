"""R-2026-11-07-HYTREND — high-yield bond trend timing (200-day moving average).
Sources: Bektic & Regele, "Moving-average timing in corporate bonds" (EFMA 2017
working paper; Darmstadt WP 92506):
https://efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2017-Athens/papers/EFMA2017_0289_fullpaper.pdf
and the practitioner rule run live by Counterpoint Funds ("Trend Following in
High Yield: Appearances Can Be Deceiving"):
https://counterpointfunds.com/trend-following-in-high-yield-appearances-can-be-deceiving/

NOT a repeat of DD-2026-11-TREND: that deep dive timed TREASURY funds (VUSTX,
VFITX) with a 10-month SMA / 12-1 rule and found nothing. This times CREDIT
(high yield), whose returns are autocorrelated for a reason Treasuries lack:
illiquid, slowly-repriced bonds (stale marks) and slow diffusion of default
news. Bektic-Regele find the timing gain strongest where information
uncertainty is highest (HY, wide spreads). The risk-off leg is Treasuries, so
the switch also captures flight-to-quality.

RULE (fixed before any run; Counterpoint's published default):
  each day, if the high-yield fund's close YESTERDAY (i-1) is above its simple
  average of the 200 closes ending yesterday, hold the high-yield fund
  (VWEHX, Vanguard High-Yield Corporate) at today's close; otherwise hold
  intermediate Treasuries (VFITX, Vanguard Intermediate-Term Treasury; the
  source uses 3-5y Treasuries). One-day signal lag = no same-close trading.
  Warm-up (first 200 days): hold the benchmark.
Benchmark: VBMFX (Vanguard Total Bond Market Index) = AGG proxy (AGG is 2003+).
Costs: 3bp/unit turnover (bonds). 1992+ (VFITX starts 1991-10).
Variants (robustness gate): SMA 100 / 150 / 250 / 300 days. trials = 5
(1 published default + 4 neighbours; the source's own robustness table spans
similar windows).
Red-team flags to check: mutual-fund NAV staleness (HY fund NAVs are partly
stale, which makes yesterday's trend partly a forecast of today's NAV — the
ETF version HYG/IEI 2007+ is the tradeable one; Vanguard also limits round
trips within 30 days); does 2008 alone carry it?"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

HY, SAFE, BENCH = "VWEHX", "VFITX", "VBMFX"


def make(n=200):
    def weights(i, dates, px):
        if i < n or px[SAFE][i] is None:
            return {BENCH: 1.0}
        c = [x for x in px[HY][i - n:i] if x]          # closes i-n .. i-1
        if len(c) < int(0.95 * n):
            return {BENCH: 1.0}
        return {HY: 1.0} if c[-1] > sum(c) / len(c) else {SAFE: 1.0}
    return weights


weights = make(200)

if __name__ == "__main__":
    import json
    r = rb.evaluate("R-2026-11-07-HYTREND", weights, [HY, SAFE, BENCH], BENCH,
                    start="1992-01-02", asset_class="bonds", trials=5,
                    family="R-2026-11-07-HYTREND",
                    variants={f"sma{n}": make(n) for n in (100, 150, 250, 300)},
                    notes="VWEHX if its close (i-1) > 200-day SMA else VFITX; daily, 1-day lag; "
                          "bench VBMFX (AGG proxy); 1992+")
    print(json.dumps(r, indent=1))
