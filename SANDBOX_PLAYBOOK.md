# SANDBOX PLAYBOOK — from idea to live capital, the Logicon way

*Written 2026-09-29, after one full cycle: the SPX 0DTE options lab went
from a written spec (2026-08-30) to paper trading (08-31), through
statistical gates (09-22), to real-money execution (09-23), to a
multi-strategy, multi-account live pilot (09-29). This file is the
blueprint for repeating that process on a NEW asset class — next up:
a STOCKS sandbox. It records what we built, in what order, what broke,
and exactly what to copy versus change.*

---

## 1. Principles (copy these before any code)

1. **Paper first, always.** No strategy touches real money until it has
   a statistical record in an idempotent journal. Ever.
2. **Pre-registered gates, decided before the first trade.** Ours:
   ~100 trades or 6 weeks per strategy, plus money tripwires (e.g.
   "kill/review at 20 triggers or −$3,000"). Gates make kill decisions
   unemotional — we held ORB through −$1,536 because the gate said so,
   and it recovered to +$1,448. We also retired METF-class ideas the
   moment their gate verdict landed.
3. **Keep losers running until their gate.** One bad week and one good
   week are both noise. The gate, not the mood, decides.
4. **Retire with records.** `RETIRED.md` holds every dead strategy's
   final stats and the lesson. Check it before proposing anything new —
   failed ideas do not get readopted by accident.
5. **The paper engine stays the only brain.** Live execution is a
   MIRROR of the paper journal — it never re-decides anything. This
   keeps live vs paper perfectly comparable (slippage is measurable
   trade-by-trade) and means one battle-tested rules engine.
6. **The broker is ground truth.** The live ledger is audited against
   real account positions every cycle; on mismatch, stop trading first,
   reconcile second.
7. **Every deploy is gated on the offline test suite.** A push that
   breaks the rules engine must never reach the live journal.
8. **Real money starts at pilot size with hard rails**: 1 unit,
   per-strategy daily stops, a global daily stop, entry cutoffs,
   freshness guards, kill switches, disarmed-by-default arming.

## 2. Architecture (five components — port all five)

```
┌─────────────┐   signals/exits    ┌──────────────┐
│ paper_engine │──────────────────▶│ paper_store  │  append-only CSV journal
│ (the brain)  │                   │ (the memory) │  + sanctioned updates only
└──────┬───────┘                   └──────┬───────┘
       │ market data                      │ mirrors
┌──────▼───────┐                   ┌──────▼───────┐
│ paper_data   │                   │ live executor │  per-strategy arming,
│ (the eyes)   │                   │ (the hands)   │  broker ground-truth sync
└──────────────┘                   └──────┬───────┘
        ┌──────────────────────────┐      │
        │ dashboard + supervisor    │◀─────┘  arming UI, kill switches,
        │ (the face & the heartbeat)│         live-vs-paper reporting
        └──────────────────────────┘
```

- **`paper_engine.py` (brain):** pure decision functions (entry rules,
  stops, sizing) + an idempotent full-day loop. Pure functions take
  data in, return decisions out — no I/O — so they are unit-testable
  offline. The day loop re-derives all state from the journal, so a
  crash/restart never duplicates or loses a slot (missed slots get an
  explicit SKIP row with a reason).
- **`paper_store.py` (memory):** append-only CSVs (`day`, `signals`,
  `positions`) with allow-listed in-place updates only (actual fills,
  exits). Theoretical columns are IMMUTABLE once written — the store
  raises if code tries. This is what makes the journal trustworthy.
- **`paper_data.py` (eyes):** every network call lives here behind one
  exception type; a data problem becomes a SKIP/DATA journal row, not a
  crash. Self-paced rate limiting.
- **`paper_dashboard.py` + static HTML (face/heartbeat):** browser-only
  operation (the owner never runs Python), supervises the engine
  process, serves state/report/log APIs, hosts the arming UI.
