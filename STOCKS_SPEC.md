# STOCKS & ETF SANDBOX — Phase 0 spec (pre-registered)

*Written 2026-09-30, before the first paper trade. Per SANDBOX_PLAYBOOK.md
§3 Phase 0: strategies, journal schema, risk budget and the decision gate
are fixed HERE. Changing a rule after the first trade = a NEW strategy
with its own gate (the running one stays as the control).*

Lives inside this repo and this dashboard (`paper.sahmi.ae/stocks`, same
Flask app on :5250, same gate SSO): no new nginx vhost, port or Schwab grant.
The engine runs as its OWN supervised subprocess (`stocks_engine.py run`)
with its OWN journal (`data/stocks/`). A stocks crash can't reach the
options loop or the MEIC live mirror.

**Paper only.** No live executor exists for stocks. One gets built
(`live_stocks.py`, a mirror of the journal) only after a strategy passes
the §4 checklist in the playbook.

---

## 1. Universe (frozen for the test window)

100 symbols, listed in `stocks_config.yaml`: 80 liquid US large caps and
20 ETFs (index, sector, GLD/TLT/EEM/EFA). The list is FIXED: no index
reconstitution, no survivorship repair. A name delisted or acquired
mid-window just stops producing signals, and any open position in it is
closed at its last good mark with reason `DELISTED`.

Liquidity tiers (slippage model): `etf` = the ETF list, `large` = the
rest. All 100 are mega-liquid, so two tiers are enough.

## 2. Session loop (ET, NYSE calendar incl. half days)

| time | step | idempotency key |
|---|---|---|
| 09:15 | PREMARKET: holiday check, daily bars for the universe (Schwab, Yahoo fallback), regime tags, split heal | one `day` row per date |
| 09:45 (grace 30 min) | ENTRY slot per strategy: rank candidates from the prior close, adds, sizing, simulated fills at the live quote | any `signals` row for (date, 09:45, strategy); position_id is deterministic |
| 09:45–16:00, every 2 min | TRACK: stops / targets vs last trade | a closed position can't close twice |
| 15:50–16:00 | RULE EXITS: time stops, RSI2 exit, MOM review | same |
| 16:10 (13:10 on half days) | MARK: mark every open campaign, update peak, write the `eod` row | one `eod` row per date |

A missed ENTRY slot (engine down past the grace) writes `SKIP / MISSED`
and does **not** chase later in the day (freshness guard). A day where the
premarket data step fails still writes its `day` row (status `DATA_FAIL`);
entries skip with `DATA` and tracking continues on quotes.

## 3. Strategies (long-only v1)

All signals use daily bars **through the prior close** (no look-ahead).
Entry is at the 09:45 quote (the "next-morning" variant of close-signal
systems; documented, not hidden). Ranking ties break alphabetically.

### MOM — scanner momentum + the platform's two-phase exit (well 6c)
Source: the platform's Slope EXPL factor (1m+3m momentum percentile,
winner of the 2026-08 walk-forward) and the exit_scan two-phase engine
built on the pick_behavior study.
- **Universe:** the 80 stocks (no ETFs).
- **Entry:** EXPL = 0.5·r21 + 0.5·r63, percentile-ranked across the
  stocks; EXPL rank ≥ 90 AND close > SMA50 > SMA200 AND r3d ≥ 0.
  Up to 2 new names per day by EXPL rank; max 8 open MOM campaigns.
- **Add (double-down, platform rule):** once per campaign, at the 09:45
  slot, when r21 ≥ +10%, r3d ≥ 0 and last within 3% of the peak close
  since entry → buy the same qty again. The campaign becomes PHASE 2.
