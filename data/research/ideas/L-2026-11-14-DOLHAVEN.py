"""L-2026-11-14-DOLHAVEN — the DOLLAR as the crisis currency: UUP only while the
S&P 500 is below its 10-month SMA, else T-bills (lab original, RESEARCH.md
§2b: a shortlist block applied to a new instrument).

INGREDIENTS:
  * DD-2026-11-TREND (potential 5): SPY below its 10-month SMA = bear state.
  * L-2026-11-07-SAFEHAVEN (yen + franc in the same bear state; potential 4
    before harness fix 2, its family's sleeves fell after it). Its learnings
    row: it fails in rate-driven bears when the yen falls with stocks (2022).
    The dollar is the currency that ROSE in exactly those bears.
  * Lilley, Maggiori, Neiman & Schreger, "Exchange Rate Reconnect", Review of
    Economics and Statistics 104(4) 2022 (https://www.nber.org/papers/w26046):
    since 2007 the dollar appreciates when global risk appetite falls (risk
    measures explain a meaningful share of all post-2007 exchange-rate
    variation; none before). Maggiori, "Financial Intermediation,
    International Risk Sharing, and Reserve Currencies", AER 2017: the reserve
    currency appreciates in global crises.
RATIONALE (written before any run): in global risk-off, dollar funding
demand (foreign banks' and corporates' dollar liabilities, safe-asset demand
for Treasuries) lifts the dollar against the DXY basket (mostly EUR). Bear
states persist for months, so a month-end trend reading of equities is a
tradeable, lagged proxy for the risk-off regime. Unlike Treasuries the dollar
also rose in the 2022 inflation bear, so it should hedge when the stock-bond
correlation is positive — the one regime the rest of the book (rates
calendar, Treasuries, yen/franc) does not cover.
COUNTER-HYPOTHESIS (on the record): the post-2007 link is contemporaneous;
it may not survive a one-month lag (2009 H1 and 2020 Q2: the dollar fell
while SPY was still below its SMA). The sealed vault holds April 2025, when
the dollar FELL with stocks (tariff shock) — a known adverse event.

PASS CRITERION (pre-registered): the research_bt verdict vs T-bills (§4 +
world-class gates). Expected FAIL on t >= 3 (in the market ~25% of months).
Building-block claim (potential >= 3), judged on this run's traits: positive
active return overall AND in the recent half, worst drop no worse than -15%,
and correlation <= 0.3 to SPY; the lead's portfolio.marginal decides fit.
DATA-TIMING: the bear flag reads SPY's close on the last trading day of each
month (bar i) and the previous month-end closes; no `=X` data is used (UUP and
SPY are both 4pm New York closes). Weights decided at close i earn close i ->
close i+1 in UUP; held through the next month-end.
RULE (fixed before any run):
  * At each month-end close: bear = SPY < mean of its last N month-end closes
    (N = 10, the DD-TREND default, incl. the current one, as SAFEHAVEN).
  * bear -> UUP 100% next month; else T-bills. Before N month-ends or with no
    UUP price: T-bills.
  * Variants: N = 8, 9, 11, 12.
Instruments: Invesco DB US Dollar Index Bullish (UUP: long USDX futures +
T-bill collateral, so it earns its rate gap and the harness cash accounting
is exact; Schwab-tradeable). Benchmark T-bills; asset_class "fx" (2bp).
Start 2007-03-01 (UUP lists 2007-02-20). FAMILY "L-fx-safehaven" (same
hypothesis: hold the haven currency in equity bear states; results files show
42 lifetime trials) -> honest trials 47. Never vault.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "L-2026-11-14-DOLHAVEN"
SYMS = ["UUP", "SPY"]


def make(n_months=10):
    st = {"w": {}, "spy": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["spy"] = {}, []                # evaluate() re-simulates
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end:
            if px["SPY"][i]:
                st["spy"].append(px["SPY"][i])
            s = st["spy"]
            bear = len(s) >= n_months and s[-1] < sum(s[-n_months:]) / n_months
            st["w"] = {"UUP": 1.0} if bear and px["UUP"][i] else {}
        return st["w"]
    return weights


weights = make(10)
VARIANTS = {"SMA8": make(8), "SMA9": make(9), "SMA11": make(11), "SMA12": make(12)}

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, SYMS, None, start="2007-03-01", asset_class="fx",
                    trials=47, family="L-fx-safehaven", variants=VARIANTS,
                    notes="UUP 100% only when SPY < 10-mo SMA (month-end), else T-bills; the dollar "
                          "as the crisis currency (Lilley-Maggiori-Neiman-Schreger 2022); same "
                          "family as SAFEHAVEN (yen/franc)")
    print(json.dumps(r, indent=1))
