#!/usr/bin/env bash
# setup_shine_gate.sh — one login for the whole estate: put shine.sahmi.ae
# behind the same nginx auth_request gate as trader/paper.sahmi.ae.
# =========================================================================
# Run on the hub (the gate from setup_sahmi_login.sh must already be up):
#     sudo bash /opt/logicon/spx-paper-trader/deploy/setup_shine_gate.sh
#
# What it does:
#   1. Rewrites the shine.sahmi.ae nginx vhost: proxy to 127.0.0.1:8795 as
#      before, but every request now passes auth_request against the gate
#      (127.0.0.1:5260). The gate cookie is scoped to .sahmi.ae, so ONE
#      sign-in (password + authenticator code) covers trader/paper/shine.
#   2. Keeps GET /api/rec public — the Auto-Invest desk and curl consumers
#      read the month's pick without a session (leaks nothing: see the
#      endpoint's docstring in shine/app.py).
#   3. Leaves TLS exactly as-is: Cloudflare Flexible -> origin :80. Adding
#      a :443 listener here would 521 — nginx has no shine cert
#      (PROJECT_SHINE.md §4).
#
# After it runs, drop Shine's own in-app login so there is only one login:
#     sudo systemctl edit shine     # delete the SHINE_PASSWORD
#                                   # (and SHINE_TOTP_SECRET) lines
#     sudo systemctl restart shine
# (Tailnet access http://hub:6052 bypasses nginx and is then open on the
#  tailnet, same as every other tailnet surface of the estate.)

set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

command -v nginx >/dev/null || { echo "nginx not found"; exit 1; }
curl -fsS -o /dev/null http://127.0.0.1:5260/gate/login \
  || { echo "gate not answering on 127.0.0.1:5260 — run setup_sahmi_login.sh first"; exit 1; }

# The hub's sahmi.conf may already carry a gated shine block (a later
# sahmi-nginx setup added one). A second vhost would only produce
# "conflicting server name ... ignored" — and lose, since sahmi.conf
# sorts first. Nothing to do in that case (2026-10-08, live hub).
if grep -q "server_name shine" /etc/nginx/sites-enabled/sahmi.conf 2>/dev/null; then
  grep -A30 "server_name shine" /etc/nginx/sites-enabled/sahmi.conf \
      | grep -q "auth_request" \
    && { echo "shine.sahmi.ae is already gated inside sahmi.conf — nothing to do."; exit 0; }
  echo "sahmi.conf serves shine WITHOUT auth_request — it would shadow this"
  echo "script's vhost. Remove that block first, then rerun."
  exit 1
fi

AVAIL=/etc/nginx/sites-available/shine.sahmi.ae
ENABLED=/etc/nginx/sites-enabled/shine.sahmi.ae

# back up whatever serves shine today (plain file in sites-enabled, or the
# sites-available target of a symlink)
for f in "$ENABLED" "$AVAIL"; do
  [ -f "$f" ] && [ ! -L "$f" ] && cp "$f" "$f.bak.$(date +%s)"
done

cat > "$AVAIL" <<'EOF'
# shine.sahmi.ae — Project Shine behind the estate sign-in gate.
# Written by spx-0DTE-v1 deploy/setup_shine_gate.sh. One login covers
# trader/paper/shine (gate cookie, domain .sahmi.ae). TLS: Cloudflare
# Flexible -> this :80 vhost (no :443 on purpose — no origin cert).
server {
    listen 80;
    server_name shine.sahmi.ae;

    # public on purpose: current month's pick only (see app.py /api/rec)
    location = /api/rec {
        proxy_pass http://127.0.0.1:8795;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location = /gate/check {
        internal;
        proxy_pass http://127.0.0.1:5260;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI $request_uri;
    }
    location /gate/ {
        proxy_pass http://127.0.0.1:5260;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location / {
        auth_request /gate/check;
        error_page 401 = @login;
        proxy_pass http://127.0.0.1:8795;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
    location @login {
        return 302 /gate/login?next=$request_uri;
    }
}
EOF
rm -f "$ENABLED"
ln -sf "$AVAIL" "$ENABLED"
nginx -t
systemctl reload nginx

cat <<'MSG'
============================================================
DONE — shine.sahmi.ae now uses the SAME sign-in as trader/
paper (one gate cookie for .sahmi.ae). /api/rec stays public.

Finish by removing Shine's own in-app login so exactly one
login remains:
    sudo systemctl edit shine    # delete the SHINE_PASSWORD
                                 # (and SHINE_TOTP_SECRET) lines
    sudo systemctl restart shine
============================================================
MSG
