#!/usr/bin/env bash
# setup_autodeploy.sh — install the auto-deployer for spx-0DTE-v1 on the hub.
# After this, every push to main goes live within ~2 minutes, gated on the
# offline test suite. Run:  sudo bash setup_autodeploy.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cp "$REPO_DIR/deploy/logicon-paper-update.service" \
   "$REPO_DIR/deploy/logicon-paper-update.timer" /etc/systemd/system/
chmod +x "$REPO_DIR/deploy/auto-update-paper.sh"
systemctl daemon-reload
systemctl enable --now logicon-paper-update.timer

echo "auto-deploy armed: pushes to main deploy within ~2 min (tests must pass)."
echo "  watch:  journalctl -u logicon-paper-update -f"
echo "  pause:  systemctl stop logicon-paper-update.timer"
systemctl list-timers logicon-paper-update.timer --no-pager | head -3
