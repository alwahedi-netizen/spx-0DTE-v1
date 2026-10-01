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

## 10. Candidate round 2 (2026-09-30): "strong edge, survives, high octane"

Five new lanes. Rules were fixed in `stocks_config.yaml` before their first
run, and all start at `stage: backtest`. MOM stays the untouched control.

| lane | idea (source) | PF | OOS PF | maxDD | 2020 crash (hold −34%) | Sharpe vs hold | verdict |
|---|---|---|---|---|---|---|---|
| MOMR | MOM + regime filter (Faber) | 1.80 | 1.93 | −9.9% | −6.6% | 0.69 vs 1.00 | FAIL (benchmark) |
| BRK55 | 55-day breakout, 20-day-low exit (Turtles) | 1.87 | 1.74 | −12.2% | −12.0% | 0.87 vs 1.00 | FAIL (benchmark) |
| HI52 | 52-week-high momentum (George & Hwang) | 1.65 | 2.22 | −8.8% | −6.3% | 0.61 vs 1.00 | FAIL (benchmark) |
| QBO | box breakout of 3-month leaders (Qullamaggie) | 1.06 | 1.03 | −12.5% | −1.0% | 0.16 vs 1.00 | FAIL (no edge: 67% conf) |
| SECROT | monthly dual-momentum ETF rotation (Antonacci) | 1.70 | 1.92 | −3.0% | −3.0% | 0.60 vs 0.75 | FAIL (benchmark) |

MOMR, BRK55, HI52 and SECROT pass every check except "beat buy-and-hold
of the same universe". They are real edges that crash far less than
holding, but they don't beat simply holding a survivorship-biased list of
today's winners. The bar is NOT moved after seeing results. The honest
fix is a point-in-time universe (historical index membership), which
removes the bias instead of benchmarking against it. That's the next
backtester upgrade; these four get re-judged there.

## 11. Deep test: point-in-time S&P 500 (2026-09-30)