- **Exit:** PHASE 1: last ≤ entry × 0.85. PHASE 2: last ≤ peak × 0.85.
  REVIEW (machine version of the platform's advisory): age ≥ 28 calendar
  days and return between −5% and +5% → exit at 15:50.
- **Fails in:** sharp momentum reversals (e.g. Nov-2020-style factor
  crashes) and chop with SPY below its 10-month SMA.

### PB90 — Slope PULLBACK lane, systematized (well 6c)
Source: the platform's Slope PULLBACK lane (owner 2026-09-19). The
platform's "5Y > 3.9×" filter needs 5y history per name every day. The
lab substitutes a 1-year proxy computable from the same 260 bars: 1-year
return rank ≥ 70 and close > SMA200. The substitution is recorded here.
- **Universe:** the 80 stocks.
- **Entry:** EXPL rank ≥ 75, close 2–12% below the 63-session high,
  r3d > 0 (the bounce has started), close > SMA200, 1y-return rank ≥ 70.
  Up to 2 per day, deepest-in-trend first (EXPL rank); max 5 open.
- **Exit:** stop = entry − 2·ATR20. Target = the 63-session high at
  signal time (a retest). Time stop: 20 sessions.
- **Fails in:** trend breaks, where pullbacks keep falling.

### RSI2 — Connors RSI(2) mean reversion on ETFs (well 6b, canon)
Source: Larry Connors' short-term ETF strategies (practitioner canon,
recorded as a hypothesis to verify, never as edge).
- **Universe:** the 20 ETFs.
- **Entry:** close > SMA200 AND RSI(2) < 10. Up to 2 per day, lowest
  RSI first; max 4 open.
- **Exit:** 15:50 last > SMA5 (5-day SMA using the last as today's
  close), or 10 sessions. Catastrophe stop: entry − 3·ATR20 (the canon
  has no stop; the lab needs one for risk units).
- **Fails in:** crash regimes (2008/2020): oversold keeps getting
  oversold. The SMA200 filter is the canon's own guard.

**Shorts:** out of scope for v1. The schema carries `side` so a short
lane can be added later. Such a lane must log `would_short` separately
from `can_short` (locates/HTB), per the playbook.

## 4. Risk units and sizing

- Paper equity $100,000 (config). No margin: total open notional ≤ equity.
- **Per-campaign risk** = 0.5% of equity ($500) = qty × (entry − stop).
  qty = floor($500 / stop distance), also capped at 8% notional ($8,000).
- **Portfolio heat** = Σ open stop risk (qty × max(0, last − stop)) ≤ 8%.
- **Daily new-risk budget** = Σ initial risk of today's entries+adds ≤ 2%.
- Skip reasons: `NOSIGNAL`, `MAXPOS`, `HELD`, `HEAT`, `BUDGET`, `CASH`,
  `QTY` (price too high for one share at the risk unit), `DATA`, `MISSED`.

## 5. Execution model (simulated, like the options lab)

- Theo entry = last trade at the slot; sim fill = theo × (1 + slip) rounded
  **up** to the penny. Theo exit = the stop/target level, or the last trade
  if it gapped through; sim fill = theo × (1 − slip) rounded **down**.
  Slippage: `large` 5 bps, `etf` 2 bps.
- Fees: $0 commission; SEC fee 0.278 bps + FINRA TAF on sells (config).
  Netted into P&L.
- Manual `*_actual` fills (if the owner mirrors trades in paperMoney)
  always override the simulated ones.
- Corporate actions: **splits** are healed. At premarket, the prior mark
  (unadjusted) is compared with the freshly adjusted history. A clean
  ratio (2, 3, 4, 5, 10, 1.5 or their inverses, ±3%) multiplies the
  campaign's `split_factor` and writes a `SPLIT` event. Theo prices stay
  immutable; effective price = stored / factor, effective qty = qty ×
  factor. **Dividends are not credited.** P&L is price-only, which
  slightly understates ETF/RSI2 returns. Recorded, not hidden.

## 6. Journal schema (`data/stocks/`)

- `day.csv`: date, status, spy_close, spy_sma200, spy_sma10m, spy_regime
  (ABOVE/BELOW 10-month SMA), vix, breadth50 (% of stocks > SMA50),
  bars_source, notes
- `signals.csv`: one row per (slot, strategy, candidate or skip) with
  every input: rank, EXPL, r3d, RSI2, SMAs, ATR, stop/target, qty, risk.
- `positions.csv`: one row per **campaign**. Theo entry columns are
  immutable. Add and exit columns are write-once. Only `stop_px`,
  `peak_px`, `phase` and `split_factor` are mutable (tracker). `*_actual`
  columns are for fills.
