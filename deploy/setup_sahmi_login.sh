#!/usr/bin/env bash
# setup_sahmi_login.sh — replace the browser basic-auth popup with a proper
# in-page sign-in for trader/paper.sahmi.ae (one login covers both).
# ==========================================================================
# Run AFTER setup_sahmi_nginx.sh, on the hub:
#     cd ~/spx-paper-trader && git pull
#     cd deploy && sudo bash setup_sahmi_login.sh
#
# What it does:
#   1. Asks for the sign-in username/password and stores them for gate.py
#      (PBKDF2 hash + random cookie secret, chmod 600, never in git).
#   2. Installs/updates the app at /opt/logicon/spx-paper-trader and starts
#      the gate service (127.0.0.1:5260).
#   3. Rewrites the sahmi nginx config: basic_auth popup -> auth_request
#      against the gate, with a styled login page at /gate/login.
#      Other nginx sites (the client portal) stay untouched.

set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

DOMAIN="sahmi.ae"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="/opt/logicon/spx-paper-trader"
CERT_DIR="/etc/nginx/sahmi-certs"
CONF="/etc/nginx/sites-available/sahmi.conf"

command -v nginx >/dev/null || { echo "nginx not found"; exit 1; }
[ -f "$CERT_DIR/sahmi.crt" ] || { echo "run setup_sahmi_nginx.sh first (no cert dir)"; exit 1; }
LOGICON_USER="${LOGICON_USER:-$(stat -c %U /opt/logicon/combo-trader 2>/dev/null || echo root)}"
id "$LOGICON_USER" >/dev/null 2>&1 || LOGICON_USER=root

echo "== 1/3 Sign-in credentials =="
read -rp  "  username [tariq]: " AUTH_USER
AUTH_USER="${AUTH_USER:-tariq}"
while :; do
  read -rsp "  password (typing hidden, min 12 chars): " PW1; echo
  read -rsp "  repeat: " PW2; echo
  [ "$PW1" = "$PW2" ] && [ "${#PW1}" -ge 12 ] && break
  echo "  mismatch or too short — again."
done
mkdir -p "$APP_DIR"
GATE_PW="$PW1" python3 - "$AUTH_USER" "$APP_DIR/gate_credentials.json" <<'PY'
import hashlib, json, os, secrets, sys
user, out = sys.argv[1], sys.argv[2]
pw = os.environ["GATE_PW"]
salt = secrets.token_bytes(16)
h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()
with open(out, "w") as f:
    json.dump({"user": user, "salt": salt.hex(), "hash": h}, f)
os.chmod(out, 0o600)
PY
unset PW1 PW2

echo "== 2/3 Gate service =="
rsync -a --exclude '.git' --exclude '__pycache__' --exclude 'data' \
      --exclude 'gate_credentials.json' --exclude 'gate_secret' \
      "$REPO_DIR/" "$APP_DIR/"
chown -R "$LOGICON_USER":"$LOGICON_USER" "$APP_DIR"
sed "s/__LOGICON_USER__/${LOGICON_USER}/" "$REPO_DIR/deploy/logicon-gate.service" \
    > /etc/systemd/system/logicon-gate.service
systemctl daemon-reload
systemctl enable --now logicon-gate
systemctl restart logicon-gate
sleep 1
systemctl is-active logicon-gate >/dev/null || { echo "gate failed to start:"; journalctl -u logicon-gate -n 10 --no-pager; exit 1; }

echo "== 3/3 nginx: popup -> login page =="
[ -f "$CONF" ] && cp "$CONF" "${CONF}.bak.$(date +%s)"
cat > "$CONF" <<EOF
# sahmi.ae — Combo Trader + SPX Paper Trader (added by spx-0DTE-v1 deploy).
# Auth: signed-cookie sign-in page served by the local gate (127.0.0.1:5260);
# nginx checks every request via auth_request. One login covers both hosts
# (cookie domain .${DOMAIN}). Public TLS terminates at Cloudflare (Proxied +
# SSL mode Full); the self-signed cert covers the Cloudflare->origin hop.
# Existing sites (the client portal) are untouched.

server {
    listen 80;
    listen 443 ssl;
    server_name ${DOMAIN} www.${DOMAIN};
    ssl_certificate     ${CERT_DIR}/sahmi.crt;
    ssl_certificate_key ${CERT_DIR}/sahmi.key;
    return 302 https://trader.${DOMAIN}\$request_uri;
}

server {
    listen 80;
    listen 443 ssl;
    server_name trader.${DOMAIN};
    ssl_certificate     ${CERT_DIR}/sahmi.crt;
    ssl_certificate_key ${CERT_DIR}/sahmi.key;

    location = /gate/check {
        internal;
        proxy_pass http://127.0.0.1:5260;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI \$request_uri;
    }
    location /gate/ {
        proxy_pass http://127.0.0.1:5260;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    location / {
        auth_request /gate/check;
        error_page 401 = @login;
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }
    location @login {
        return 302 /gate/login?next=\$request_uri;
    }
}

server {
    listen 80;
    listen 443 ssl;
    server_name paper.${DOMAIN};
    ssl_certificate     ${CERT_DIR}/sahmi.crt;
    ssl_certificate_key ${CERT_DIR}/sahmi.key;

    location = /gate/check {
        internal;
        proxy_pass http://127.0.0.1:5260;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI \$request_uri;
    }
    location /gate/ {
        proxy_pass http://127.0.0.1:5260;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    location / {
        auth_request /gate/check;
        error_page 401 = @login;
        proxy_pass http://127.0.0.1:5250;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
    location @login {
        return 302 /gate/login?next=\$request_uri;
    }
}
EOF
ln -sf "$CONF" /etc/nginx/sites-enabled/sahmi.conf
nginx -t
systemctl reload nginx

cat <<EOF

============================================================
DONE. The browser popup is gone — https://trader.${DOMAIN}
and https://paper.${DOMAIN} now show a proper sign-in page.
One login covers both sites for 30 days; /gate/logout signs out.

If you haven't yet, finish the two Cloudflare settings so the
padlock is clean:
  - DNS -> Records: all four records **Proxied** (orange)
  - SSL/TLS -> Overview: mode **Full**
============================================================
EOF
