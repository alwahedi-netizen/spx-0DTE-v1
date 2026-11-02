# Notes for Claude Code sessions

## Working across sessions (from Tariq)

Tariq often runs several Claude Code sessions at the same time and may paste a message into the wrong one.

- Requests meant for this session: act normally — no extra confirmation needed.
- Reading other sessions, their branches, pull requests or the work they produced is always fine.
- **Before modifying anything another session built or is working on** — its branch, open pull request, feature, data, scheduled tasks or messages it sent — or when a request looks like it was meant for a different session or project: **stop and ask Tariq to confirm first.** Say what you would change and whose work it touches.
- If two sessions turn out to be working on the same thing, tell Tariq and wait for his choice instead of merging or overwriting.

## Estate status after the Cloudflare migration (2026-11-02) — read before touching gate.py or nginx

The estate migrated behind a Cloudflare Worker on 2026-11-01/02
(owner-ordered; plan of record: `CLOUDFLARE_MIGRATION.md` in
`alwahedi-netizen/combo-trader-tv`). What it means for THIS repo:

- **paper.sahmi.ae (0DTE lab + Stox sandbox) is now routed through the
  estate edge Worker — but for EDGE AUTH + PASS-THROUGH ONLY** (owner
  order, 2026-11-02). Unauthenticated requests are 302'd to the gate at
  the edge; authenticated ones pass to hub nginx -> port 5250 exactly
  as before. NOTHING of this repo's app is cached, served from the
  edge, or otherwise touched — all trader-only Worker rooms are
  hostname-gated off for paper, and no code here changed. Day-to-day
  development is unaffected; deploys work as before (the Worker is a
  transparent front). One new rule: any NEW endpoint that must be
  reachable WITHOUT the gate cookie (a webhook, a health probe) needs
  a matching exemption in the edge Worker too — ask Tariq / the
  combo-trader-tv session. Rollback lives there (remove the paper
  route from wrangler.router.jsonc).
- **But `gate.py` is now shared edge infrastructure.** The Cloudflare
  Worker verifies the `sahmi_gate` cookie itself (HMAC vs the same
  gate secret) for every trader.sahmi.ae request, and gate.py's
  `/gate/check` also accepts a signed `X-Logicon-Svc` service pass
  (commit f7f1b06) that the Worker's cron uses daily at 13:15 UTC.
  Do NOT change the cookie format/name/signing, the gate-secret file
  location, or `/gate/check` semantics without checking with Tariq —
  it would lock trader.sahmi.ae out at the edge or kill the CF cron.
- **Rotating the gate secret now has two extra steps:** after rotating
  on the hub, update the `GATE_SECRET` GitHub Actions secret in
  combo-trader-tv and re-run its "Deploy Cloudflare edge" workflow.
- Hub-side (FYI): the combo journals, shine.sqlite AND this repo's
  data/labs/labs.sqlite now stream continuously to R2 (litestream-uid*
  units) with hourly snapshots. The CSV journals' off-box copy remains
  the hourly git snapshot.

## Edge (Cloudflare) — since 2026-11-02

paper.sahmi.ae is routed through the estate's Cloudflare worker
`logicon-estate-router` (repo combo-trader-tv, branch
claude/new-session-tsupmi, `wrangler.router.jsonc` + `cloudflare/router-worker.mjs`),
migrated by the trader session ("Phase 7"). For this host it does **edge auth +
pass-through only**: a request without a valid `sahmi_gate` cookie is sent to
`/gate/login` at the edge; everything else reaches the hub unchanged — no edge
caching, no edge assets, no cron for this app.

- Don't add a second worker for paper.sahmi.ae; changes go into that worker
  (another session's repo — ask Tariq first).
- New pages/APIs here need nothing at the edge: they pass through. Never ask
  for edge caching of lab data (live paper journals).
- Health check: `curl -s https://paper.sahmi.ae/__cf/version` (host_scope).
- Rollback (owner/trader session): remove the `paper.sahmi.ae/*` route from
  `wrangler.router.jsonc` and push — traffic goes straight to the hub again.
- `data/labs/labs.sqlite` IS in the estate's R2 + Litestream backups
  (since 2026-11-02); the CSV journals' off-box copy is the hourly git
  snapshot (deploy/auto-update-paper.sh).

## Hubless program (owner decision 2026-11-02)

Tariq decided: migrate everything to Cloudflare and eventually power off
the hub. Plan of record: `HUB_RUNBOOK.md` (Part B) here + Part B section of
`CLOUDFLARE_MIGRATION.md` in combo-trader-tv. **The trader session
(combo-trader-tv) executes all phases**, including this repo's pieces (B2
sign-in gate, B5 Paper Lab). Before changing gate.py or lab architecture,
sync with Tariq/the trader session so the port doesn't chase a moving
target. Day-to-day lab work continues as normal until each phase's
parallel-run begins.
