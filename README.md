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

## Setup

```bash
pip install requests pyyaml
cp .env.example .env            # fill in SCHWAB_APP_KEY / SCHWAB_APP_SECRET
python3 schwab_auth.py auth     # Schwab login; tokens.json (7-day refresh life)
python3 tests_paper.py          # offline regression suite — must pass
```

Already running the Logicon platform? Skip `auth` and point at its tokens:
`export LOGICON_TOKENS_FILE=/path/to/combo-trader-tv/tokens.json`. To get a
real GEX tag instead of `unknown`, also add the platform repo to
`PYTHONPATH` (the logger imports its `gex_bridge` read-only).

## Daily use

```bash
python3 paper_engine.py run       # full-day loop, 09:00–16:05 ET, idempotent
python3 paper_engine.py status    # open positions, stop distance, risk vs budget
python3 paper_engine.py fill 2026-09-01-METF-10:00-PUT --credit 1.45 --exit 0.00 --note "filled 10:01"
python3 paper_engine.py report --weeks 1
```

`run` is safe to restart mid-day: logged slots never re-run, and slots missed
while the engine was down are journaled as `SKIP`/`DATA` so every day still
has a complete, honest record. Run it under cron/systemd on trading days
(it exits by itself on weekends and calendar-skip days).

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

- `paper_engine.py` — rules, day loop, CLI
- `paper_data.py` — Schwab market data (1-min SPX bars, 0DTE SPXW chain, VIX)
- `paper_store.py` — the CSV journal
- `paper_report.py` — stats
- `paper_config.yaml` — the one fixed config for the test window
- `schwab_auth.py` — minimal Schwab OAuth (auth / status CLI)
- `logicon_env.py` — `.env` secrets loader
- `tests_paper.py` — offline regression suite (fixture chains, no API)
