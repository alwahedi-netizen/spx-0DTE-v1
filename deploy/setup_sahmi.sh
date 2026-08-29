#!/usr/bin/env bash
# setup_sahmi.sh — host Combo Trader + SPX Paper Trader on sahmi.ae
# =================================================================
# Run ON THE SAME SERVER that already runs Combo Trader
# (/opt/logicon/combo-trader, per its deploy/setup_server.sh):
#
#     git clone https://github.com/alwahedi-netizen/spx-0DTE-v1 ~/spx-paper-trader
#     cd ~/spx-paper-trader/deploy && sudo bash setup_sahmi.sh
#
# What it does:
#   1. Installs the paper dashboard to /opt/logicon/spx-paper-trader and
#      starts it as systemd service logicon-paper (127.0.0.1:5250, sharing
#      Combo Trader's Schwab tokens read-compatibly — no new Schwab login).
#   2. Installs Caddy and serves, with automatic HTTPS + a password on
#      every route:  trader.sahmi.ae -> Combo Trader (5050)
#                    paper.sahmi.ae  -> Paper Trader (5250)
#   3. Opens ports 80/443 in ufw. Nothing else changes: the apps stay on
#      127.0.0.1, Tailscale access keeps working, Combo Trader's files and
#      services are not touched.
#
# BEFORE running: at your .ae registrar's DNS panel for sahmi.ae, add
# A records for @, www, trader and paper pointing at this server's public
# IP (this script prints the IP and the exact records at the end).

set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

DOMAIN="sahmi.ae"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="/opt/logicon/spx-paper-trader"
# The hub keeps shared Schwab secrets in /opt/logicon/infra (tokens.json
# symlinked from combo-trader); prefer that, fall back to the plain layout.
if   [ -f /opt/logicon/infra/tokens.json ];        then TOKENS=/opt/logicon/infra/tokens.json
elif [ -f /opt/logicon/combo-trader/tokens.json ]; then TOKENS=/opt/logicon/combo-trader/tokens.json
else TOKENS=/opt/logicon/combo-trader/tokens.json
     echo "WARNING: no tokens.json found under /opt/logicon — is Combo Trader deployed here? (continuing)"
fi
echo "using Schwab tokens: $TOKENS"
# Owner of the app tree; on the dockerized hub the dir can be owned by a
# container UID with no passwd entry (stat prints UNKNOWN) — fall back to root.
LOGICON_USER="${LOGICON_USER:-$(stat -c %U /opt/logicon/combo-trader 2>/dev/null || echo root)}"
id "$LOGICON_USER" >/dev/null 2>&1 || LOGICON_USER=root

echo "== 1/5 Paper Trader -> ${APP_DIR} (user: ${LOGICON_USER}) =="
apt-get update -qq
apt-get install -y -qq python3 python3-pip debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null
pip3 install --break-system-packages --ignore-installed blinker -q flask requests pyyaml
mkdir -p "$APP_DIR"
rsync -a --exclude '.git' --exclude '__pycache__' --exclude 'data' "$REPO_DIR/" "$APP_DIR/"
chown -R "$LOGICON_USER":"$LOGICON_USER" "$APP_DIR"
sed -e "s/__LOGICON_USER__/${LOGICON_USER}/" -e "s|__TOKENS_FILE__|${TOKENS}|" \
    "$REPO_DIR/deploy/logicon-paper.service" > /etc/systemd/system/logicon-paper.service
systemctl daemon-reload
systemctl enable --now logicon-paper
systemctl --no-pager --lines=0 status logicon-paper | head -3

echo "== 2/5 Caddy =="
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi

echo "== 3/5 Dashboard password =="
read -rp  "  username for the web login [tariq]: " AUTH_USER
AUTH_USER="${AUTH_USER:-tariq}"
while :; do
  read -rsp "  password (typing hidden, min 12 chars): " PW1; echo
  read -rsp "  repeat: " PW2; echo
  [ "$PW1" = "$PW2" ] && [ "${#PW1}" -ge 12 ] && break
  echo "  mismatch or too short — again."
done
AUTH_HASH="$(caddy hash-password --plaintext "$PW1")"
unset PW1 PW2

echo "== 4/5 Caddyfile -> /etc/caddy/Caddyfile =="
[ -f /etc/caddy/Caddyfile ] && cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%s)"
sed -e "s|__AUTH_USER__|${AUTH_USER}|g" -e "s|__AUTH_HASH__|${AUTH_HASH}|g" \
    "$REPO_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy

echo "== 5/5 Firewall: allow HTTPS =="
ufw allow 80/tcp  >/dev/null   # Let's Encrypt HTTP-01 + redirect to HTTPS
ufw allow 443/tcp >/dev/null
ufw status | sed 's/^/    /'

IP="$(curl -4fs https://ifconfig.me || echo '<server public IP>')"
cat <<EOF

============================================================
DONE ON THE SERVER. Now add these DNS records for ${DOMAIN}
at your .ae registrar (where the domain list you have lives):

    Type  Host     Value
    A     @        ${IP}
    A     www      ${IP}
    A     trader   ${IP}
    A     paper    ${IP}

Within a few minutes of DNS resolving, Caddy fetches HTTPS
certificates automatically and these go live:

    https://trader.${DOMAIN}   -> Combo Trader platform
    https://paper.${DOMAIN}    -> SPX Paper Trader dashboard

Both prompt for the username/password you just set.
Tailscale access is unchanged and keeps working as backup.
============================================================
EOF
