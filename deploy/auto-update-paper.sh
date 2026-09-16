#!/usr/bin/env bash
# auto-update-paper.sh — hub self-deployer for spx-0DTE-v1.
# A systemd timer runs this every 2 min: poll GitHub, and when a new commit
# lands on main, run the offline test suite and — only if it passes — deploy
# to /opt/logicon/spx-paper-trader and restart the services.
#
# Install once (as root on the hub):  sudo bash deploy/setup_autodeploy.sh
# Watch it:   journalctl -u logicon-paper-update -f
# Pause it:   systemctl stop logicon-paper-update.timer
#
# Scope: deploys APP code (python + static). It never touches nginx or the
# Cloudflare setup — changes to deploy/*.sh remain a manual `sudo bash` run,
# so an unattended job can never break the portal's web server.
# A restart mid-session briefly stops the dashboard; the day loop is
# idempotent and the supervisor relaunches it within ~1 min, so at most one
# tracking cycle is missed and no slots are ever duplicated.

set -uo pipefail

# systemd runs without HOME; git then can't read /root/.gitconfig (the
# safe.directory exceptions and stored GitHub credentials) — same incident
# as combo-trader's auto-update (2026-08-28). Pin HOME, declare the dir safe.
export HOME="${HOME:-/root}"
CLONE="${PAPER_CLONE:-/root/spx-paper-trader}"
APP_DIR=/opt/logicon/spx-paper-trader
MARKER=/opt/logicon/.autoupdate-paper-deployed

git config --global --get-all safe.directory 2>/dev/null | grep -qx "$CLONE" \
  || git config --global --add safe.directory "$CLONE"

# One deploy at a time; also guards a slow deploy against the next tick.
exec 9>/run/logicon-paper-update.lock
flock -n 9 || exit 0

log() { echo "[$(date '+%F %T')] $*"; }

[ -d "$CLONE/.git" ] || { log "no clone at $CLONE — skipped"; exit 0; }
git -C "$CLONE" fetch origin main --quiet 2>&1 || { log "fetch failed"; exit 0; }

r=$(git -C "$CLONE" rev-parse origin/main)
cur=$(cat "$MARKER" 2>/dev/null || echo none)
if [ "$cur" != "$r" ]; then

log "deployed=$cur origin=$r — updating"

# ff-only on purpose: local edits in the clone must never be silently
# discarded by an unattended job. If this warns, resolve by hand.
if ! git -C "$CLONE" merge --ff-only origin/main --quiet 2>&1; then
  log "NOT fast-forwardable (local commits/edits in $CLONE?) — left untouched"
  exit 0
fi

# Journal-snapshot commits touch only data/ — record them as deployed
# without re-running tests or restarting anything.
if [ "$cur" != "none" ] && \
   ! git -C "$CLONE" diff --name-only "$cur" "$r" 2>/dev/null | grep -qv '^data/'; then
  echo "$r" > "$MARKER"
  log "data-only change (journal snapshot) — no redeploy needed"
else

# Gate the deploy on the offline regression suite: a push that breaks the
# rules engine must never reach the live journal.
if ! (cd "$CLONE" && python3 tests_paper.py >/tmp/paper-tests.log 2>&1); then
  log "TESTS FAILED — deploy blocked. tail /tmp/paper-tests.log:"
  tail -5 /tmp/paper-tests.log
  exit 0
fi

LOGICON_USER="$(stat -c %U "$APP_DIR" 2>/dev/null || echo root)"
id "$LOGICON_USER" >/dev/null 2>&1 || LOGICON_USER=root
rsync -a --exclude '.git' --exclude '__pycache__' --exclude 'data' \
      --exclude 'gate_credentials.json' --exclude 'gate_secret' \
      "$CLONE/" "$APP_DIR/"
chown -R "$LOGICON_USER":"$LOGICON_USER" "$APP_DIR"

systemctl restart logicon-paper 2>/dev/null || true
systemctl try-restart logicon-gate 2>/dev/null || true

echo "$r" > "$MARKER"
log "deployed $(git -C "$CLONE" rev-parse --short HEAD); logicon-paper restarted"
if git -C "$CLONE" diff --name-only "$cur" "$r" 2>/dev/null | grep -q '^deploy/'; then
  log "NOTE: this commit also changed deploy/ scripts — those are not"
  log "auto-applied; run the relevant 'sudo bash deploy/...' step by hand."
fi

fi  # end data-only vs full-deploy
fi  # end deploy stage ($cur != $r)

# ── journal backup: commit the live CSVs into the repo (hourly) ─────────────
# Gives the paper-test record an off-server copy and lets analysis run from
# anywhere. Only data/ changes are pushed; the data-only short-circuit above
# keeps these snapshots from triggering redeploys.
if [ -d "$APP_DIR/data/paper" ]; then
  last=$(git -C "$CLONE" log -1 --format=%ct -- data 2>/dev/null)
  [ -n "$last" ] || last=0
  if [ $(( $(date +%s) - last )) -ge 3600 ]; then
    mkdir -p "$CLONE/data/paper"
    rsync -a --exclude 'logs' "$APP_DIR/data/paper/" "$CLONE/data/paper/"
    if [ -n "$(git -C "$CLONE" status --porcelain -- data)" ]; then
      git -C "$CLONE" add data
      git -C "$CLONE" -c user.name="Logicon Hub" -c user.email="alwahedi@logicon.ae"         commit -q -m "journal snapshot $(TZ=America/New_York date '+%F %H:%M ET')

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01CNijtbEomNEwJhzqoeQPkc" -- data || true
      if git -C "$CLONE" push -q origin main 2>/dev/null || \
         { git -C "$CLONE" pull --rebase -q origin main 2>/dev/null && \
           git -C "$CLONE" push -q origin main 2>/dev/null; }; then
        git -C "$CLONE" rev-parse origin/main > /dev/null
        log "journal snapshot pushed"
      else
        log "journal push FAILED (no push credentials?) — resetting so deploys stay unwedged"
        git -C "$CLONE" reset --hard -q origin/main
      fi
    fi
  fi
fi
