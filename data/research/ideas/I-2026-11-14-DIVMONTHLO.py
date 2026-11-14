"""I-2026-11-14-DIVMONTHLO — long-only form of R-2026-11-14-DIVMONTH: hold
only the S&P 500 stocks expected to go ex-dividend this month, vs SPY.

This is the queue row I-2026-11-08-DIVMONTH's own rule (long-only, monthly)
and the form a Schwab account trades without shorting 300 names.
Source: Hartzmark & Solomon (2013) JFE 109(3) 640-660
(https://econpapers.repec.org/RePEc:eee:jfinec:v:109:y:2013:i:3:p:640-660);
CXO summary (https://www.cxoadvisory.com/?p=16926): LONG ALL EXPECTED
PAYERS earns 0.41%/month equal-weighted (0.24% value-weighted) factor-
adjusted alpha, CRSP 1927-2009.
RUNS ONLY IF DIVMONTH REPLICATES (RESEARCH.md § LEAGUE rule 1): the script
first runs DIVMONTH.replication_check() and refuses (no evaluate, no
trial) if the hedged spread does not reproduce.

RATIONALE (fixed before any run): as DIVMONTH — dividend-seeking demand
lifts expected payers in their dividend month. Long-only keeps full equity
beta plus the payer/value and equal-weight tilts, which the FF5+Mom alpha
gate strips out; the question is whether the calendar pressure survives as
alpha in large caps net of ~2 units/month of turnover.

RULE (fixed before any run): at each month's last close (trade day
dates[i], coming month m = month of dates[i+1]), hold EXPECTED payers
(DIVMONTH.classify on signal day dates[i-1]: ex-date in m-3, m-6, m-9 or
m-12, ex-dates <= dates[i-1]) equal weight, fully invested; drift in the
month. < 10 names -> SPY for the month. Before the first book: SPY.
  * Variants (robustness gate): lags {12}, {3}, {3, 12}, {6, 12}.
  * Benchmark SPY (Yahoo, aligned to the Sharadar calendar), 5bp/side,
    1998-01 -> vault, strict bar + FF5+Mom alpha gate. Family
    "dividend-month": lifetime 5 after DIVMONTH + 5 here -> trials 10.
PASS CRITERION (written before any run): harness verdict PASS with every
world-class gate (incl. factor alpha t >= 2) on 1998-01 -> 2024-10.

DATA-TIMING: as DIVMONTH — ex-dates, membership and prices dated <=
dates[i-1]; px[.][i] only drifts the held book. Weights decided at close
i earn close i -> close i+1.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("divmonth", _here.with_name("R-2026-11-14-DIVMONTH.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

ID = "I-2026-11-14-DIVMONTHLO"
BENCH = "SPY"


def make_weights(lags=(3, 6, 9, 12), min_names=10):
    def select(dates, i, px):
        exp, _ = dm.classify(dates[i - 1], dates[i + 1][:7], lags)
        exp = [t for t in exp if t in px and px[t][i - 1] is not None]
        if len(exp) < min_names:
            return {BENCH: 1.0}
        return {t: 1.0 / len(exp) for t in exp}
    return dm.make_monthly(select, warmup={BENCH: 1.0})


weights = make_weights()
VARIANTS = {"lag12": make_weights((12,)), "lag3": make_weights((3,)),
            "lag3_12": make_weights((3, 12)), "lag6_12": make_weights((6, 12))}


if __name__ == "__main__":
    rep = dm.replication_check()
    print("REPLICATION (DIVMONTH rule)", json.dumps(rep))
    if not rep["replicated"]:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "DIVMONTH did not replicate the source headline — harness/data suspect; "
                                    "variant not tested (RESEARCH.md LEAGUE rule 1)"}))
        sys.exit(0)
    out = rb.evaluate(
        ID, weights, dm.ag.all_tickers(dm.START), BENCH, start=dm.START, asset_class="stocks",
        trials=10, family=dm.FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Hartzmark-Solomon long-only: point-in-time S&P 500 members expected to go ex-dividend "
               "in the coming month (ex-date 3/6/9/12 months earlier, Sharadar ACTIONS), equal weight, "
               "monthly; SPY warm-up / fallback; variants lag12/lag3/lag3_12/lag6_12; the rule of "
               "queue row I-2026-11-08-DIVMONTH"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
