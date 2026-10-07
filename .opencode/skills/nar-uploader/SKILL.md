---
name: nar-uploader
description: Use when working on the NiFi NAR uploader project — a FastAPI + Next.js app for uploading, deploying, and managing NAR bundles to remote NiFi servers over SSH/SFTP.
---

# NiFi NAR Uploader

A web application for uploading NAR bundles, deploying them to remote NiFi servers via SSH/SFTP, and managing NAR repositories (local + remote).

## Architecture

| Layer | Tech | Location |
|-------|------|----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, SQLite, Paramiko | `backend/` |
| Frontend | Next.js 14, React, Tailwind, shadcn/ui | `frontend/` |
| Container | Docker Compose (backend + frontend, optional Keycloak + Postgres) | `docker-compose.yml` |

## Setup & Running

```bash
echo sudopass | sudo -S docker compose up -d --build
```

Two containers: `nar-manager-backend` (`:8000`) and `nar-manager-frontend` (`:3000`).

## SSH Deployment

The pipeline connects to remote NiFi servers via Paramiko (SSH) / SFTP:

1. **SSH key**: stored in `ssh-key/id_ansible` (mounted to `/home/narmgr/.ssh/`)
2. **User**: `ansible` on the target server (has passwordless sudo)
3. **Key path**: `~/.ssh/id_ansible` in the database
4. **Restart**: `docker compose -f /opt/nifi/docker-compose.yml restart` (passwordless via sudo)

The entrypoint script `backend/docker-entrypoint.sh` copies SSH keys and fixes ownership to `narmgr` at container start.

## Deployment Pipeline (`backend/app/services/deployment_service.py`)

| Step | Action |
|------|--------|
| 1 | Validate local NAR file (checksum, size) |
| 2 | Compatibility check (group/artifact match) |
| 3 | Backup existing remote file, then remove it |
| 4 | Upload new NAR via SFTP |
| 5 | Verify remote checksum |
| 6 | Restart NiFi via sudo |
| 7 | Record deployment history |

Database config for server 1 (the only server):
- `ssh_user`: `ansible`
- `ssh_key_path`: `~/.ssh/id_ansible`
- `nar_directory`: `/opt/nifi/nifi/PST.AG/nar`
- `restart_command`: `docker compose -f /opt/nifi/docker-compose.yml restart`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/servers/` | List servers |
| GET/POST/PUT/DELETE | `/api/v1/servers/{id}` | CRUD server |
| GET | `/api/v1/servers/{id}/nar-files` | List remote NAR files |
| DELETE | `/api/v1/servers/{id}/nar-files` | Delete remote NAR files |
| GET/POST/PUT/DELETE | `/api/v1/bundles/` | CRUD local bundles |
| POST | `/api/v1/bundles/upload` | Upload NAR files |
| DELETE | `/api/v1/bundles/{id}` | Delete local bundle + file |
| POST | `/api/v1/bundles/bulk-delete` | Bulk delete bundles |
| POST | `/api/v1/deployments/` | Create and run deployment |
| GET | `/api/v1/auth/users` | List users |
| POST | `/api/v1/auth/users` | Create local user |
| PUT | `/api/v1/auth/users/{id}` | Update user role/status |

## Key Files

- `backend/app/services/ssh_service.py` — SSHClient wrapper (Paramiko)
- `backend/app/services/deployment_service.py` — Deployment pipeline
- `backend/app/api/endpoints/servers.py` — Server + remote NAR endpoints
- `backend/app/api/endpoints/bundles.py` — Local bundle endpoints
- `backend/app/api/endpoints/auth.py` — Auth + user management
- `frontend/src/app/servers/page.tsx` — Server list + NAR Repository dialog
- `frontend/src/app/repository/page.tsx` — Local bundle repository
- `frontend/src/app/settings/page.tsx` — Settings + user management

## Common Tasks

**Add a new feature endpoint**: Add route in `backend/app/api/endpoints/`, schema in `backend/app/schemas/schemas.py`, type in `frontend/src/lib/types.ts`, API call in `frontend/src/lib/api.ts`, UI component in `frontend/src/app/`.

**Test SSH from container**: `docker exec -u narmgr nar-manager-backend ssh -i /home/narmgr/.ssh/id_ansible ansible@dv-nifi-com-01.pstag.de "command"`

**Rebuild after code changes**: Use `--build` flag: `docker compose up -d --build backend` (or `frontend`).

## Database

SQLite at `/app/data/nar_manager.db` (mounted from `./nar-data/`). Access via:
```bash
docker exec nar-manager-backend python -c "
import sqlite3
conn = sqlite3.connect('/app/data/nar_manager.db')
for row in conn.execute('SELECT * FROM nifi_servers'): print(row)
"
```
