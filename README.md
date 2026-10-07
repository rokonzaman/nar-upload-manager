# NiFi NAR Upload Manager

Enterprise-grade web application for deploying and managing **Apache NiFi NAR (NiFi Archive)**
files across multiple NiFi environments — without manually copying files to servers.

Upload custom processor bundles once, then deploy them to DEV, QA, UAT and PROD NiFi servers
over SSH/SFTP with automatic backup, checksum verification, rollback, retention policies,
Nexus integration and a full audit trail.

![Stack](https://img.shields.io/badge/stack-Next.js%2014%20%C2%B7%20FastAPI%20%C2%B7%20SQLite%2FPostgreSQL-blue)

---

## Features

| Area | Capabilities |
|---|---|
| **Dashboard** | Server/bundle/storage counters, upload & deployment charts, storage growth, most-deployed bundles, recent activity |
| **Multi-server** | Register unlimited NiFi servers (hostname, SSH, directories, restart command, environment, enabled flag); test connections; live health (disk/CPU/memory/NiFi process) |
| **Server groups** | Group nodes into clusters (e.g. 3-node PROD cluster) and deploy a NAR to every node in one operation — per-node status, independent failure handling |
| **NAR Upload** | Drag & drop, multi-file, progress bars, duplicate detection, replace mode, SHA256/MD5 checksums, manifest metadata extraction, path-traversal protection, size limits |
| **Repository** | Grouped artifact → version tree, flat view, search/filter/sort/pagination, tags, pin, deprecate, compare two versions, bulk delete |
| **Deployment** | Multi-server deployments, backup-before-replace, SFTP upload, remote checksum verification, optional NiFi restart, dry-run mode, step-by-step live log, one-click rollback |
| **Backups** | Automatic dated backup layout `backup/<server>/<YYYY>/<MM>/<DD>/`, one-click restore, orphan cleanup |
| **Nexus** | Multiple Nexus servers, repository browsing, artifact search, direct import with checksum verification, scheduled sync |
| **Retention** | Keep-latest-N + keep-newer-than-X-days, dry run, preview report, confirmation-gated execution, scheduled cron cleanup, pinned/deployed protection |
| **Audit** | Every action logged (user, IP, browser, target, result); search, filter, CSV export |
| **Notifications** | Email (SMTP), Slack, Teams, generic webhooks per event |
| **Security** | Keycloak OIDC SSO or local dev login, JWT, RBAC (admin/developer/viewer), rate-limited login, encrypted secrets at rest, security headers, API tokens for CI/CD |

## Architecture

```
┌─────────────────┐      REST / JWT      ┌──────────────────┐      SSH/SFTP     ┌───────────────┐
│  Next.js 14 UI  │ ───────────────────▶ │  FastAPI backend │ ────────────────▶ │  NiFi servers │
│  (TypeScript)   │                      │  (Python 3.12+)  │                   │  DEV/QA/PROD  │
└─────────────────┘                      │                  │ ──── HTTPS ────▶  │  Nexus repos  │
        ▲                                │  SQLAlchemy +    │                   └───────────────┘
        │ OIDC                           │  Alembic         │
┌───────┴─────────┐                      │  APScheduler     │
│    Keycloak     │ ◀── JWT (JWKS) ───── │  SQLite/Postgres │
└─────────────────┘                      └──────────────────┘
```

## Quick start (Docker Compose)

```bash
cp .env.example .env
# edit .env — at minimum set SECRET_KEY (openssl rand -hex 32)

docker compose up --build
```

- UI: http://localhost:3000
- API + Swagger docs: http://localhost:8000/docs
- Default login (dev mode): **admin / admin123**

Seed demo data (servers, sample bundles, users):

```bash
docker compose exec backend python seed.py
```

Optional profiles:

```bash
docker compose --profile sso up        # + Keycloak with pre-configured realm
docker compose --profile postgres up   # + PostgreSQL (set DATABASE_URL accordingly)
```

## Quick start (local development)

**Backend** (Python 3.12+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 20+):

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Tests

```bash
cd backend
.venv/bin/pytest -q        # 64 tests: auth, RBAC, uploads, deployments, retention, audit, nexus, settings
cd frontend
npm run build              # type-check + lint + production build
```

## Roles

| Role | Permissions |
|---|---|
| **Administrator** | Everything: servers, settings, users, tokens, retention, audit, notifications |
| **Developer** | Upload, deploy, rollback, download, import from Nexus, restore backups |
| **Viewer** | Browse repository, servers, deployments, dashboard; download bundles |

**Roles are managed in the app** (Settings → Users) — Keycloak handles sign-in only.
New SSO users start as Viewer; bootstrap your first admin via `ADMIN_USERNAMES` in `.env`.
If you prefer Keycloak-managed roles, set `KEYCLOAK_ROLE_SYNC_ENABLED=true` and use realm
roles `nar-admin` / `nar-developer` / `nar-viewer` (see `docs/keycloak-realm.json`).

## REST API

Full interactive documentation at `/docs` (Swagger UI) and `/redoc`.
High-level groups — see [API_CONTRACT.md](API_CONTRACT.md) for the full specification:

`/api/v1/auth` · `/api/v1/servers` · `/api/v1/bundles` · `/api/v1/deployments` ·
`/api/v1/backups` · `/api/v1/nexus` · `/api/v1/retention` · `/api/v1/audit-logs` ·
`/api/v1/dashboard` · `/api/v1/settings`

### CI/CD integration (API tokens)

Create a token in **Settings → API Tokens**, then:

```bash
curl -H "X-API-Key: nrm_..." http://localhost:8000/api/v1/bundles/

# GitLab CI example — deploy a NAR after build:
curl -X POST -H "X-API-Key: $NAR_TOKEN" -F "files=@build/my-nar-1.0.0.nar" \
  "https://nar-manager.example.com/api/v1/bundles/upload?replace=false"
```

## Configuration

Everything is environment-variable driven — see [.env.example](.env.example) for the
annotated reference. Runtime-tunable values (SSH timeout, upload size, retention, log level)
can also be changed from **Settings → General** without restart; changes are audited.

Secrets (server SSH passwords, Nexus passwords) are stored Fernet-encrypted, keyed from
`SECRET_KEY`. Never commit `.env`.

## Project layout

```
├── backend/
│   ├── app/
│   │   ├── api/endpoints/    # REST routers (auth, servers, bundles, deployments, …)
│   │   ├── core/             # config, database, security, RBAC deps
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic contracts
│   │   ├── services/         # nar, ssh, deployment, backup, nexus, retention, …
│   │   ├── scheduler.py      # APScheduler cron jobs
│   │   └── main.py           # app factory
│   ├── alembic/              # migrations
│   ├── tests/                # pytest suite (64 tests)
│   └── seed.py               # idempotent demo data
├── frontend/
│   └── src/
│       ├── app/              # Next.js pages (dashboard, servers, repository, …)
│       ├── components/       # ui/ (shadcn), layout, shared widgets
│       ├── hooks/            # auth context
│       └── lib/              # api client, types, utils
├── docs/                     # installation guide, keycloak realm
├── docker-compose.yml
└── API_CONTRACT.md
```

## License

Proprietary — internal platform engineering use.