`python3 stocks_backtest.py --pit` replays each stock lane on the **actual**
S&P 500 membership of every day since 2017 (`reference/sp500_pit.csv`, from
fja05680/sp500 = Clenow's list maintained from Wikipedia changes). That
includes 242 names that later left the index. A holding whose prices stop
(buyout, bankruptcy) is closed at its last price. The benchmark is the
equal-weight, daily-rebalanced S&P 500 of those same members (CAGR 9.8%,
max DD −40%, Sharpe 0.58). Price coverage: 90.8% of member-days. The
missing 9% are mostly acquired companies plus three collapses (SVB, First
Republic, Bed Bath & Beyond), so the test is still slightly flattering.

| lane | today's-100 test | deep test PF | deep maxDD | deep Sharpe vs S&P EW | verdict |
|---|---|---|---|---|---|
| MOM | PASS (PF 2.32) | 1.30 | −19.4% | 0.43 vs 0.58 | **FAIL** |
| MOMR | fail | 1.30 | −21.3% | 0.37 vs 0.58 | FAIL |
| BRK55 | fail | 1.56 | −18.5% | 0.56 vs 0.58 | FAIL (closest) |
| HI52 | fail | 1.24 | −14.2% | 0.32 vs 0.58 | FAIL |
| PB90 | fail | 1.08 | −16.2% | 0.32 vs 0.58 | FAIL |
| QBO | fail | 1.03 | −21.9% | 0.13 vs 0.58 | FAIL |

**Reading:** most of MOM's shallow-test edge was survivorship bias.
Momentum on a list of known winners looks brilliant, and on the real
index it is roughly break-even vs owning the index. Every lane is much
better in the recent window (2024–26, held-out PF 1.3–2.8) than in
2017–2023: a regime tailwind, not a proven edge. Every lane lost less than
the index in all three crashes, but paid for that in the good years.
The deep test is now the promotion test for stock lanes; ETF lanes
(RSI2, SECROT) have no stock-survivorship issue and keep their verdicts.

## 12. Round 3 (2026-09-30): evidence-backed families + MOM stopped

MOM was moved back to `stage: backtest` (owner), so no lane is paper
trading. Round 3 tested the families with the strongest published,
survivorship-free evidence. The rotation lanes are equal-weight portfolios
rebalanced monthly (`size_for`, `ROTATION`).

| lane | idea | test | PF | maxDD | Sharpe vs hold | verdict |
|---|---|---|---|---|---|---|
| ETFTREND | each ETF held while > SMA200 (Faber) | ETFs | 2.95 | −16.3% | 0.69 vs 0.75 | FAIL (closest: DD + Sharpe) |
| LOWVOL | 15 lowest-vol S&P names | deep | 2.46 | −28.9% | 0.37 vs 0.58 | FAIL |
| LVMOM | momentum × low-vol blend, 15 | deep | 1.39 | −28.1% | 0.34 vs 0.58 | FAIL |
| MOM12 | 12-1 momentum, 15, SPY>SMA200 | deep | 1.22 | −49.3% | 0.33 vs 0.58 | FAIL |
| RSI2S | RSI(2)<5 dip-buy on S&P stocks | deep | 0.97 | −17.8% | −0.10 vs 0.58 | FAIL (no edge) |

**Reading across 3 rounds / 16 lanes:** on a fair test, no long-only rule
set here beats owning the index on a risk-adjusted basis over 2017–2026.
That fits the literature: published anomalies decay, and this decade was
won by mega-cap indexing. The lanes consistently cut crash losses; none
turned that into a better risk-adjusted return.

**Known modelling gap:** returns are price-only. Dividends are missing
for strategies AND benchmarks, which hurts high-yield holdings most
(LOWVOL's utilities/staples, ETFTREND's TLT/XLU). A total-return mode
(Yahoo adjclose) is the next honest upgrade before these are re-judged.


## 13. Round 4 (2026-09-30): market-wide effects + dividends

`--total-return` backtests on dividend-adjusted prices (Yahoo adjclose)
for strategies AND benchmarks. The dashboard shows each lane's most
rigorous verdict: point-in-time + dividends, then point-in-time, then
dividends, then basic.

| lane | test | PF | maxDD | in market | return on invested $ | Sharpe vs hold | fails on |
|---|---|---|---|---|---|---|---|
| TOM (turn of month, 4 index ETFs) | ETFs+div | 1.52 | −3.8% | 4% | 29% | 0.57 vs 0.78 | Sharpe |
| SECROT | ETFs+div | 1.97 | −3.1% | 10% | 14% | 0.69 vs 0.84 | Sharpe |
| RSI2 | ETFs+div | 1.30 | −4.0% | 7% | 18.5% | 0.56 vs 0.84 | Sharpe |
| IBS (4 index ETFs) | ETFs+div | 1.26 | −3.1% | 6% | 16% | 0.49 vs 0.78 | PF, Sharpe |
| ETFTREND | ETFs+div | 3.44 | −16.3% | 83% | 8.6% | 0.78 vs 0.84 | DD, Sharpe |
| LOWVOL | deep+div | 4.15 | −26.6% | 98% | 6% | 0.55 vs 0.67 | DD, Sharpe |
| LVMOM | deep+div | 1.79 | −25.9% | 97% | 6% | 0.51 vs 0.67 | DD, Sharpe |
| MOM | deep+div | 1.42 | −22.1% | 52% | 11% | 0.53 vs 0.67 | DD, Sharpe |
| BRK55 | deep+div | 1.49 | −19.0% | 54% | 10% | 0.53 vs 0.67 | conf, DD, Sharpe |

**Finding:** four short-exposure timing lanes (TOM, SECROT, RSI2, IBS)
have statistically solid edges (≥ 99% confidence) and near-zero crash
losses. They fail only on annual Sharpe vs a fully-invested hold,
because they sit in cash 90–96% of the time and the model pays 0% on
that cash. Two open methodology questions for the owner (not applied):
(1) credit idle cash with the T-bill rate and use excess-return Sharpe
(the textbook definition); (2) test the low-exposure edges STACKED in
one book, since they trade on different days.


## 14. Round 5 (owner-approved): T-bill cash + a stacked book

Two methodology changes, made with the owner's OK after round 4:
`--cash-yield` pays the 13-week T-bill rate (Yahoo ^IRX) on idle cash,
and Sharpe is computed on excess returns over it (the textbook
definition), for strategies AND benchmarks. `STACK` runs TOM + SECROT +
RSI2 + IBS on one account (P&L and exposure add). It must also fit
(peak exposure ≤ 100%).

| lane | CAGR | maxDD | exposure | excess Sharpe vs hold | verdict |
|---|---|---|---|---|---|
| STACK | 6.2% | −5.7% | 28% (peak 104%) | 0.65 vs 0.69 | FAIL (Sharpe by 0.04; fit 104%) |
| ETFTREND | 8.1% | −16.1% | 83% | 0.61 vs 0.69 | FAIL (DD, Sharpe) |
| SECROT | 3.7% | −2.9% | 10% | 0.56 vs 0.69 | FAIL (Sharpe) |
| TOM | 3.7% | −1.8% | 4% | 0.52 vs 0.65 | FAIL (Sharpe) |
| RSI2 | 3.6% | −2.6% | 7% | 0.44 vs 0.69 | FAIL (Sharpe) |
| IBS | 3.4% | −2.6% | 6% | 0.42 vs 0.65 | FAIL (PF, Sharpe) |

The fixes lowered both sides: the index's excess Sharpe fell 0.84 → 0.69,
and the timing lanes (mostly in T-bills) lost most of their excess return
too. STACK is the best risk profile found (crash losses of 2–5% vs 15–31%
for holding, 2,247 trades, 100% confidence), but it does not beat the
index per unit of risk. No lane is promoted.


## 15. Round 6 (owner: keep searching): Sharpe-raising lanes

Weighted monthly lanes (`WEIGHTED`, `lane_weights`): sold at the month's
last close, re-bought at the next open. Judged with dividends + T-bill cash.

| lane | idea | CAGR | maxDD | excess Sharpe vs hold | verdict |
|---|---|---|---|---|---|
| VTSPY | vol-managed SPY, 15% target, ≤100% | 8.6% | −22.0% | 0.58 vs 0.69 | FAIL |
| VT4 | same on SPY/QQQ/IWM/DIA | 7.5% | −22.4% | 0.48 vs 0.65 | FAIL |
| RPAR | risk parity SPY/TLT/GLD | 6.3% | −18.4% | 0.52 vs 0.72 | FAIL |
| RPTREND | 5-asset risk parity, > SMA200 only | 5.2% | −8.0% | 0.42 vs 0.57 | FAIL (Sharpe only) |

Monthly vol targeting could not react inside fast crashes (2020 lasted a
month) and missed the rebounds. Risk parity was hurt by 2022, when stocks
and bonds fell together. This matches the out-of-sample literature
(e.g. Cederburg et al. 2020 on vol-managed portfolios).

**Tally: 25 lanes tested, 0 pass.** The multiple-testing risk now
dominates: at this count a lucky pass is likely, so any future pass needs
its held-out window and paper record weighed more heavily than the
full-window numbers.


## 16. Round 7 (owner: keep searching, stricter bar — 2026-10-01)

New lanes carry `strict: true`: 99% confidence AND beating buy-and-hold
inside the held-out last 30% (the multiple-testing guard after 25 lanes).

| lane | idea | PF | maxDD | Sharpe vs hold (full / held-out) | verdict |
|---|---|---|---|---|---|
| TSMOM | 12m time-series momentum, 20 ETFs, vol-scaled | 1.34 | −20.5% | 0.26 vs 0.69 / 0.91 vs 1.02 | FAIL |
| GAPFADE | buy ≥0.75% gap-down opens, sell at close | 1.20 | −1.3% | 0.33 vs 0.65 / 0.57 vs 0.84 | FAIL (94% conf) |
| OVN | hold SPY/QQQ only overnight | 1.01 | −31.3% | −0.07 vs 0.76 / 0.32 vs 0.96 | FAIL (no edge after costs) |

OVN: the famous overnight anomaly has no edge left once each night's
round trip pays the sandbox's ETF cost model (2 bps per side).
TSMOM was hit by whipsaws in 2018–2023 (in-sample PF 1.06).

**Tally: 28 lanes, 0 pass.**


## 17. Round 8 (owner: Chinese, Indian, Japanese methods — 2026-10-01)

Six methods, each on the US index ETFs (X) and the Asia ETFs (XA: China
FXI/MCHI/ASHR, India INDA/EPI, Japan EWJ/DXJ). Strict bar, dividends +
T-bill cash.

| lane | origin | trades | PF | conf | maxDD | Sharpe vs hold (full / held-out) | fails on |
|---|---|---|---|---|---|---|---|
| **KDJA** | China KDJ, Asia ETFs | 224 | 1.36 | 97% | −3.3% | **0.35 vs 0.31 / 0.99 vs 0.68** | 99% confidence only |
| ST | India Supertrend, US | 145 | 2.04 | 99.9% | −3.1% | 0.54 vs 0.65 / 0.58 vs 0.84 | Sharpe |
| ICHI | Japan Ichimoku, US | 379 | 1.49 | 98% | −3.9% | 0.34 vs 0.65 / 0.21 vs 0.84 | conf, Sharpe |
| HA | Japan Heikin-Ashi, US | 627 | 1.29 | 99% | −1.9% | 0.44 vs 0.65 / 0.24 vs 0.84 | PF, Sharpe |
| MAAL | China MA alignment, US | 230 | 1.37 | 95% | −2.8% | 0.19 vs 0.65 / −0.38 vs 0.84 | conf, OOS, Sharpe |
| KDJ | China KDJ, US | 108 | 0.85 | 24% | −3.2% | −0.25 | no edge |
| ENG / ENGA | Japan engulfing | 20 / 11 | — | — | — | — | too few trades |
| ICHIA, HAA, MAALA, STA | Asia ETFs | 348–879 | 0.94–1.05 | ≤ 67% | | | no edge |

**KDJA is the first lane to pass every Sharpe test:** it beats holding
the Asia ETFs over the full window and in the held-out last 30%. It
misses only the round-7 multiple-testing guard (97% vs 99%), and would
have passed the original 90% bar. Caveats: its benchmark is weak (Asia
ETFs returned 6.8%/yr with a −35% drawdown), and it was one of 12 tests
in this round. **Tally: 40 lanes, 0 pass the bar in force.**
