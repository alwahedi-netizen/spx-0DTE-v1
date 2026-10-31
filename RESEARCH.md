# RESEARCH.md — the weekly strategy-research scan

Owner request (2026-10-28): every week, scan the web for new trading techniques
that look worth testing, score them, backtest the best, and email Tariq
(alwahedi@logicon.ae) what to move through the three phases. Asset classes:
**stocks/ETFs, bonds, FX, futures/commodities, crypto. NOT options** (another
instance owns options).

The weekly run is a scheduled cloud session. It reads this file and follows it
exactly. Changing the rules means editing this file, not the schedule.

## 1. Pipeline and who decides

| Phase | What | Who moves an idea in |
|---|---|---|
| 0 Idea | Found, scored, logged in `data/research/ideas.csv` | the scan |
| 1 Backtest | `research_bt.py`, rules written before the run | the scan (top 1–5 per week + a monthly deep dive) |
| 2 Paper | A pre-registered lane in the matching Paper Lab sandbox | **Tariq says "go"** |
| 3 Live | Small size via the hub's single Schwab grant | **Tariq says "go", after the paper gates pass** |

The scan never builds a paper lane, never touches a running lab, never trades.
It recommends; Tariq decides.

## 2. Sources (scan each, newest first, last ~14 days)

- arXiv q-fin (PM, TR, ST): https://arxiv.org/list/q-fin/new and search
- SSRN finance (new working papers on trading strategies)
- Quantocracy (aggregator): https://quantocracy.com
- Alpha Architect, Quantpedia (new strategies), Robot Wealth, QuantStart,
  Return Stacked, Allocate Smartly, Flirting with Models (Newfound), CXO Advisory
