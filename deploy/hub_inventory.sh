#!/usr/bin/env bash
# hub_inventory.sh — READ-ONLY snapshot of what runs on the hub (HUB_RUNBOOK.md §1).
# Prints names, owners, sizes, ports and paths — NEVER file contents of
# secrets. Safe to paste the output into a session.
#     sudo bash /opt/logicon/spx-paper-trader/deploy/hub_inventory.sh
set -uo pipefail
h() { echo; echo "== $*"; }

h "host"
hostnamectl 2>/dev/null | grep -E 'Static hostname|Operating System|Kernel' || uname -a
df -h / | tail -1
free -h | head -2

h "systemd services (logicon / shine / litestream / gate / caddy / nginx / docker / tailscale)"
systemctl list-units --type=service --all --no-pager --plain \
  | grep -E 'logicon|shine|litestream|gate|caddy|nginx|docker|tailscale|ib' | awk '{print $1, $3, $4}'

h "systemd timers"
systemctl list-timers --all --no-pager --plain | grep -E 'logicon|litestream|backup|update' | awk '{print $(NF-1), $NF}'

h "unit files we installed (ExecStart / User / WorkingDirectory)"
for f in /etc/systemd/system/logicon*.service /etc/systemd/system/shine*.service \
         /etc/systemd/system/litestream*.service /etc/systemd/system/*.service.d/*.conf; do
  [ -f "$f" ] || continue
  echo "-- $f"
  grep -E '^(ExecStart|User|WorkingDirectory|EnvironmentFile)=' "$f" | sed 's/^/   /'
  grep -E '^Environment=' "$f" | sed -E 's/(SECRET|PASSWORD|TOKEN|KEY)=[^ ]*/\1=<redacted>/Ig; s/^/   /'
done

h "docker containers + compose files"
docker ps -a --format '{{.Names}}  {{.Image}}  {{.Status}}' 2>/dev/null || echo "(no docker)"
for c in $(docker ps -aq 2>/dev/null); do
  docker inspect "$c" --format '{{.Name}}: project={{index .Config.Labels "com.docker.compose.project"}} file={{index .Config.Labels "com.docker.compose.project.config_files"}} dir={{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null
done

h "listening ports (process)"
ss -ltnp 2>/dev/null | awk 'NR>1 {print $4, $6}' | sed 's/users:((//; s/,pid=.*//' | sort -u

h "nginx sites + server_names"
ls -l /etc/nginx/sites-enabled/ 2>/dev/null
grep -Rh 'server_name' /etc/nginx/sites-enabled/ 2>/dev/null | sort -u

h "tailscale"
tailscale status --self 2>/dev/null | head -3
tailscale serve status 2>/dev/null | head -20

h "/opt/logicon tree (depth 2) — owners"
find /opt/logicon -maxdepth 2 -printf '%M %u:%g %p\n' 2>/dev/null | grep -vE '/\.git|__pycache__' | sort -k3

h "databases (path, owner, size, journal mode)"
for db in $(find /opt/logicon /root -name '*.sqlite' -size +0 2>/dev/null | grep -v '/cache/'); do
  mode=$(python3 -c "import sqlite3;print(sqlite3.connect('file:$db?mode=ro',uri=True).execute('PRAGMA journal_mode').fetchone()[0])" 2>/dev/null || echo '?')
  echo "$(stat -c '%u:%g %s' "$db") $mode $db"
done

h "secret / state files — PRESENCE ONLY (never contents)"
for f in /opt/logicon/infra/.env /opt/logicon/infra/tokens.json /opt/logicon/infra/r2-backup.env \
         /opt/logicon/combo-trader/.env /opt/logicon/combo-trader/tokens.json \
         /opt/logicon/combo-trader/logicon_config.json /opt/logicon/combo-trader/.logicon_session.json \
         /opt/logicon/spx-paper-trader/gate_secret /opt/logicon/spx-paper-trader/gate_credentials.json \
         /etc/default/litestream /etc/litestream*.yml; do
  [ -e "$f" ] && echo "present  $(stat -c '%a %u' "$f")  $f" || echo "absent   $f"
done
find / -xdev \( -name 'docker-compose*.yml' -o -name 'compose*.yml' -o -name '.env' \) \
  -not -path '*/node_modules/*' -not -path '/proc/*' 2>/dev/null | grep -vE '^/home/.*/\.cache' | head -20

h "git checkouts that deploy (branch, head)"
for d in /root/combo-trader /opt/logicon/combo-beta /root/spx-paper-trader; do
  [ -d "$d/.git" ] && echo "$d  $(git -C "$d" rev-parse --abbrev-ref HEAD) $(git -C "$d" rev-parse --short HEAD)"
done

h "cron"
crontab -l 2>/dev/null | grep -v '^#' || echo "(no root crontab)"
ls /etc/cron.d 2>/dev/null

echo; echo "== done (read-only; no secrets printed)"
