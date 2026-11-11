"""R-2026-11-11-FFTERM — the term spread forecasts corporate-bond returns
(Fama & French, "Business conditions and expected returns on stocks and
bonds", JFE 25(1) 1989), scripted from the bond queue (I-2026-11-10-FFTERM).

SOURCE: https://doi.org/10.1016/0304-405X(89)90095-0 (Fama-French 1989).
Finding (1927-1987): the term spread (long minus short yield) is high near
business-cycle troughs and low near peaks, and it forecasts the excess
returns of stocks AND of corporate bonds of every grade; expected returns
are high when conditions are poor. The signal is the spread RELATIVE TO ITS
NORMAL LEVEL, not its sign.

VARIES: R-2026-11-07-TSCARRY (graveyard: VUSTX when 10y-3m > 0 was a near
copy of its benchmark, Sharpe 0.302 vs 0.305). Two differences that matter:
(1) the asset is investment-grade corporates (term + credit premium, which
F-F find the spread predicts), not long Treasuries; (2) the threshold is
the spread's own trailing mean (steeper than normal), not zero, so the rule
is out of credit for long stretches of a merely positive curve.

RATIONALE (written before any run): a steep curve is the market pricing a
recovery from poor conditions; required returns on duration and credit are
high then (F-F, Cochrane-Piazzesi, Cieslak-Povala all find slope-type
variables predict bond excess returns). Holding LQD only when the curve is
steeper than its 5-year mean should earn the premium in the high-premium
states and park in short Treasuries otherwise. Counter-evidence logged
before the run: TSCARRY's failure, and Acadian 2025 (most spread-timing
rules lose out-of-sample). Expected weakness: a steep curve in 2008 H2
(cuts) while credit crashed — the rule may hold LQD into the 2008 drop.

RULE (fixed before any run):
  * On the first trading day of each month (weights at that close), from
    the PREVIOUS month-end: slope = ^TNX - ^IRX (Yahoo, percent; the last
    valid print on or before that month-end). Mean = average of slope at
    the last WIN = 60 month-ends (including that one).
  * slope > mean + THR (THR = 0) -> LQD 1.0 for the month, else SHY 1.0.
  * Month-end yields are read from Yahoo's full ^TNX / ^IRX history (1985+,
    loaded once outside the price panel) but ONLY for month-ends strictly
    before the decision month, so the 60-month mean exists from the start;
    the queue's "warm-up AGG" never triggers.
Benchmark: AGG buy & hold. Costs 3bp. Start 2003-10-01 (AGG listed
2003-09-29; LQD/SHY 2002-07). Includes 2008, 2013, 2020, 2022.
Variants (4): WIN 36 and 120 month-ends; THR = plain positive slope
(slope > 0, no mean); IEF instead of LQD (term premium only).
trials = 10 = TSCARRY's 5 (the same slope-signal family) + this run's 5.
Own family "R-2026-11-11-FFTERM" (the harness adds the TSCARRY count only
through the trials= floor).
DATA TIMING: ^TNX / ^IRX are end-of-day CBOE yield indices; the signal uses
the prior month-end close for a trade at the next day's close (no FRED, no
revised data).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-11-FFTERM"
BENCH = "AGG"
_CURVE = {}


def month_end_slopes():
    """{'YYYY-MM': slope at that month's last valid ^TNX/^IRX prints}."""
    if not _CURVE:
        d, p = rb.prices(["^TNX", "^IRX"], "1985-01-01")
        last_t = last_b = None
        for k, day in enumerate(d):
            t, b = p["^TNX"][k], p["^IRX"][k]
            if t is not None:
                last_t = t
            if b is not None:
                last_b = b
            if last_t is not None and last_b is not None:
                _CURVE[day[:7]] = last_t - last_b     # overwritten until month-end
        # the current (incomplete) month is never read: see weights()
    return _CURVE


def _prev_month(ym, k=1):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def make(win=60, thr=0.0, plain=False, credit="LQD", short="SHY"):
    st = {}

    def reset():
        st.clear()
        st.update(w={})

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        first = i == 0 or dates[i][:7] != dates[i - 1][:7]
        if not first:
            return st["w"]
        curve = month_end_slopes()
        ym = _prev_month(dates[i][:7])                # last COMPLETE month
        hist = [curve.get(_prev_month(ym, k)) for k in range(win)]
        hist = [h for h in hist if h is not None]
        s = curve.get(ym)
        if s is None or len(hist) < int(0.9 * win):
            st["w"] = {BENCH: 1.0} if px[BENCH][i] else {}
            return st["w"]
        on = s > thr if plain else s > sum(hist) / len(hist) + thr
        sym = credit if on else short
        st["w"] = {sym: 1.0} if px[sym][i] else {}
        return st["w"]
    return weights


weights = make()

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, ["LQD", "SHY", "IEF"], BENCH, start="2003-10-01",
                    asset_class="bonds", trials=10, family=ID,
                    variants={"WIN36": make(36), "WIN120": make(120),
                              "PLAIN0": make(60, 0.0, True), "IEF": make(60, 0.0, False, "IEF")},
                    notes="first trading day of each month: (^TNX-^IRX at the prior month-end) > its "
                          "mean over the last 60 month-ends -> LQD, else SHY; bench AGG; 2003-10+; "
                          "Fama-French 1989 term spread, varies TSCARRY")
    print(json.dumps(r, indent=1))
