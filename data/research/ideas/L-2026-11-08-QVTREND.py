"""L-2026-11-08-QVTREND — lab original: Greenblatt quality-value WITH a trend
overlay (KNOWLEDGE.md combination queue: MAGICSF × DD-TREND).

Rationale (written before the first run): R-2026-11-07-MAGICSF showed real
alpha on survivorship-free data (+14.2%/yr vs +7.6%, factor-alpha t 2.8) but
fell 57% in 2008 and lagged 2017-24. The trend deep dive (DD-2026-11-TREND)
is the ledger's most reliable crash cutter. Holding the quality-value book
only while the S&P 500 is in an uptrend should keep most of the alpha and cut
the bear-market drawdowns that make it hard to hold.

Rule (fixed before the first run):
  at each month end, if SPY's close is above the average of its last 10
  month-end closes, hold MAGICSF's book (best 30 of the point-in-time S&P 500
  ex financials/utilities by EBIT/EV + point-in-time ROIC ranks, equal
  weight); otherwise hold T-bills. Re-checked monthly.
Same harness, costs, period and benchmark as MAGICSF (SPY, 5bp, 2000 → vault).
Family GREENBLATT: a variation of the same core, so it shares (and raises)
the family's lifetime trial count. Lab original → sealed vault applies.
Variants: 8- and 12-month SMA, SPY 12-1 momentum > 0 as the filter, and
a 200-day SMA checked monthly.
"""
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location("magic", Path(__file__).with_name("R-2026-11-07-MAGICSF.py"))
magic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(magic)


def make(sma_months=10, mode="sma"):
    base = magic.make()
    st = {"ends": [], "on": False}

    def weights(i, dates, px):
        if i == 0:
            st.update(ends=[], on=False)
        w = base(i, dates, px)                        # keeps the base book's own state current
        spy = px.get("SPY")
        if i + 1 < len(dates) and dates[i + 1][:7] == dates[i][:7]:
            return w if st["on"] else {}
        st["ends"].append(i)
        if spy is None or not spy[i]:
            st["on"] = False
        elif mode == "sma":
            closes = [spy[j] for j in st["ends"][-sma_months:] if spy[j]]
            st["on"] = len(closes) == sma_months and spy[i] > sum(closes) / sma_months
        elif mode == "mom":
            st["on"] = i >= 252 and spy[i - 252] and spy[i - 21] / spy[i - 252] > 1
        elif mode == "sma200":
            win = [spy[j] for j in range(max(0, i - 199), i + 1) if spy[j]]
            st["on"] = len(win) >= 200 and spy[i] > sum(win) / len(win)
        return w if st["on"] else {}
    return weights


if __name__ == "__main__":
    import json
    out = rb.evaluate("L-2026-11-08-QVTREND", make(), magic.TICKERS, "SPY", start="2000-01-01",
                      asset_class="stocks", source="sharadar", family="GREENBLATT",
                      variants={"sma8": make(8), "sma12": make(12), "spy12-1": make(mode="mom"),
                                "sma200d": make(mode="sma200")},
                      notes="Lab original: MAGICSF book only while SPY > 10-month SMA, else T-bills; "
                            "Sharadar survivorship-free; family GREENBLATT")
    print(json.dumps({k: out[k] for k in out if k not in ("equity",)}, indent=1)[:6000])
