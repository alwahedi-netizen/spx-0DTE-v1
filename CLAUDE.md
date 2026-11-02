# Notes for Claude Code sessions

## Working across sessions (from Tariq)

Tariq often runs several Claude Code sessions at the same time and may paste a message into the wrong one.

- Requests meant for this session: act normally — no extra confirmation needed.
- Reading other sessions, their branches, pull requests or the work they produced is always fine.
- **Before modifying anything another session built or is working on** — its branch, open pull request, feature, data, scheduled tasks or messages it sent — or when a request looks like it was meant for a different session or project: **stop and ask Tariq to confirm first.** Say what you would change and whose work it touches.
- If two sessions turn out to be working on the same thing, tell Tariq and wait for his choice instead of merging or overwriting.

## Estate status after the Cloudflare migration (2026-11-02) — read before touching gate.py or nginx

The Combo Trader platform (trader.sahmi.ae) migrated behind a Cloudflare
Worker on 2026-11-01/02 (owner-ordered; plan of record:
`CLOUDFLARE_MIGRATION.md` in `alwahedi-netizen/combo-trader-tv`).
**This repo's apps did NOT migrate and are not going to:**

- **paper.sahmi.ae (0DTE lab) and the Stox sandbox run exactly as before** —
  hub nginx + gate, no Worker in front, explicitly on the migration's
  "never moves" list. Nothing here changed routing-wise.
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
- Hub-side (FYI): the combo journals + shine.sqlite now stream
  continuously to R2 (litestream-uid* units) with hourly snapshot
  backups. This repo's own DBs/journals are NOT in that backup set.
