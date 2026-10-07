# Installation Guide

This guide covers production deployment of the NiFi NAR Upload Manager.

## Prerequisites

- Docker 24+ and Docker Compose v2 (recommended), **or**
- Python 3.12+ and Node.js 20+ for bare-metal installs
- SSH access (key or password) from the backend host to every NiFi server
- (Optional) Keycloak 24+ for SSO
- (Optional) PostgreSQL 16 for the database

## 1. Configure

```bash
cp .env.example .env
```

Minimum production changes:

| Variable | Why |
|---|---|
| `SECRET_KEY` | Generate with `openssl rand -hex 32`. Protects JWTs and encrypts stored secrets. |
| `AUTH_DEV_MODE` | Set `false` when using Keycloak. |
| `CORS_ORIGINS` | Add your real frontend origin, e.g. `https://nar-manager.example.com`. |
| `NEXT_PUBLIC_API_URL` | Public URL of the backend API, e.g. `https://nar-api.example.com`. |
| `DATABASE_URL` | Switch to PostgreSQL for production loads. |
| `KEYCLOAK_*` | Point at your Keycloak realm (see §4). |

## 2. Start with Docker Compose

```bash
docker compose up --build -d
docker compose exec backend python seed.py   # optional demo data
```

> `NEXT_PUBLIC_API_URL` is baked into the frontend bundle at image build time
> (passed as a Docker build arg from `.env`). If you change it, rebuild with
> `docker compose up --build frontend`.

Data persists in the `nar-data` volume (SQLite DB, uploaded NARs, backups, logs).

### PostgreSQL

```bash
docker compose --profile postgres up -d postgres
# in .env:
DATABASE_URL=postgresql://narmgr:narmgr@<host>:5432/nar_manager
```

Migrations run automatically at container start (`alembic upgrade head`).
To run manually: `docker compose exec backend alembic upgrade head`.

## 3. Bare-metal install

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Frontend:

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=https://nar-api.example.com npm run build
npm start   # serves on :3000
```

Put a reverse proxy (nginx/Traefik) with TLS in front of both. Example nginx rules:

```nginx
location /        { proxy_pass http://127.0.0.1:3000; }
location /api/    { proxy_pass http://127.0.0.1:8000; }
location /docs    { proxy_pass http://127.0.0.1:8000; }
```

If the API is served from the same origin, set `NEXT_PUBLIC_API_URL` to the external URL
(CORS is already restricted via `CORS_ORIGINS`).

## 4. Keycloak SSO

### Option A — bundled dev Keycloak

```bash
docker compose --profile sso up -d keycloak
```

This imports `docs/keycloak-realm.json` (realm `nar-manager`, client
`nar-manager-frontend`, roles `nar-admin`/`nar-developer`/`nar-viewer`, demo users).

### Option B — existing Keycloak

1. Create realm `nar-manager`.
2. Create a **confidential** client `nar-manager-frontend` (standard flow enabled) with
   redirect URI `https://<frontend>/login/callback`.
3. Set in `.env`:

```ini
AUTH_DEV_MODE=false
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=https://keycloak.example.com
KEYCLOAK_REALM=nar-manager
KEYCLOAK_CLIENT_ID=nar-manager-frontend
KEYCLOAK_CLIENT_SECRET=<client secret>
```

4. **Choose where roles are managed** (default: in the app):

| Mode | Configuration | Behavior |
|---|---|---|
| **App-managed roles** (default) | `KEYCLOAK_ROLE_SYNC_ENABLED=false` | Keycloak authenticates only. New SSO users are auto-provisioned as `DEFAULT_USER_ROLE` (viewer). Admins assign roles in **Settings → Users**. No realm-role setup needed in Keycloak. |
| **Keycloak-managed roles** | `KEYCLOAK_ROLE_SYNC_ENABLED=true` | Realm roles `nar-admin` / `nar-developer` / `nar-viewer` sync into the app on every login and overwrite local assignments. |

**Bootstrapping the first admin (app-managed mode):** add your SSO username to
`ADMIN_USERNAMES` in `.env` (comma-separated), restart, and sign in once — you will
receive the admin role automatically and can then manage everyone else in the UI:

```ini
ADMIN_USERNAMES=admin,jane.doe@example.com
```

Users are auto-provisioned on first login; email and display name always sync from the IdP.

## 5. Registering NiFi servers

For each NiFi host:

1. Create a dedicated SSH user (e.g. `nifi`) with write access to the NAR directory
   (usually `$NIFI_HOME/lib`) and permission to run the restart command
   (passwordless sudo for `systemctl restart nifi`).
2. Copy the backend's SSH public key to the host, or store a password in the server record.
3. In **Servers → Add Server**, fill in host, SSH details, directories and restart command.
4. Use **Test connection** to verify, and **Health** to see disk/CPU/memory/NiFi status.

> Deployments upload to `<nar_directory>/<filename>` and restart NiFi only when requested.

## 6. Backups

Backups are stored **on the backend host** under `BACKUP_DIRECTORY/<server>/<YYYY>/<MM>/<DD>/`
whenever a deployment replaces an existing remote file. Restore from **Backups → Restore**
or **Deployments → Rollback**.

## 7. Hardening checklist

- [ ] `SECRET_KEY` is random and private
- [ ] `AUTH_DEV_MODE=false` in production
- [ ] HTTPS terminated at the reverse proxy
- [ ] `CORS_ORIGINS` restricted to the frontend origin
- [ ] PostgreSQL instead of SQLite
- [ ] `LOG_LEVEL=INFO` or `WARNING`
- [ ] SSH keys (not passwords) for NiFi servers; least-privilege sudo for restart
- [ ] Regular volume backups of the DB + NAR store
- [ ] API tokens with minimal role + expiry for CI/CD

## 8. Upgrading

```bash
git pull
docker compose up --build -d     # migrations run automatically
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401` on every API call | Token expired — sign in again; check `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Deployment fails at SSH | **Servers → Test connection**; verify key path, user, sudoers |
| Checksum mismatch | Network corruption or proxy — retry; file never silently replaces |
| Frontend cannot reach API | `NEXT_PUBLIC_API_URL` must be reachable from the **browser**, not the container |
| Keycloak login loop | Redirect URI in client must match `${origin}/login/callback` exactly |
