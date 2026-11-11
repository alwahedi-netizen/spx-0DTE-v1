# RESEARCH.md — the weekly research league (was: the daily scan)

Owner request (2026-10-28): every week, scan the web for new trading techniques
that look worth testing, score them, backtest the best, and email Tariq
(alwahedi@logicon.ae) what to move through the three phases. Asset classes:
**stocks/ETFs, bonds, FX, futures/commodities, crypto** — and, since the
2026-11-11 league, **options** as its own team (studies on our own journal).

## LEAGUE — WEEKLY, since 2026-11-14 (owner 2026-11-11: "do a reset and a league same time and move it to weekly instead of daily")

**This section overrides everything below it where they disagree.** The
daily scan (≥10 ideas per class per day, up to 5 tests per class per day,
2026-11-07 → 11-11) is retired: 129 tests in 5 nights produced no usable
strategy and the volume itself raised every luck bar (theme 18, 21, 24).

**Rhythm.** One research ROUND per week, run inside the Saturday 07:13 UAE
digest (after Friday's US close). Weekday digests carry no research desks;
their Research section is one line: the league table and anything pending.

**Teams** (one lead agent each, spawned per round; scoreboard in
`data/research/league.json`):

| Team | Weekly test budget (Nov) | Scope |
|---|---|---|
| **Options** | 4 | Our proven edge (MEIC is live). Studies on our own journal (`data/paper/positions.csv`, `live/live_trades.csv`, `day.csv`): pre-registered replays and splits, and proposals for paper lanes (MEIC 2.0 family). Paper lanes need the owner's go. |
| Stocks | 2 | Point-in-time Sharadar only; factor-alpha gate applies |
| Bonds | 2 | ETFs only for credit; FRED allowed with publish lags |
| Commodities | 2 | ETFs; no back-adjusted futures |
| FX | 1 | CurrencyShares / UUP / UDN preferred; `=X` are start-of-day prices |
| Crypto | 1 | Benchmark sleeves against the STATIC sleeve (theme 22) |

A "test" = one `research_bt.evaluate` run (or, for Options, one
pre-registered journal study). A team may spend fewer, never more.
**Portfolio desk** (not competing; run by the lead): builds and maintains
ONE Logicon portfolio from survivors and near-misses, runs it forward on
paper once the owner approves, and reports it monthly.

**Quality rules (every team):**
1. **Replication first:** a sourced idea's first run must reproduce the
   source's published headline (sign and rough size) on the source's own
   period/universe before any variant is tried; if it cannot, log
   "harness/data suspect" and stop.
2. **Data-timing line** in every script header (which bar dates the signal
   reads; none on/after the trade day).
3. Fewer, deeper: ≥10 ideas per team are NOT required; score only what
   the team would actually test.
4. All existing gates, family trial counts, red team and the one-time vault
   (§0, §2b) still apply.

**Cross red team:** every round, each team red-teams the best result of the
team after it (Options → Stocks → Bonds → Commodities → FX → Crypto →
Options), on top of the lead's red team for any PASS.

**Scoring** (points in league.json; the lead awards them and writes why):

| Event | Points |
|---|---|
| A result survives red team AND its vault test → proposed to the owner | +10 |
| The owner approves it to paper | +5 |
| A paper lane from this team beats its benchmark over a calendar month (≥15 sessions) | +5 (−3 if it trails) |
| A shortlist near-miss (potential ≥4 after red team) | +2 |
| A genuine error caught in ANOTHER team's work (confirmed by the lead) | +3 |
| Own result withdrawn for a data/timing error | −5 |

**Month end:** the leader gets +50% test budget next month, the last team
−50% (minimum 1); ties keep their budget. The table goes in the first
digest of the month. November is a trial season (3 rounds: 14, 21, 28 Nov);
December is the first full season.

**Learning stays:** every idea still gets a learnings row and KNOWLEDGE.md
is still read first and updated last (§00).

## 00. Learning first (owner 2026-11-07)

"Don't be overly restrictive in idea selection — that enables our learning.
Capture learnings from each idea, build a knowledge base, rate it; a failed
idea can still be shortlisted as having potential and later combined into
our own proprietary system."
- **Start every run by reading `data/research/KNOWLEDGE.md` and
  `learnings.csv`;** end it by updating both (one learnings row per idea
  scored or tested, and the themes/shortlist/combination tables).
- **Test broadly:** every idea scoring ≥ 40 that our data can test gets a
  Phase-1 run (up to 5 per asset class per day; more when time allows).
  Only untestable or untradeable ideas skip the test — they still get a
  learnings row saying what data or access would unlock them.
- **Rate potential (0–5)** for every idea, separate from the verdict, using
  the `traits` research_bt reports (rubric in KNOWLEDGE.md). Potential ≥ 3
  goes on the shortlist even when the verdict is FAIL.
- **Learnings rows** must say: when it works, when it fails, the lesson,
  what to combine it with, and what would make it worth revisiting.

## 0. World-class protocol (owner 2026-11-07: "match what world class is doing — cost is not a problem")

1. **Parallel researchers.** Each daily run spawns one research agent per
   asset class (stocks/ETFs, bonds, FX, futures/commodities, crypto — five in
   parallel), each sourcing and scoring its ≥10 ideas against §2–§4 with the
   ledger loaded for de-duplication. The run merges and de-duplicates across
   classes before anything is written.
2. **Harness gates.** Every Phase-1 test goes through `research_bt.evaluate`
   with `asset_class=` (per-class cost model; the Fama-French 5 + momentum
   factor-alpha gate for stocks), an honest `trials=` (every variant ever run
   for that idea family, not just today's), and — for any rule with a
   parameter — `variants=` holding ≥4 neighbouring settings (e.g. lookback
   ±25%/±50%). PASS requires: 99% confidence vs benchmark, held-out win,
   Deflated Sharpe ≥ 0.95, t ≥ 3 (Harvey-Liu-Zhu), still beating the
   benchmark at 2× costs, ≥70% of neighbours also beating it, and (stocks)
   factor alpha t ≥ 2. Any FAIL demotes the verdict; the result JSON shows
   which gate failed and the email names it.
3. **Red team.** Every PASS or PROMISING is handed to a SEPARATE agent that
   did not build it, with one job: break it. Check look-ahead (signals using
   same-day closes for same-day trades, revised data), survivorship (a
   universe of today's tickers), data errors (splits, stale prices, gaps),
   regime dependence (does one year/crisis carry it?), cost and capacity
   realism, and whether it is a known factor in disguise. Its findings go in
   the ledger notes; a PASS the red team breaks is reported as FAIL with the
   reason. Only a PASS that survives the red team reaches the email as PASS.
4. **Portfolio fit** (`portfolio.py`). research_bt saves monthly returns of
   every shortlist-grade idea (suggested potential ≥ 3) to
   `data/research/series/`. For every PASS or new shortlist entry, run
   `portfolio.marginal(book, id, series)` where the book = the shortlist's
   series (inverse-vol weighted): report correlation to the book and the
   Sharpe gain from adding it at 10%. An uncorrelated small edge beats a
   correlated big one; combination candidates (§2b) are judged the same way.
5. **Data honesty.** Daily Yahoo data has no delisted stocks and no
   point-in-time fundamentals: any cross-sectional single-stock idea is
   marked `survivorship-biased` in its notes and can be PROMISING at best
   until survivorship-free data is connected (see §7).

## 1. Pipeline and who decides

| Phase | What | Who moves an idea in |
|---|---|---|
| 0 Idea | Found, scored, logged in `data/research/ideas.csv` | the scan |
| 1 Backtest | `research_bt.py`, rules written before the run | the scan (every testable idea ≥40, up to 5 per class per day + a monthly deep dive) |
| 2 Paper | A pre-registered lane in the matching Paper Lab sandbox | **Tariq says "go"** |
| 3 Live | Small size via the hub's single Schwab grant | **Tariq says "go", after the paper gates pass** |

The scan never builds a paper lane, never touches a running lab, never trades.
It recommends; Tariq decides.

## 2. Sources (scan each, newest first, since the last scan; widen to ~30 days when a class is thin)

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

Daily additions (2026-11-07), to reach the per-class quota with quality:
  - **arXiv q-fin** (PM, TR, ST, CP) and **SSRN FEN / NBER** working papers;
    central-bank & BIS working papers (rates, FX, carry, macro)
  - **Practitioner research**: AQR, Man Institute, Research Affiliates, Robeco
    Quant, Alpha Architect, Quantpedia (new + "screener"), CXO Advisory,
    Allocate Smartly, Verdad, Newfound/Return Stacked, Hudson & Thames
  - **Asset-class desks**: CME Group & EIA research (commodities/futures);
    Coin Metrics, Kaiko, Glassnode research (crypto, daily-data rules only);
    BIS/IMF FX notes; bond: Treasury/Fed term-premium and curve research
  - **Canon mining** when new publications are thin: untested VARIANTS of the
    classic literature (Jegadeesh-Titman, Moskowitz-Ooi-Pedersen TSMOM, Asness
    et al. "Value and Momentum Everywhere", Koijen et al. carry, Frazzini-
    Pedersen BAB, Baltas-Kosowski, Hurst-Ooi-Pedersen, Gorton-Rouwenhorst) —
    each with the paper as source and the exact variant stated; a variant of
    a ledger row must say which row and why the difference matters (§3)

Skip anything about options or that needs data we cannot get (tick data, paid
alt-data, order books). **Quota: ≥10 scored ideas per asset class per day.**
Never fabricate a source or rule to meet it: if a class truly has fewer than
10 credible ideas that day, score what exists, say the count plainly in the
email, and make it up from canon mining the next day.

## 2b. Original research — combinations and variations (owner 2026-11-07)

"Why limit yourself to what is published? You can always combine or do
variations." Each daily run ALSO designs **≥3 original ideas per asset class**
(id prefix `L-` for lab-generated), on top of the ≥10 sourced ones:
  - **shortlist first:** ingredients come from the KNOWLEDGE.md shortlist
    (potential ≥ 3) and its queued combination candidates;
  - **combinations** of signals that each have evidence (e.g. trend × carry,
    value × momentum, a regime filter from one class applied to another);
  - **variations** of ledger ideas that failed for a stated, fixable reason
    (the notes say which row and what the fix is);
  - **conditioning** on regimes the lab has measured itself (negative-GEX
    days, volatility regime, curve shape, trend state);
  - **cross-asset** signals (e.g. credit spreads → equities, FX carry → risk).
Rules that make this safe (enforced in `research_bt.py`):
  1. **Rationale first:** write the economic reason it should work and the
     exact rule BEFORE the first run (script header). No reason, no test.
  2. **One family per hypothesis:** pass `family=` so every variation of the
     same idea shares one lifetime trial count — the Deflated Sharpe bar
     rises automatically with every attempt (`results/trials.json`).
  3. **The vault:** development runs never see data after `VAULT_FROM` (the
     last ~2 years). A lab idea that passes every gate on development data
     takes ONE vault test (`vault=True`); only a vault PASS is proposed to
     Tariq. The vault never opens twice for the same family.
  4. Same §0 gates and red team as sourced ideas — no shortcuts.

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

Backtest **every testable idea scoring ≥40 — up to 5 per asset class per
day** (owner, 2026-11-07: test broadly to learn; was top 1–5 per week at
≥50), one script each at
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

On the **first scan of each calendar month** (day 1),
in addition to the daily scan, take the next family from the rotation below
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
alwahedi-netizen/spx-0DTE-v1 (a data-only change: the Cloudflare lab rebuilds
nightly from main, which refreshes the Research tab). Never edit any other file or branch; if the
harness itself needs a fix, say so in the email instead.

## 6. The email (to alwahedi@logicon.ae)

Subject: `Logicon research — <date>: <n> new · <k> backtested · <p> pass`

DAILY and SHORT (a 2-minute read; the full ledger is the Research tab):
1. **Ready for Phase 2** (PASS this week): name, what it does in one line,
   result vs benchmark (return/yr, worst drawdown, Sharpe, confidence,
   held-out result), and the exact sentence Tariq can reply to approve.
2. **Backtested this week**: one row each — verdict and one-line why.
   On a deep-dive week, a separate section: the family, one row per asset
   class (return vs benchmark, worst drop, verdict) and the one-line takeaway.
3. **New ideas scored**: per asset class, the count and the TOP 3 by score
   (name · score · one-line idea · link); the rest are in the Research tab.
4. **Paper lanes due a verdict** (from the labs' gates), if any.
5. **Learned today:** 2–4 bullets — new shortlist entries (potential ≥ 3,
   even if FAIL) and any theme the knowledge base changed.

No jargon without a plain-English gloss. If nothing passed, say so plainly:
that is the normal outcome.

## 7. Data roadmap (world-class gaps)

Connected: Yahoo daily prices (ETFs, indices, FX, crypto, futures fronts),
^IRX T-bills, Ken French daily factors (FF5 + momentum, 1926→).
**Sharadar Full History Bundle (2026-11-07):** survivorship-free US stock
prices 1997→ incl. delisted names (final tickers, e.g. SVB = SIVBQ), point-
in-time fundamentals 1993→ (`date` = when public), S&P 500 membership 1970→
(`sp500_members(asof)` rebuilt 2008-06-30 = 500 names incl. MER, WB1,
LEHMQ), insiders 2008→, 13F `holdings`. Use `evaluate(..., source="sharadar")`
for single-stock ideas; universes from `sp500_members` on each rebalance
date; fundamentals only where `date` <= the decision day. Ideas run this
way are NOT capped by §0.5 (`survivorship_free: true` in the result).
The key is never in code: the environment's network secret injects it.
Gaps that cap what can PASS today: (a) survivorship-free US stocks incl.
delisted names, (b) point-in-time fundamentals, (c) back-adjusted continuous
futures with roll history. When a paid source is connected, record it here
and lift the §0.5 cap for the ideas it covers.
