# spx-paper-trader

METF + Band Condor **paper-mode signal logger** for SPX 0DTE credit spreads.
Signal generation + journaling only — **no order routing**, paper or live.
The engine says exactly what the rules would trade, at what strikes, for what
theoretical credit; a human executes in thinkorswim paperMoney and back-fills
the actual fills. After ~100 entries per strategy (or 6 weeks), the journal
decides whether either rule set earns real capital.

Standalone sibling of the Logicon Capital platform (`combo-trader-tv`) — it
shares the Schwab auth flow and chain conventions but touches none of the
platform's files.

## Strategies

**METF** — at 6 fixed slots (10:00 → 14:15 ET), EMA 20/40 on 1-min SPX picks
the side: fast > slow → sell a PUT vertical below, else a CALL vertical
above. Strikes by credit, not delta: the **furthest OTM** short (30-wide)
whose mid credit ≥ $1.50; skip the slot below $1.25. Stop when the spread
value reaches 2× credit; otherwise hold to expiry.

**Band Condor** — at 10:30 the expected move = ATM straddle mid × 0.85,
rounded out to 5s. Band skew inside [0.80, 1.25] → iron condor at the band
edges (30-wide wings); skewed → a single vertical on the cushioned side.
Stop per side = total credit collected (single vertical: its credit × 2);
take-profit each short at $0.05. Size from the rolling 20-day containment
rate: full ≥ 0.70, half ≥ 0.55, else skip.

Both share a daily risk budget (1.5% of configured equity) that caps the
**sum of all stop losses**. GEX sign is journaled as a tag only — never an
entry condition. FOMC decision days (and any `skip_dates` in the config,
e.g. CPI, FOMC minutes) produce a no-trade day.

## One Schwab app — how tokens work (read this first)

This tool **never places orders** and never touches thinkorswim. You trade
manually in thinkorswim paperMoney; the Schwab API is used **read-only** for
market data (quotes, chains, 1-min bars).

Schwab allows one active login per developer app: running a new OAuth login
from a second place **invalidates the refresh token the first app is using**.
So there are exactly two safe setups:

1. **Share Combo Trader's tokens (recommended, zero disruption).** Run this
   on the same machine as Combo Trader and point at its token file before
   starting:
   `export LOGICON_TOKENS_FILE=/path/to/combo-trader-tv/tokens.json`
   The logger then behaves like one more platform process on that file (the
   platform's own services already share it the same way). In this mode the
   `auth` command and the dashboard's login flow are **hard-blocked** so a
   new login can never be triggered from here by accident.
2. **Standalone (only if this is your ONLY Schwab API app).** Copy
   `.env.example` to `.env`, fill in the app key/secret, authenticate once
   from the dashboard (or `python schwab_auth.py auth`). Do **not** do this
   if Combo Trader uses the same app key — it would break Combo Trader.

## Quick start — browser only, no Python commands

**Windows:** double-click `START_PAPER.bat`. It installs dependencies on
first run, starts the dashboard, and opens http://127.0.0.1:5250/ in your
browser. Leave the black window open (it is the engine); close it to stop.

**Linux/macOS/server:** `./start_paper.sh` (set `PAPER_HOST=0.0.0.0` to open
the dashboard from another machine, and `LOGICON_TOKENS_FILE` as above).

The dashboard does everything:

- **supervises the day loop** — on trading days it starts the engine at
  08:55 ET, restarts it if it dies (the loop is idempotent, nothing
  duplicates), and shows its live log;
- **live state** — today's signals, open/closed positions, risk used vs
  budget, the 10:30 band, VIX/GEX tags;
- **fills** — type your paperMoney credit/exit into the actual columns and
  press Save (theo columns stay locked);
- **report** — the weekly stats, rendered in the page.

Leave it running all week; it does nothing on weekends and calendar-skip
days by itself.

## CLI (optional — same engine, no dashboard)

```bash
python3 paper_engine.py run | status | report --weeks 1
python3 paper_engine.py fill <position_id> --credit 1.45 --exit 0.00 --note "filled 10:01"
python3 tests_paper.py     # offline regression suite
```

All schedule times are **America/New_York** regardless of server timezone;
every timestamp is ET ISO-8601 with offset.

## The journal (`data/paper/`)

| file | contents |
|---|---|
| `day.csv` | one row per day: VIX, 5-day VIX change, prior close, ATR20, GEX sign, risk budget |
| `signals.csv` | one row per slot per strategy — trade or skip (reason: CREDIT / RISK / CONTAINMENT / CALENDAR / DATA) with every input that drove it |
| `positions.csv` | one row per side: theo credit, stop, exit (STOPPED / TP / EXPIRED), theo P/L — plus `*_actual` columns **left blank for the human** |
| `band.csv` | 10:30 band per day: straddle, expected move, edges, skew, close, contained |

Theo columns are immutable once written; `fill` can only touch the
`*_actual` columns. `report` computes win rate, expectancy, premium capture
rate, double-stop rate, P/L by slot / EMA state / GEX sign / VIX bucket,
slippage (actual − theo) and the rolling containment rate — from the CSVs
alone, no API.

## Files

- `paper_dashboard.py` + `static/paper.html` — browser dashboard (supervises
  the day loop; fills, report, log — no Python needed day-to-day)
- `START_PAPER.bat` / `start_paper.sh` — double-click / server launchers
- `paper_engine.py` — rules, day loop, CLI
- `paper_data.py` — Schwab market data (1-min SPX bars, 0DTE SPXW chain, VIX)
- `paper_store.py` — the CSV journal
- `paper_report.py` — stats
- `paper_config.yaml` — the one fixed config for the test window
- `schwab_auth.py` — minimal Schwab OAuth (auth / status CLI)
- `logicon_env.py` — `.env` secrets loader
- `tests_paper.py` — offline regression suite (fixture chains, no API)