- r/algotrading, r/quant (only ideas with a stated, testable rule; Reddit may
  be unreachable from the scan's environment — say so in the email if it is)
- *Added 2026-10-31 (owner):*
  - **Google Scholar + SSRN keyword searches** (newest first), e.g.
    "trading strategy out-of-sample net of transaction costs", "time-series
    momentum", "carry strategy", "tactical asset allocation", "volatility
    managed portfolio", "cryptocurrency trading strategy", "commodity futures
    strategy", "currency strategy", "bond return predictability"
  - **GitHub**: strategy repositories updated in the window with a stated rule
    and a backtest (search: "backtest strategy", "trading strategy", sorted by
    recently updated) — the rule, not the code, is what gets scored
  - **Journal of Portfolio Management** and **Financial Analysts Journal**:
    new-issue abstracts

Skip anything about options or that needs data we cannot get (tick data, paid
alt-data, order books). Max **20 ideas scored per week**.

## 3. De-duplication

Before scoring, read `data/research/ideas.csv`. If an idea is the same
mechanism as any row (including phase `graveyard` or `paper`), do not re-add
it. A real variant gets a new row whose notes say which row it varies and why
the difference matters.

## 4. Scoring (0–100) and Phase-1 verdicts

| Criterion | Max | 0 | full marks |
|---|---|---|---|
| evidence | 25 | one blog backtest | peer-reviewed + independent out-of-sample replication |
| costs | 20 | daily turnover, thin edge | monthly or slower, edge >> 10bp/trade |
| diversify | 20 | same bet as an existing lane (equity momentum / trend) | different asset class or driver, low expected correlation |
| testable | 15 | needs unavailable data | free daily data (Yahoo) covers 15+ years incl. a crash |
| tradeable | 10 | not executable at Schwab | Schwab-tradeable ETF/stock/future |
| simplicity | 10 | many tuned parameters | ≤3 parameters, published defaults |

Backtest the top **1–5** ideas scoring **≥50** (owner, 2026-10-31; was 1–3 at
≥60), one script each at
`data/research/ideas/<id>.py`, calling `research_bt.evaluate(...)`:
- rules fixed **before** the first run, using the source's published parameters;
- benchmark: SPY (stocks), AGG or IEF (bonds), T-bills (FX, market-neutral),
  DBC (commodities), BTC-USD (crypto);
- costs ≥ 5bp per unit of turnover (≥ 10bp crypto/small caps);
- longest history Yahoo allows (aim for 2000+, must include a crash);
- if you try variants, pass `trials=` with the real count and report the
  median variant, not only the best.

`research_bt.py` sets the verdict: **PASS** (≥99% confidence the Sharpe beats
the benchmark, AND it beats it in the held-out last 30% with positive return),
**PROMISING** (≥90% + held-out beat), else **FAIL**. Both also need a
full-period Sharpe at least 0.10 above the benchmark's (no near-copies). A PASS is a candidate for
Phase 2; PROMISING stays in Phase 1 for a refinement next week (once); FAIL
goes to `graveyard`.

## 4b. Allocation track (owner, 2026-10-28)

Buy-and-hold **allocations** (fixed or slowly rebalanced mixes, e.g. a
leveraged 55/45) trade a few times a year and cannot reach 99% confidence on
any realistic history, so they are judged on the owner's question instead:
*does it beat the benchmark over long holding periods?*
Use `research_bt.evaluate_allocation(...)` with the longest history available
(mutual-fund proxies such as VFINX / VUSTX are fine when the ETF is young —
say which). Verdict:
- **10-year check:** beats the benchmark in ≥60% of rolling 10-year windows
  (monthly steps), the median window beats it, and the latest window beats it.
- **20-year check** (only if 10-year passes, the primary horizon): beats it in
  ≥70% of rolling 20-year windows, median and latest window beat it.
- *Rule history:* first set at 70%/70% on 2026-10-28; the owner revised the
  10-year bar to 60% the same day, after Hedgefundie scored 69.7% — recorded
  so readers know HFEA passed under a rule revised after its result.
- **PASS** = both pass. **PROMISING** = 10-year passes but history is too short
  for 20-year windows. **FAIL** = otherwise.
- Always report the worst calendar year: whether that loss is survivable is
  the owner's call, not the harness's.
Trading signals stay on the §4 strict bar. Do not move a threshold after
seeing a result; changes to these rules apply to the next idea.

## 4c. Monthly deep dive (owner, 2026-10-31)

On the **first scan of each calendar month** (the Saturday falling on day 1–7),
in addition to the weekly scan, take the next family from the rotation below
that has no `DD-` row in the ledger yet, and test its classic published form
across **every asset class we can get honest daily data for** — equity indices
(VFINX/SPY, QQQ, IWM, EFA, EEM), bonds (VUSTX/TLT, IEF), commodities (GLD,
DBC/commodity ETFs, CL=F/GC=F for history), FX (G10 pairs vs USD) and crypto
(BTC-USD, ETH-USD) — one `research_bt` run per class, same rules everywhere,
rules fixed before the first run. Use the strict bar (§4) for signals and the
allocation track (§4b) for allocations; `trials` = number of classes run.
Log one ledger row per family: `DD-<yyyy-mm>-<family>`, the per-class verdicts
in notes, and the best class only as a candidate for a follow-up — never as a
PASS on its own (picking the best of N classes is itself a trial).

Rotation (in order; restart at the top when all are done):
1. Time-series trend (12-1 momentum and 10-month SMA)
2. Carry (yield / roll / interest-rate differential)
3. Cross-sectional momentum (12-1, top third vs bottom third, monthly)
4. Long-term reversal / value (5-year losers vs winners)
5. Volatility targeting (scale to 15% realized vol)
6. Seasonality (turn of month, sell-in-May, day-of-week)
7. Short-term reversal (1-week losers, weekly)
8. Low volatility / betting-against-beta
9. Risk parity across asset classes (inverse vol, monthly)
10. Breakout / channel (Donchian 20/55 with ATR stop)

## 5. Ledger and commits

Update `data/research/ideas.csv` (columns as in the header; `score` = sum of the
six criteria; `phase` one of idea / backtest / paper-proposed / paper / live /
rejected / graveyard). Commit ONLY files under `data/research/` to `main` of
alwahedi-netizen/spx-0DTE-v1 (a data-only change: the hub syncs it to the
Research tab without a redeploy). Never edit any other file or branch; if the
harness itself needs a fix, say so in the email instead.

## 6. The email (to alwahedi@logicon.ae)

Subject: `Logicon research — <date>: <n> new · <k> backtested · <p> pass`

Plain language, short:
1. **Ready for Phase 2** (PASS this week): name, what it does in one line,
   result vs benchmark (return/yr, worst drawdown, Sharpe, confidence,
   held-out result), and the exact sentence Tariq can reply to approve.
2. **Backtested this week**: one row each — verdict and one-line why.
   On a deep-dive week, a separate section: the family, one row per asset
   class (return vs benchmark, worst drop, verdict) and the one-line takeaway.
3. **New ideas scored**: table name · asset class · score · one-line idea · link.
4. **Paper lanes due a verdict** (from the labs' gates), if any.

No jargon without a plain-English gloss. If nothing passed, say so plainly:
that is the normal outcome.
