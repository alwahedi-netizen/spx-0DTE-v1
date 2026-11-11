"""I-2026-11-10-BTCTOM — turn-of-the-month effect in Bitcoin.

Source: Kumar, "Turn-of-the-month effect in cryptocurrencies", Managerial
Finance 2022, https://doi.org/10.1108/MF-02-2022-0084 (BTC/ETH/LTC 2015-21:
TOM-day returns positive and significantly above other days; not explained
by day-of-week or January). Counter-evidence: Ziegler & Mobius, OBA 2023
https://linda.lindeverlag.at/Dokument/16345 (unstable across subperiods).
Ledger row 2026-11-10, queued "next crypto script".

Rationale (written before any run): month-boundary flows — salary-day and
recurring DCA purchases, fund/ETF month-end subscriptions and rebalancing —
are a plausible buying-pressure source in a retail-heavy, flow-driven asset;
in Treasuries the same calendar is the lab's best block (EOMTSY, TSYCAL,
theme 14). Counter-hypothesis: the window is out of BTC ~87% of the time,
so any trend year beats it; ~24 switches/yr x 25bp = ~6%/yr cost hurdle; the
effect may be a 2015-21 artefact (Ziegler-Mobius).

RULE (fixed before any run): window -1..+3 (Lakonishok-Smidt; the paper's
exact window is paywalled — this is OUR choice, stated): hold 100% BTC over
the last calendar day of each month and the first 3 calendar days of the
next, i.e. at the close of bar i hold BTC iff the NEXT calendar day is the
month's last day or is day 1-3 of a month; T-bills otherwise.
DATA TIMING: calendar only — no price is read; decided at the close of bar
i (00:00 UTC), earns bar i -> i+1. Stateless (no state to reset).
Benchmark BTC-USD buy & hold (§4). 25bp per unit turnover.
Variants: -2..+2, -1..+5, -2..+3, -1..+2.
trials: 5 here + the source's 2 other coins (ETH, LTC) = 7; family
btc-calendar (first calendar run in crypto; BTCCAL/BTCMONDAY/BTCPREHOL are
unrun ideas and would join this family).
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

BTC = "BTC-USD"


def make(pre=1, post=3):
    def in_window(n):
        last_pre = (n + timedelta(days=pre)).month != n.month   # among last `pre` days
        return last_pre or n.day <= post

    def weights(i, dates, px):
        nxt = date.fromisoformat(dates[i]) + timedelta(days=1)
        return {BTC: 1.0} if in_window(nxt) else {}
    return weights


weights = make()

VARIANTS = {
    "m2p2": make(pre=2, post=2),
    "m1p5": make(pre=1, post=5),
    "m2p3": make(pre=2, post=3),
    "m1p2": make(pre=1, post=2),
}


if __name__ == "__main__":
    print(json.dumps(rb.evaluate(
        "I-2026-11-10-BTCTOM", weights, [BTC], bench=BTC, start="2014-09-17",
        asset_class="crypto", cost_bps=25.0, trials=7, family="btc-calendar",
        variants=VARIANTS,
        notes="Kumar 2022 TOM on BTC: hold BTC over the last calendar day + first 3 days of each month "
              "(window -1..+3, ours; paper's exact window paywalled), T-bills otherwise; calendar only; "
              "bench BTC-USD; 25bp (~24 switches/yr); variants -2..+2, -1..+5, -2..+3, -1..+2; "
              "vault sealed from 2024-11"),
        indent=1))
