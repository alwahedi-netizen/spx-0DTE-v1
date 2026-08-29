# Hosting Combo Trader + Paper Trader on kbar.ae

Domain chosen: **kbar.ae** — currently parked/unused, and a "K-bar" is the
candlestick bar itself, so it reads like it was bought for a trading desk.

## What you get

| URL | App | Where it runs |
|---|---|---|
| `https://trader.kbar.ae` | Combo Trader platform (port 5050) | existing server |
| `https://paper.kbar.ae` | SPX Paper Trader dashboard (port 5250) | same server |
| `https://kbar.ae` | redirects to trader | — |

- Automatic HTTPS (Let's Encrypt, renews itself).
- A **username/password prompt on every page** — nothing is public. The
  platform routes real orders and holds Schwab tokens; the password wall is
  not optional.
- Combo Trader itself is untouched: it stays bound to 127.0.0.1 and its
  files/services are not modified. Caddy simply proxies in front of it.
- Tailscale access continues to work exactly as before (fallback).

## Steps

1. **On the server** (the one already running Combo Trader):
   ```bash
   git clone https://github.com/alwahedi-netizen/spx-0DTE-v1 ~/spx-paper-trader
   cd ~/spx-paper-trader/deploy
   sudo bash setup_kbar.sh
   ```
   It asks you to choose the web username/password, then prints the
   server's public IP and the exact DNS records.

2. **At the .ae registrar** (the panel showing your domain list): open DNS
   management for `kbar.ae` and add the four A records the script printed
   (`@`, `www`, `trader`, `paper` → server IP). The domain shows "Parked"
   today, so there are no existing records to conflict with.

3. Wait a few minutes for DNS, then open `https://trader.kbar.ae` and
   `https://paper.kbar.ae` and log in with the password you chose.

## If the server has no public IP (behind NAT / home network)

DNS A records only work if the server is directly reachable from the
internet. If it is not (it was Tailscale-only until now, so check), use a
**Cloudflare Tunnel** instead — no open ports at all:

1. Add `kbar.ae` to a free Cloudflare account and point the domain's
   nameservers at Cloudflare (at the .ae registrar).
2. On the server: install `cloudflared`, create a tunnel, and map
   `trader.kbar.ae → http://127.0.0.1:5050` and
   `paper.kbar.ae → http://127.0.0.1:5250`.
3. Keep the Caddy basic-auth in front (point the tunnel at Caddy on
   127.0.0.1:443/80 instead), or use Cloudflare Access for the login wall.

## Security notes

- The original deployment model was "never internet-reachable, Tailscale
  only". Putting it on a domain is a real increase in exposure — the
  password wall (bcrypt, over HTTPS only) is what stands between the
  internet and your order routing. Use a long unique password; change it by
  re-running `sudo bash setup_kbar.sh` (it re-prompts) or editing
  `/etc/caddy/Caddyfile` with `caddy hash-password`.
- Ports 5050/5151/5250 stay on 127.0.0.1 — only Caddy's 80/443 are open.
- If you only ever browse from your own devices, consider keeping
  Tailscale as the primary path and treating kbar.ae as convenience access.