- `events.csv`: ENTRY / ADD / STOP_MOVE / SPLIT / EXIT per campaign
  (campaign reconstruction).
- `marks.csv`: date × open campaign: close, qty, avg cost, unrealized.
- `eod.csv`: one row per session: open count, realized today, unrealized,
  equity estimate (the lab's equity curve).

Regime tags for §6a splits: SPY vs 10-month SMA, VIX bucket, breadth50.
Every weekly review splits each strategy's P&L by each tag.

## 7. Decision gates (pre-registered — decided before trade #1)

| strategy | sample gate | money tripwire (review/kill) |
|---|---|---|
| MOM  | 60 closed campaigns **or** 16 weeks | cumulative ≤ −$3,000 |
| PB90 | 100 closed **or** 12 weeks | cumulative ≤ −$3,000 |
| RSI2 | 100 closed **or** 10 weeks | cumulative ≤ −$2,500 |

Verdicts at the gate: retire (to RETIRED.md with final stats), keep
papering, or eligible for a live pilot. Eligibility needs the playbook §4
checklist (expectancy > 0 at ≥ 80% t-CDF confidence, PF > 1.2, worst day
inside the planned daily stop). For MOM and PB90, their dollar return on
deployed capital must also beat SPY buy-and-hold over the same window.
Otherwise the platform should just own SPY. Fewer than 20 closed trades
= statistically inadmissible, whatever the number says.

## 8. Acceptance criteria (Phase 1–3)

- `tests_stocks.py` runs offline: truth tables on every pure function
  (indicators, candidates, sizing, stops, two-phase, fills/ticks, fees,
  split heal, store immutability) and a fake-clock full session that
  crashes mid-day and restarts with no duplicated or lost slots/marks.
- The hub deploy gate runs `tests_paper.py` **and** `tests_stocks.py`.
- Hourly journal snapshots include `data/stocks/` (the bars cache is
  excluded).

## 9. The pipeline: BACKTEST → PAPER → LIVE (added 2026-09-30, owner rule)

No strategy paper-trades until it has passed a historical backtest.
`stocks_backtest.py` replays the **same functions** the paper engine
trades with (candidates, sizing, stops, adds, trailing, rule exits, fills,
fees) over ~9 years of daily bars. It never sees a bar dated on or after
the simulated day, and a test proves it: rewriting the future never
changes past trades. The paper engine only enters strategies whose config
says `stage: paper`.

**Promotion bar (fixed before the first backtest ran, `backtest_gate`):**
≥ 50 trades; expectancy > 0 at ≥ 90% t-CDF confidence; PF ≥ 1.3; the
held-out last 30% of the window keeps expectancy > 0 and PF ≥ 1.1; max
drawdown ≤ 15%; Sharpe ≥ an equal-weight buy-and-hold of the **same**
universe. That last check neutralizes survivorship bias: the universe is
today's winners, so any long strategy looks good on its history.

**First verdicts (2026-09-30, Yahoo 10y history, the §3 parameters):**

| | trades | PF | conf | OOS PF | maxDD | Sharpe vs hold | verdict |
|---|---|---|---|---|---|---|---|
| MOM | 538 | 2.32 | 100% | 2.80 | −11.9% | 1.02 vs 1.00 | **PASS → paper** |
| PB90 | 1104 | 1.16 | 98% | 1.31 | −9.6% | 0.51 vs 1.00 | FAIL → backtest |
| RSI2 | 845 | 1.27 | 99% | 1.70 | −3.3% | 0.51 vs 0.75 | FAIL → backtest |

MOM's pass on the benchmark check is a near-tie. Its edge over simply
holding the universe is risk-shape (−12% vs −33% drawdown), not return.
PB90 and RSI2 have real but thin edges (≥ 97% confidence, PF < 1.3). An
improved variant enters as a NEW strategy name through this same gate; the
original rules are not edited in place. Every run lands in
`data/stocks/backtests/runs.csv` with its parameter hash.

Known limits: survivorship bias (above), price-only returns, and stop
fills approximated from daily highs and lows.
