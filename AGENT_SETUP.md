# PingCRM Agent Setup Runbook

> **For AI agents (Claude Code, Cursor, Codex, etc.):** This is an executable runbook to deploy PingCRM as a real, running instance the user can use daily. Follow it top-to-bottom. Stop at every **ASK USER** gate and wait for input. Verify each **CHECK** before continuing.

This guide assumes the user wants a **self-hosted production deployment** on their own server, reachable at their own domain over HTTPS. For a managed alternative, point them at the [One-Click Deploy](README.md#one-click-deploy) section instead.

---

## Phase 0 — Gather Inputs

**ASK USER** for the following. Do not proceed until you have all four:

1. **Domain name** they own (e.g. `crm.example.com`). They must be able to edit DNS records for it.
2. **Server access** — one of:
   - SSH access to an existing Linux VPS (Ubuntu 22.04+ recommended), with root or sudo, OR
   - A cloud account (DigitalOcean, Hetzner, Linode, AWS) where you can provision one. Smallest viable size: 2 vCPU / 4 GB RAM / 40 GB disk.
3. **Anthropic API key** (`sk-ant-...`) — required. Get one at https://console.anthropic.com. PingCRM is unusable without it (drives suggestions, classification, drafts).
4. **Which integrations** they want enabled now. All are optional; you can add them later. Most users start with just **Gmail**.
   - Gmail (email sync, BCC logging) → needs Google OAuth client
   - Twitter/X (DMs, mentions, bios) → needs Twitter OAuth app + bird CLI cookies
   - Telegram (chats, groups, bios) → needs Telegram API ID + hash
   - LinkedIn → no creds; uses a Chrome extension installed later
   - WhatsApp → needs WhatsApp sidecar (auto-started) + QR scan after deploy

---

## Phase 1 — Provision the Server

Skip this phase if the user already has a VPS with SSH access.

1. Provision the smallest tier listed above with **Ubuntu 22.04 LTS** or newer.
2. Note the public IPv4 address.
3. Confirm SSH works: `ssh root@<ip>`.

**CHECK:** `ssh root@<ip> 'uname -a'` returns Linux kernel info.

---

## Phase 2 — Point DNS at the Server

**ASK USER** to create a DNS **A record**:

| Type | Name | Value |
|---|---|---|
| A | `crm` (or whatever subdomain) | `<server IPv4>` |

Wait for propagation:

```bash
dig +short <their-domain>
# expected: <server IPv4>
```

**CHECK:** `dig +short` returns the server IP. Caddy needs this resolving to issue the TLS cert. Do **not** continue until DNS resolves correctly — Let's Encrypt will rate-limit failed attempts.

---

## Phase 3 — Install Docker on the Server

SSH to the server and run:

```bash
ssh root@<server-ip> 'curl -fsSL https://get.docker.com | sh && systemctl enable --now docker'
```

**CHECK:** `ssh root@<server-ip> 'docker compose version'` prints v2.x.

---

## Phase 4 — Clone the Repo on the Server

```bash
ssh root@<server-ip> << 'EOF'
mkdir -p /opt/pingcrm
cd /opt/pingcrm
git clone https://github.com/sneg55/pingcrm.git .
EOF
```

**CHECK:** `ssh root@<server-ip> 'ls /opt/pingcrm/docker-compose.prod.yml'` succeeds.

---

## Phase 5 — Edit Caddyfile and Frontend URL for the User's Domain

The default `Caddyfile` and `docker-compose.prod.yml` are pinned to `pingcrm.sawinyh.com` (the maintainer's instance). Replace with the user's domain.

On the server (or by editing locally and `scp`'ing up):

```bash
ssh root@<server-ip> "cd /opt/pingcrm && \
  sed -i 's|pingcrm.sawinyh.com|<user-domain>|g' Caddyfile docker-compose.prod.yml"
```

**CHECK:** `grep <user-domain> /opt/pingcrm/Caddyfile /opt/pingcrm/docker-compose.prod.yml` shows matches; `grep sawinyh` shows none.

---

## Phase 6 — Generate Secrets and Write `.env`

Generate three random secrets locally:

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# fallback if cryptography is not installed:
# python3 -c "import base64, secrets; print('ENCRYPTION_KEY=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Compose `.env` on the server. Replace placeholders. Fill in only the integration vars the user picked in Phase 0 — the rest can stay empty.

```bash
ssh root@<server-ip> "cat > /opt/pingcrm/.env" << 'EOF'
# --- Required ---
POSTGRES_PASSWORD=<generated above>
SECRET_KEY=<generated above>
ENCRYPTION_KEY=<generated above>
ANTHROPIC_API_KEY=sk-ant-...

# --- Gmail (optional) ---
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=https://<user-domain>/auth/google/callback

# --- Twitter/X (optional) ---
TWITTER_CLIENT_ID=
TWITTER_CLIENT_SECRET=
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_BEARER_TOKEN=
AUTH_TOKEN=
CT0=

# --- Telegram (optional) ---
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# --- WhatsApp (optional) ---
WHATSAPP_WEBHOOK_SECRET=<run: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
EOF
```

**CHECK:** `ssh root@<server-ip> 'wc -l /opt/pingcrm/.env'` returns >10 lines and `grep -c ^[A-Z] /opt/pingcrm/.env` shows the var count.

> **Security:** `chmod 600 /opt/pingcrm/.env` on the server.

---

## Phase 7 — Set Up OAuth Apps for Selected Integrations

Only do the sub-steps for integrations the user picked in Phase 0.

### 7a. Gmail (Google OAuth)

**ASK USER** to:
1. Go to https://console.cloud.google.com → create a project.
2. Enable the **Gmail API**.
3. Create OAuth 2.0 credentials → **Web application**.
4. Add authorized redirect URI: `https://<user-domain>/auth/google/callback`.
5. Set OAuth consent screen to **In production** (Testing mode expires tokens after 7 days — this trips up most setups).
6. Paste `Client ID` and `Client Secret` back to you.

Then update `.env` on the server with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

### 7b. Twitter/X

**ASK USER** to:
1. Go to https://developer.twitter.com → create a project + app.
2. Enable **OAuth 2.0**, set type to **Web App**, callback URL `https://<user-domain>/auth/twitter/callback`.
3. Paste `Client ID`, `Client Secret`, `API Key`, `API Secret`, `Bearer Token`.
4. For mention/reply/bio sync, also paste `auth_token` and `ct0` cookies from a logged-in browser session (used by bird CLI).

Update `.env` accordingly.

### 7c. Telegram

**ASK USER** to:
1. Go to https://my.telegram.org → API development tools.
2. Create an app, copy `api_id` (number) and `api_hash`.

Update `.env` with `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`. The Telegram client login (phone number + code) happens later through the running app's Settings page.

---

## Phase 8 — Boot the Stack

```bash
ssh root@<server-ip> 'cd /opt/pingcrm && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d'
```

This pulls prebuilt images from `ghcr.io/sneg55/pingcrm/*` (backend, worker, frontend, whatsapp-sidecar) plus `postgres`, `redis`, `caddy`. First boot takes 2–4 minutes including TLS cert issuance.

Watch the logs:

```bash
ssh root@<server-ip> 'cd /opt/pingcrm && docker compose -f docker-compose.prod.yml logs -f --tail=100'
```

Look for:
- `caddy` issuing a cert for `<user-domain>` (`certificate obtained successfully`)
- `backend` running migrations and reporting `Application startup complete`
- `worker` reporting `celery@... ready`

**CHECK:**

```bash
curl -sS https://<user-domain>/api/health
# expected: {"status":"ok"} (or similar)
```

If TLS fails: re-verify Phase 2 DNS, then `docker compose restart caddy`.

---

## Phase 9 — Create the First User

PingCRM is single-tenant — the first sign-up is the owner.

1. Open `https://<user-domain>` in the user's browser.
2. **ASK USER** to register with their email + a password.
3. Sign in.

**CHECK:** Dashboard loads at `/dashboard`.

---

## Phase 10 — Connect Integrations

Inside the running app (`/settings`), have the user click **Connect** for each integration enabled in Phase 7. Each runs through its own auth flow (OAuth redirect for Google/Twitter, phone code for Telegram, QR scan for WhatsApp).

**CHECK:** Settings page shows each connected account with a green status indicator.

---

## Phase 11 — Optional: Install Chrome Extension for LinkedIn

If the user wants LinkedIn:

1. Download or build `chrome-extension/` from this repo (see `chrome-extension/README.md`).
2. Load unpacked in Chrome → `chrome://extensions` → Developer mode → Load unpacked.
3. In PingCRM Settings → LinkedIn → generate a pairing code, paste into the extension.

Cookies stay in the browser; nothing leaves the user's machine.

---

## Phase 12 — Verification Checklist

Run all of these. Every one must pass before reporting success.

```bash
# 1. All containers healthy
ssh root@<server-ip> 'cd /opt/pingcrm && docker compose -f docker-compose.prod.yml ps'
# expected: backend, worker, frontend, postgres, redis, caddy all "Up" / "healthy"

# 2. API responds
curl -sS https://<user-domain>/api/health

# 3. Frontend serves
curl -sS -o /dev/null -w '%{http_code}\n' https://<user-domain>/
# expected: 200

# 4. TLS valid
curl -sSI https://<user-domain>/ | head -1
# expected: HTTP/2 200

# 5. Worker processed at least one beat tick (after ~1 min)
ssh root@<server-ip> 'cd /opt/pingcrm && docker compose -f docker-compose.prod.yml logs worker --tail=50' | grep -i "beat\|task succeeded"
```

---

## Common Failure Modes and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| `caddy` keeps restarting, logs show ACME failure | DNS not propagated, or port 80/443 blocked | Re-verify Phase 2; check firewall (`ufw allow 80,443/tcp`) |
| `backend` exits with `KeyError: SECRET_KEY` | `.env` not loaded | Confirm `.env` exists at `/opt/pingcrm/.env`; restart with `docker compose --env-file .env -f docker-compose.prod.yml up -d` |
| `backend` logs `password authentication failed for user "pingcrm"` | DB password mismatch (volume initialized with old password) | If first boot: `docker compose down -v` then `up -d`. If existing data: reset password inside the postgres container |
| OAuth callback fails with `redirect_uri_mismatch` | Domain in OAuth app ≠ deployed domain | Update authorized redirect URI in Google/Twitter console to match exactly |
| Google sign-in works for 7 days then breaks | OAuth consent screen still in **Testing** mode | Switch to **In production** at Google Cloud Console |
| `worker` logs `another operation is in progress` | Stale connections after restart | `docker compose restart worker` |

---

## Updating Later

```bash
ssh root@<server-ip> 'cd /opt/pingcrm && \
  git pull && \
  docker compose -f docker-compose.prod.yml pull && \
  docker compose -f docker-compose.prod.yml up -d && \
  docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head'
```

CI publishes new images on every push to `main`; `docker compose pull` fetches the latest tag.

---

## Backups (recommended before going live)

```bash
ssh root@<server-ip> 'cd /opt/pingcrm && \
  docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U pingcrm pingcrm | gzip > /root/pingcrm-backup-$(date +%F).sql.gz'
```

Suggest the user wire this into a daily cron and ship the output off-server (S3, restic, borg).
