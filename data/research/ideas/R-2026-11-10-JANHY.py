"""R-2026-11-10-JANHY — scripts the queued I-2026-11-09-JANHY (scored 70):
the January seasonal in high-yield bonds, on tradeable ETFs.

SOURCE: Chang & Pinegar, "Return seasonality and tax-loss selling in the
market for long-term government and corporate bonds", JFE 17(2) 1986,
391-415 (https://ideas.repec.org/a/eee/jfinec/v17y1986i2p391-415.html):
low-grade corporate bonds earn abnormal returns in January (tax-loss
selling and window dressing in December, then reversal). Government and
high-grade bonds show no January effect. Counter-evidence (read
2026-11-10): Zaremba & Schabek, RIBAF 41 (2017)
(https://ideas.repec.org/a/eee/riibaf/v41y2017icp292-302.html) find no
January effect in 25 government-bond markets (1992-2016). That does not
contradict a high-yield-only effect, but it lowers the prior. KNOWLEDGE
theme 4 also applies: published calendar anomalies decay.

RATIONALE (written before any run): high-yield bonds are held by
tax-sensitive and window-dressing investors who sell losers in December.
Dealer balance sheets shrink at year-end, so the selling pressure reverses
in January. ETF-era HY (HYG) is far more liquid than 1980s bonds, so we
expect the effect to be smaller. This is a test of whether it survives at all.

RULE (fixed before any run; identical to the 2026-11-09 ledger row):
  * Weights decided at close i: HYG 1.0 if the NEXT bar (i+1) is in
    January (earns the last December close -> the last January close),
    else IEI 1.0. Only the calendar is read ahead, never prices.
  * Before HYG trades: AGG.
Benchmark: AGG buy & hold. Costs 3bp. 2007-05+ (HYG 2007-04-11; IEI
2007-01). First January held: 2008 (17 Januaries to the vault).
Variants (calendar neighbours): first 10 trading days of January only;
last 10 trading days of December + January; December + January; January
+ February. trials = 5 (new family).
Known weakness, stated now: 11 months a year it is IEI, so it may miss the
0.10 Sharpe-materiality gate even if January is real. The real question is
the January active return (HYG - IEI): report it from the daily series. If
it is positive, the idea goes on as a WINDOW inside a credit calendar book
(L-2026-11-08-EOMCREDIT).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-10-JANHY"
RISK, SAFE, BENCH = "HYG", "IEI", "AGG"


def _month_pos(dates):
    """(position from start, position from end) of each bar in its month."""
    first, last = [0] * len(dates), [0] * len(dates)
    k = 0
    while k < len(dates):
        j = k
        while j + 1 < len(dates) and dates[j + 1][:7] == dates[k][:7]:
            j += 1
        for t in range(k, j + 1):
            first[t], last[t] = t - k, j - t
        k = j + 1
    return first, last


def make(mode="JAN"):
    st = {"key": None}

    def in_window(t, dates):
        m = dates[t][5:7]
        if mode == "JAN":
            return m == "01"
        if mode == "J10":
            return m == "01" and st["first"][t] < 10
        if mode == "D10J":
            # last-10 of December only when the December is complete in the sample
            return m == "01" or (m == "12" and st["last"][t] < 10 and t + st["last"][t] + 1 < len(dates))
        if mode == "DJ":
            return m in ("12", "01")
        if mode == "JF":
            return m in ("01", "02")
        raise ValueError(mode)

    def weights(i, dates, px):
        if i == 0 or st["key"] != (len(dates), dates[0]):
            st["key"] = (len(dates), dates[0])
            st["first"], st["last"] = _month_pos(dates)
        if i + 1 < len(dates):
            h = RISK if in_window(i + 1, dates) else SAFE
            if px[h][i]:
                return {h: 1.0}
        return {BENCH: 1.0} if px[BENCH][i] else {}
    return weights


weights = make("JAN")

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [RISK, SAFE], BENCH, start="2007-05-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={v: make(v) for v in ("J10", "D10J", "DJ", "JF")},
                    notes="HYG from the last December close to the last January close, IEI "
                          "otherwise; bench AGG; 2007-05+; Chang-Pinegar JFE 1986; scripts "
                          "I-2026-11-09-JANHY")
    print(json.dumps(r, indent=1))
