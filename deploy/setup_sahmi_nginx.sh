#!/usr/bin/env bash
# setup_sahmi_nginx.sh — serve trader/paper.sahmi.ae via the hub's EXISTING nginx
# ==============================================================================
# Use this instead of setup_sahmi.sh's Caddy step when the hub already runs
# nginx on ports 80/443 (it serves the Logicon client portal behind Cloudflare,
# which is why Caddy could not bind and sahmi.ae showed the portal).
#
# What it does — without touching any existing nginx site:
#   1. Disables the Caddy service the earlier script enabled (it never bound).
#   2. Asks for the dashboard username/password (htpasswd via openssl).
#   3. Generates a self-signed cert for *.sahmi.ae (Cloudflare fronts the
#      public TLS; this cert only encrypts Cloudflare -> hub).
#   4. Adds ONE new nginx config with server blocks:
#        trader.sahmi.ae -> 127.0.0.1:5050   (Combo Trader)
#        paper.sahmi.ae  -> 127.0.0.1:5250   (Paper dashboard)
#        sahmi.ae / www  -> redirect to trader
#      all behind basic auth, then nginx -t && reload.
#
# AFTER running, two clicks in the Cloudflare dashboard for sahmi.ae:
#   - DNS -> Records: set all four records back to **Proxied** (orange cloud).
#   - SSL/TLS -> Overview: set encryption mode to **Full**.
#
# Run:  sudo bash setup_sahmi_nginx.sh

set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

DOMAIN="sahmi.ae"
CERT_DIR="/etc/nginx/sahmi-certs"
HTPASSWD="/etc/nginx/.sahmi_htpasswd"
CONF="/etc/nginx/sites-available/sahmi.conf"

command -v nginx >/dev/null || { echo "nginx not found — this script is for the nginx hub"; exit 1; }

echo "== 1/4 Disable Caddy (ports are nginx's here) =="
systemctl disable --now caddy 2>/dev/null || true

echo "== 2/4 Dashboard password =="
read -rp  "  username for the web login [tariq]: " AUTH_USER
AUTH_USER="${AUTH_USER:-tariq}"
while :; do
  read -rsp "  password (typing hidden, min 12 chars): " PW1; echo
  read -rsp "  repeat: " PW2; echo
  [ "$PW1" = "$PW2" ] && [ "${#PW1}" -ge 12 ] && break
  echo "  mismatch or too short — again."
done
printf '%s:%s\n' "$AUTH_USER" "$(openssl passwd -apr1 "$PW1")" > "$HTPASSWD"
chmod 640 "$HTPASSWD"; chown root:www-data "$HTPASSWD" 2>/dev/null || true
unset PW1 PW2

echo "== 3/4 Origin certificate (encrypts Cloudflare -> hub) =="
mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/sahmi.crt" ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$CERT_DIR/sahmi.key" -out "$CERT_DIR/sahmi.crt" \
    -subj "/CN=*.${DOMAIN}" \
    -addext "subjectAltName=DNS:${DOMAIN},DNS:*.${DOMAIN}" >/dev/null 2>&1
  chmod 600 "$CERT_DIR/sahmi.key"
fi

echo "== 4/4 nginx sites for ${DOMAIN} =="
cat > "$CONF" <<EOF
# sahmi.ae — Combo Trader + SPX Paper Trader (added by spx-0DTE-v1 deploy).
# Public TLS is terminated by Cloudflare (records Proxied, SSL mode Full);
# this self-signed cert encrypts the Cloudflare->origin hop only.
# Existing sites (the client portal) are untouched: these blocks match only
# the sahmi.ae hostnames.

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

    auth_basic           "Logicon Trader";
    auth_basic_user_file ${HTPASSWD};

    location / {
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
}

server {
    listen 80;
    listen 443 ssl;
    server_name paper.${DOMAIN};
    ssl_certificate     ${CERT_DIR}/sahmi.crt;
    ssl_certificate_key ${CERT_DIR}/sahmi.key;

    auth_basic           "SPX Paper Trader";
    auth_basic_user_file ${HTPASSWD};

    location / {
        proxy_pass http://127.0.0.1:5250;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
}
EOF
ln -sf "$CONF" /etc/nginx/sites-enabled/sahmi.conf
nginx -t
systemctl reload nginx

cat <<EOF

============================================================
DONE ON THE SERVER. Now two settings in the Cloudflare
dashboard for ${DOMAIN}:

  1. DNS -> Records: click Edit on each of the four records
     (@, www, trader, paper) and switch Proxy status back to
     **Proxied** (orange cloud). Save.

  2. SSL/TLS -> Overview: set the encryption mode to **Full**.

A minute later:

    https://trader.${DOMAIN}   -> Combo Trader platform
    https://paper.${DOMAIN}    -> SPX Paper Trader dashboard

Both prompt for the username/password you just set.
The client portal on this hub is completely untouched.
============================================================
EOF