- **`live_meic.py` (hands, added ONLY after gates):** mirrors journal
  rows of ARMED strategies into real broker orders. Per-strategy
  arm/disarm to a chosen account, dry-run mode, daily stops,
  tick-legal pricing, fee-netted P&L, broker position audit.

**Infra rails around them:** git push = deploy (a 2-min timer on the
server pulls, RUNS THE FULL TEST SUITE, and only then rsyncs + restarts);
hourly journal snapshots committed back to git (remote analysis without
server access, survives everything); data-only commits don't trigger
redeploys; secrets and armed-state live outside git.

## 3. The build, phase by phase (what we actually did)

**Phase 0 — Spec (1 day).** A written spec before any code: strategies,
journal schema, risk budget, decision gate ("100 entries per strategy or
6 weeks; no live capital before then"), acceptance criteria. The gate
being IN the spec is what made every later decision clean.

**Phase 1 — Paper engine + journal (2–3 days).** Brain, memory, eyes,
face. Deterministic day loop; per-strategy entry windows; explicit skip
reasons (DATA/CREDIT/RISK/REGIME); simulated execution (fills at theo ±
a slippage assumption) so the journal has an "actual" column from day 1.

**Phase 2 — Offline test harness (same days, not later).** Two layers:
- *Unit truth tables* on the pure functions (45 checks at launch, ~80
  now): entry rules, stop math, sizing, sign conventions, store
  immutability, idempotent slot helpers.
- *Fake-clock full-day simulations*: monkeypatch the clock and the data
  adapter, run a whole trading day in milliseconds INCLUDING a mid-day
  crash and restart, assert no duplicated or lost slots. This harness
  later validated every new strategy (FLYR's crash-in-the-gap test) and
  every execution fix before it touched production.

**Phase 3 — Auto-deploy with a test gate (1 day).** Server timer:
fetch → ff-only merge → run tests → deploy → restart. Plus hourly
journal snapshot pushes. From here on, shipping = `git push`, and a
broken push cannot deploy.

**Phase 4 — Run, analyze, iterate (3–4 weeks).** Daily scorecards and
weekly full analyses FROM THE JOURNAL ONLY: expectancy ± SE, t-stat,
"confidence the edge is real" (t-CDF), profit factor, max drawdown,
win rate, per-regime splits. Rules we held ourselves to:
- annualizing 2 weeks of data is labeled as the fantasy it is;
- <20 trades = "statistically inadmissible", whatever the number says;
- one jackpot day (ORB +$2,473) is lottery profile, not edge;
- regime splits (our GEX tag) generate NEW strategies (MNG), never
  in-place edits to a running experiment — the original keeps running
  as the control (same discipline as FLY vs FLYR).

**Phase 5 — Gate verdicts (end of window).** At ~100 trades each
strategy got a verdict: retire (METF-class, BAND, LATE — recorded in
RETIRED.md), keep papering (coin-flips), or graduate to a live pilot
(best evidence + deepest sample first).

**Phase 6 — Live pilot (only after Phase 5).** The mirror executor,
shipped DISARMED, armed by the owner in the UI (account tail + typing
"ARM LIVE"), 1 contract, daily loss cap, entry cutoff, freshness guard
(never chase a stale signal after downtime), kill switches everywhere.
**Reality taught us, at 1-lot cost, in the first three days:**
- *Tick-size grids*: the broker rejects off-grid limit prices (SPX:
  0.05 under $3, 0.10 above). Every computed price must snap to the
  instrument's legal grid. Stocks equivalent: penny increments, and
  sub-penny rules for certain order types.
- *Never loop a rejected order*: escalate the price a bounded number of
  times, then stop and flag. Our first version resubmitted one rejected
  close every 31 seconds for two hours.
- *Log the broker's rejection reason verbatim.*
- *Fees are strategy-relevant*: measure the real per-unit cost from
  your own fills (ours: $1.18/leg) and net every booked P&L with it.
- *Sync with the broker, don't trust your own ledger*: pull real
  positions every cycle; absorb manual closes from the order history;
  hold entries on any mismatch (DESYNC); book expired/settled positions
  from official prices. Target: your P&L equals the broker app's to the
  penny — the owner WILL compare screenshots.
- *Bookkeeping must not require being armed* (a disarmed bot still owes
  you yesterday's accounting).
- *Emergency closes need guaranteed-marketable limits* (spread width for
  credit structures; for stocks: marketable limit through the NBBO).
**Result:** live execution validated in 4 sessions (+$1,879 net), with
the honest note that ~half was luck from a bug — which the pilot's size
made cheap to learn.

**Phase 7 — Scale out (after the pilot proves the plumbing).**
Multi-strategy arming, each to its OWN account (risk isolation), signed
pricing for debit structures, per-strategy + global stops, dry-run
rehearsal per strategy. New strategies enter the LAB, not the live
whitelist — they earn arming eligibility through the same gates.

## 4. The migration-to-live checklist (use verbatim)

A strategy may be armed only when ALL of these hold:
- [ ] ~100 paper trades or its full pre-registered window elapsed
- [ ] positive expectancy with confidence ≥ ~75–80% (t-CDF), PF > 1.2
- [ ] its worst paper day fits inside the planned daily stop
- [ ] executor supports its structure (tick grid, signs, order types)
      with offline tests for every new price/leg path
- [ ] one clean DRY-RUN session (full shadow, zero orders)
- [ ] daily stop + global stop + entry cutoff + freshness guard + side
      cap configured; kill switch reachable; fee model in the P&L
- [ ] broker ground-truth audit live for its account
- [ ] pilot size = 1 unit; a pre-registered LIVE tripwire (e.g. "disarm
      if live cumulative < X") written down BEFORE arming

## 5. Porting this to a STOCKS sandbox — what changes

**Copy unchanged (≈70% of the design):** the five-component split; the
append-only journal with immutable theo columns; pure decision functions
+ fake-clock simulations; test-gated auto-deploy; hourly journal
snapshots to git; SKIP-with-reason discipline; gates, tripwires,
RETIRED.md; the mirror-executor concept with per-strategy arming,
dry-run, daily stops, DESYNC audit, fee-netted P&L; the dashboard
pattern (browser-only operation, arm panels, live-vs-paper report).

**Rethink for stocks (the real work):**
1. **No expiry = no automatic exit.** 0DTE positions self-destruct at
   16:00; stocks positions live until YOU exit. Every stocks strategy
   needs an explicit exit rule (time stop, trailing stop, target) and
   the engine needs an overnight state: positions carried across days,
   marked-to-market at each close in a new `marks` journal, P&L split
   into realized + unrealized. The day loop becomes a
   session loop + an end-of-day mark/roll step.
2. **Journal schema:** replace short/long strikes with symbol, side
   (long/short), qty, entry px, stop px, target px, and a campaign id
   (multi-day positions need add/trim events — see the main platform's
   two-phase exit engine for the campaign reconstruction pattern).
3. **Risk units:** options risk was defined by structure (width −
   credit). Stocks risk = qty × stop distance, budgeted the same way
   (daily risk budget, per-position cap, portfolio heat = sum of open
   stop risks). Position sizing = risk budget / stop distance.
4. **Execution details:** penny ticks; RTH vs extended hours; slippage
   model per liquidity tier; shorting needs locates/HTB awareness — the
   sandbox should log "would short" separately from "can short";
   corporate actions (splits/dividends) must be healed in the journal
   (the platform's split-heal logic is the reference).
5. **Data adapter:** same Schwab token estate (ONE grant, hub-owned —
   never a second app). Bars + quotes come from the same marketdata API;
   the FMP metrics the platform already caches (90d highs, returns,
   RS) are the natural signal inputs.
6. **Strategy seeds for the stocks lab** (each with a pre-registered
   gate, entering PAPER only): the platform already produces graded
   momentum scans, slope/trend screens, GEX regime for indices, and a
   two-phase exit engine — sandbox candidates are e.g. (a) scanner
   top-decile momentum entries with the two-phase exit rules, (b) 90d
   high pullback continuation, (c) the Slope lab's PULLBACK lane traded
   systematically. The lab's job is to make the platform's discretionary
   ideas testable the same way MEIC/FLY were.
7. **What "settlement reconcile" becomes:** there is none — replace it
   with a nightly broker-positions reconcile (qty + avg cost vs ledger)
   and mark-to-market bookkeeping.

## 6. Idea sourcing — where the lab's strategies came from

Every strategy in this lab came from one of THREE wells. Draw from all
three on the next project, in this order of trust:

### 6a. Our own journal (the best well — free, honest, ours)
The lab's strongest ideas were mined from its own data, not imported:
- **FLYR** came from noticing FLY's take-profits landed ~1h after entry,
  leaving the rest of the afternoon's decay unharvested → reload rule.
- **MNG** came from splitting every strategy's P&L by the daily GEX
  regime tag (+$2,230 negative-GEX vs −$1,821 positive for MEIC).
- **PBW's mandate** ("premium selling that survives whipsaw") came from
  the autopsy of BAND/LATE — the journal showed the FAILURE MODE
  precisely, which told us the shape of the fix.
**Method to copy:** tag every trading day with regime features (for the
options lab: GEX sign, VIX level, band containment; for stocks: market
breadth, SPY vs 10-month SMA, sector RS, VIX). Then split every
strategy's P&L by every tag at each weekly review. A significant split
= a candidate NEW strategy (never an edit to the running control).

### 6b. The practitioner canon (import, then verify in paper)
The imported strategies are documented community/practitioner systems —
these names and sources are from my (Claude's) training knowledge of
the 0DTE trading ecosystem, recorded here as research leads to verify,
not as fetched citations:
- **MEIC** — "Multiple Entry Iron Condor", popularized by Tammy
  Chambless; discussed extensively in the Option Omega backtesting
  community and its podcast circuit (search: "MEIC Tammy Chambless").
- **FLY / iron-fly pin trades** — the classic 0DTE "theta harvest at
  the pin"; widely documented among SPX 0DTE sellers.
- **PBW (broken-wing butterfly)** — the Ron Bertino / Trading Dominion
  school of structured premium (also the "A14"-style BWB variants);
  hallmark: no upside risk, bounded left tail.
- **METF / ORB** — standard EMA-trend-filtered verticals and the
  Opening Range Breakout, textbook intraday systems (ORB literature
  goes back to Toby Crabel's work on opening range).
- **LATE** — the "power hour theta" claim circulating in 0DTE forums;
  the lab FALSIFIED our condor implementation of it in 16 trades.
**Where to scan for more of this canon** (options and stocks alike):
Option Omega and similar backtest-platform blogs/communities; the
r/thetagang and 0DTE trader forums (ideas, never conclusions); Tastylive
research segments (mechanics and POP framing); CBOE's own index-options
research notes; podcast transcripts of systematic 0DTE traders. For
STOCKS specifically: the academic factor canon (momentum — Jegadeesh &
Titman; trend following on indices — Meb Faber's 10-month SMA timing;
post-earnings drift; low-volatility anomaly), Stockbee/Qullamaggie-style
momentum-breakout practitioner playbooks, and O'Neil/CANSLIM-descended
relative-strength methods. Treat ALL of it as hypothesis, never edge:
the lab exists because most of the canon fails out-of-sample or
regime-shifts — BAND and LATE both came from plausible canon and died
in under 6 weeks.

### 6c. The estate's own tooling (signals we already compute)
The main platform already produces graded momentum scans (21-point
score), the Slope 5y log-trend screen with its PULLBACK lane, GEX
regime tags, expected-move bands, and the two-phase exit engine built
from the pick_behavior study of the owner's own fills. Each of those is
a strategy seed with its infrastructure already paid for. The stocks
sandbox should start here — systematizing what the platform already
believes — before importing anything external.

### The vetting checklist (before ANY idea gets a lab slot)
- [ ] check `RETIRED.md` — is this a dead idea wearing a new name?
- [ ] state the edge's SOURCE in one sentence (whose behavior pays us?)
- [ ] state the regime it should fail in (if you can't, you don't
      understand it yet) — that becomes its tripwire
- [ ] define entry/exit/sizing so a machine needs zero judgment
- [ ] pre-register the gate (trades-or-weeks + money tripwire) in the
      spec BEFORE the first paper trade
- [ ] confirm it's cheap to test (defined risk, fits the daily budget)

## 7. File map (reference implementation, this repo)

| File | Role |
|---|---|
| `paper_engine.py` | rules, pure functions, idempotent day loop |
| `paper_store.py` | append-only journal + allow-listed updates |
| `paper_data.py` | all market-data I/O behind one exception |
| `paper_dashboard.py` | Flask UI/API + engine supervisor + live loop |
| `live_meic.py` | live mirror executor (multi-strategy, multi-account) |
| `static/paper.html`, `static/suggested.html` | dashboards |
| `tests_paper.py` | the deploy gate: ~80 offline checks |
| `deploy/auto-update-paper.sh` | test-gated deploy + journal snapshots |
| `paper_config.yaml` | the one config (mirrors DEFAULTS) |
| `RETIRED.md` | permanent registry of dead strategies |
| `data/paper/*.csv` | the journal — the lab's single source of truth |

## 8. Keys, permissions & infrastructure — the one-time setup, never again

Everything below already EXISTS for the estate. A new sandbox (stocks
included) reuses nearly all of it — the point of this section is that
nothing here should ever be re-created from scratch, and two things
must NEVER be duplicated. No secret values live in this file or in any
repo — only names and locations.

### Schwab API (the crown jewels — ONE of everything, ever)
- **One developer app** (developer.schwab.com) with BOTH products:
  *Market Data Production* and *Accounts and Trading Production*.
  App key + secret live on the hub in `/opt/logicon/infra/.env` as
  `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET`. **Never create a second app
  or a second OAuth grant** — a second refresher invalidates the first
  and takes down everything sharing the token.
- **One token file**: `/opt/logicon/infra/tokens.json`, pointed at by
  the env var `LOGICON_TOKENS_FILE` in every consumer's systemd unit.
  Any new app CONSUMES this file (read + refresh-compatible writes that
  preserve `refresh_auth_at`); it must never run its own OAuth login —
  our `schwab_auth.shared_mode()` hard-blocks it in code. Copy that
  module verbatim into new projects.
- **Token lifecycle:** access token ~30 min (auto-refresh); refresh
  token **7 days** → weekly re-auth at `trader.sahmi.ae/reauth`.
  Schwab auth codes are single-use and expire in ~30 seconds — do the
  paste fast, click Complete once. On the Schwab approval screen,
  **tick ALL accounts** — an unticked account (e.g. …910 initially) is
  simply absent from `accountNumbers` until the next re-auth.
- **Account prerequisites for live trading:** each account to be traded
  needs the appropriate options approval level for spreads (or margin/
  shorting approval for a stocks bot). The bot validates the account
  tail against `accountNumbers` at arm time.
- **Trader API quirks we paid to learn** (all handled in `live_meic.py`,
  copy it): no `Content-Type` header on body-less GETs (400s);
  limit prices must sit on the instrument's legal tick grid; order ids
  come from the `Location` response header; fills are reconstructed
  from `orderActivityCollection` execution legs; rejection reasons are
  in `statusDescription`. Rate ceiling ~120 req/min — self-pace.

### Other API keys (locations, not values)
- **FMP** (fundamental/price metrics for the stocks side): key lives in
  the platform's `.env` on the hub; note some endpoints are plan-gated
  — batch quotes need the per-symbol fallback the platform already has.
- **Anthropic / OpenAI** (platform AI Analyst): entered in the
  platform's Settings page, stored in its config, never in git.
- **Telegram / email doorbell** (`notify.py`): bot token + chat id /
  SMTP creds in the platform `.env`; reuse `notify.send` rather than
  building new channels.

### Server & deploy rails (hub droplet)
- **Host:** DigitalOcean droplet, Tailscale name `hub`
  (`ssh root@hub.tail6aba41.ts.net` — Tailscale SSH handles auth).
- **Layout:** `/opt/logicon/<app>` per app; clones for the auto-updater
  live in `/root/<repo>`; shared secrets in `/opt/logicon/infra/`.
- **systemd per app:** a service (e.g. `logicon-paper`) + an update
  timer (`logicon-paper-update.timer`, every 2 min) that pulls GitHub,
  RUNS THE TEST SUITE, rsyncs (excluding `.git`, `data/`, credentials)
  and restarts. Gotchas already solved in `deploy/auto-update-paper.sh`:
  pin `HOME=/root` (systemd strips it and git loses its config), add
  `safe.directory`, flock against overlapping runs, ff-only merges,
  data-only commits skip redeploy, hourly journal snapshot pushes with
  a reset-on-push-failure so the deployer never wedges.
- **GitHub:** one repo per project under `alwahedi-netizen`; the hub
  clone holds stored push credentials (needed for journal snapshots).
  Push to main = deploy. New project = new repo + copy
  `deploy/setup_autodeploy.sh`, adjust names, run once via SSH.

### Web / DNS / SSO (sahmi.ae)
- **Cloudflare:** domain on Cloudflare DNS, A records per subdomain →
  hub IP, **proxied (orange cloud)**, SSL mode **Full**, **Always Use
  HTTPS on** (the "Not secure" saga), self-signed origin cert in
  `/etc/nginx/sahmi-certs/`.
- **nginx owns 80/443** on the hub (it also serves the Logicon client
  portal — never bind another server to those ports; Caddy died for
  this sin). New app = new vhost proxying to its local port, created by
  a `deploy/setup_*_nginx.sh` script run once by hand — the auto-
  updater deliberately never touches nginx.
- **Gate SSO** (`gate.py`, :5260): one login for every `*.sahmi.ae`
  surface via nginx `auth_request`; cookie `Domain=.sahmi.ae`, 30-day
  HMAC, PBKDF2 credentials in `gate_credentials.json` + `gate_secret`
  (chmod 600, NEVER in git, survives deploys via rsync excludes). A new
  subdomain gets SSO for free by including the auth_request snippet in
  its vhost — no new logins, which is also why dashboards can iframe
  each other across subdomains.
- **Ports in use:** platform 5050/5151 (docker), beta 6050, paper 5250,
  gate 5260, shine 8795. Pick a fresh port for the stocks sandbox and
  register it in the nginx setup script.

### App-level env vars (set in each systemd unit)
`LOGICON_TOKENS_FILE=/opt/logicon/infra/tokens.json`,
`PAPER_HOST=127.0.0.1` (nginx fronts it), `PAPER_PORT=<app port>`,
optional `LOGICON_PLATFORM_DIR=/opt/logicon/combo-trader` (read-only
import of platform modules like the GEX bridge).

### Runtime state that must NEVER be in git
`armed.json` (what's armed, which account), `state.json` (halts),
`gate_credentials.json`, `gate_secret`, `tokens.json`, `.env` files.
The deploy rsync excludes them; keep it that way in the new project.

**Bootstrapping the stocks sandbox:** new repo, copy `paper_store.py`,
`schwab_auth.py` and the deploy scripts nearly verbatim, write the
stocks spec FIRST (strategies, schema, gates), then follow the phases
in §3 in order. Do not skip Phase 2 — every hour spent on the
fake-clock harness repaid itself tenfold when real money was on the
line.
