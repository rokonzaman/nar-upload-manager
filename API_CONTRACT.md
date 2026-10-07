# NiFi NAR Upload Manager — API Contract

Base URL: `/api/v1`. All endpoints (except `/health`, `/api/v1/auth/login`, `/api/v1/auth/keycloak/*`) require
`Authorization: Bearer <token>` or `X-API-Key: <token>`.

Roles: `admin` (full), `developer` (upload/deploy/download), `viewer` (browse/download).
RBAC notation below: **[A]** admin, **[D]** developer+, **[V]** viewer+.

Standard error body: `{"detail": "..."}`. Paginated lists return
`{"items": [...], "total": n, "page": 1, "page_size": 20, "pages": n}` with query params
`page`, `page_size` (max 200) plus filters.

## Auth — `/api/v1/auth`
| Method | Path | Role | Body → Response |
|---|---|---|---|
| POST | `/login` | public | `{username, password}` → `TokenResponse` (dev mode) |
| GET | `/keycloak/login?redirect_uri=` | public | → `{authorization_url}` |
| POST | `/keycloak/callback` | public | `{code, redirect_uri}` → `TokenResponse` |
| GET | `/config` | public | → `{dev_mode: bool, keycloak_enabled: bool, app_name, version}` |
| GET | `/me` | any | → `UserOut` |
| POST | `/logout` | any | → `Message` (audit only) |
| GET | `/users` | [A] | → `UserOut[]` |
| PUT | `/users/{id}` | [A] | `{role?, is_active?}` → `UserOut` |

## Servers — `/api/v1/servers`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [V] | paginated; filters `environment`, `enabled`, `q` |
| POST | `/` | [A] | `NiFiServerCreate` → `NiFiServerOut` |
| GET | `/{id}` | [V] | → `NiFiServerOut` |
| PUT | `/{id}` | [A] | partial update |
| DELETE | `/{id}` | [A] | |
| POST | `/{id}/test-connection` | [A] | → `ServerTestResult` |
| GET | `/{id}/health` | [V] | → `ServerHealth` (disk/cpu/mem/nifi status, warnings) |
| GET | `/environments` | [V] | → `["DEV","QA","UAT","PROD"]` |

## Server Groups (NiFi clusters) — `/api/v1/server-groups`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [V] | → `ServerGroupOut[]` (includes member `servers` + `server_count`) |
| POST | `/` | [A] | `{name, description?, environment, server_ids: []}` → `ServerGroupOut` |
| GET | `/{id}` | [V] | → `ServerGroupOut` |
| PUT | `/{id}` | [A] | partial update incl. `server_ids` membership |
| DELETE | `/{id}` | [A] | removes the group only; servers are kept |
| POST | `/{id}/deploy` | [D] | `GroupDeployRequest {bundle_id, backup, restart_nifi, dry_run, notes?, target_directory?}` → `DeploymentOut[]` — one deployment per member node, executed independently |

## Bundles (NAR Repository) — `/api/v1/bundles`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [V] | paginated; filters `q` (artifact/group/version), `group`, `artifact`, `status`, `tag`, `source`, `pinned`; sort via `sort_by` (uploaded_at\|file_size\|version\|artifact), `sort_order` (asc\|desc) |
| GET | `/grouped` | [V] | → `BundleGroup[]` (artifact → versions tree, newest first) |
| POST | `/upload?replace=true|false` | [D] | multipart `files` (multiple `.nar`) → `UploadResult[]` |
| GET | `/{id}` | [V] | → `NarBundleOut` |
| PUT | `/{id}` | [D] | `BundleUpdate` (rename artifact, tags, status, pin) |
| DELETE | `/{id}` | [D] | 409 if pinned or has active deployment |
| POST | `/bulk-delete` | [D] | `{ids: []}` → `BulkActionResult` |
| GET | `/{id}/download` | [V] | file stream (audited) |
| POST | `/{id}/replace` | [D] | multipart `file` → `NarBundleOut` |
| POST | `/compare` | [V] | `{id_a, id_b}` → `BundleCompareResult` |
| GET | `/stats/storage` | [V] | → `{total_bytes, count, by_group: [{label, value}]}` |

Upload rules: `.nar` only (configurable), size ≤ `MAX_UPLOAD_SIZE`, SHA256+MD5 computed while streaming;
duplicate (group, artifact, version) → 409 unless `replace=true`; metadata extracted from
`META-INF/MANIFEST.MF` inside the NAR (zip) when present. Stored at
`{NAR_DIRECTORY}/{group}/{artifact}/{version}/{filename}`.

## Deployments — `/api/v1/deployments`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [V] | paginated; filters `status`, `server_id`, `bundle_id`, `user`, `from`, `to` |
| POST | `/` | [D] | `DeploymentCreate` (multi-server) → `DeploymentOut[]`; executes via background task |
| GET | `/{id}` | [V] | → `DeploymentOut` (includes `log` step output) |
| POST | `/{id}/rollback` | [D] | restores backup created during deployment → `DeploymentOut` |
| POST | `/compatibility` | [V] | `{bundle_id, server_ids: []}` → `CompatibilityReport[]` |

Deployment steps (recorded in `log`): validate NAR → compatibility checks → backup existing →
SFTP upload → verify remote SHA256 → optional restart → verify → history. Dry-run performs
read-only checks only. Statuses: `pending, in_progress, success, failed, rolled_back, cancelled`.

## Backups — `/api/v1/backups`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [V] | paginated; filters `server_id`, `artifact`, `q` |
| POST | `/{id}/restore` | [D] | one-click restore to originating server → `Message` |
| DELETE | `/{id}` | [A] | |
| POST | `/cleanup-orphans` | [A] | → `{deleted: n, freed_bytes: n}` |

## Nexus — `/api/v1/nexus`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET/POST | `/servers` | [V]/[A] | list / create |
| PUT/DELETE | `/servers/{id}` | [A] | |
| POST | `/servers/{id}/test` | [A] | → `ServerTestResult` |
| GET | `/servers/{id}/repositories` | [V] | → `[{name, format, type}]` |
| GET | `/servers/{id}/search?q=&repository=&group=&artifact=&version=` | [V] | → `NexusArtifact[]` |
| POST | `/download` | [D] | `NexusDownloadRequest` → `NarBundleOut` (cached into repository) |
| POST | `/servers/{id}/sync` | [A] | → `NexusSyncResult` |

## Retention — `/api/v1/retention`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/policy` | [V] | → `RetentionPolicyOut` |
| PUT | `/policy` | [A] | `RetentionPolicyIn` → `RetentionPolicyOut` |
| POST | `/preview` | [A] | optional `RetentionPolicyIn` overrides → `RetentionPreview` |
| POST | `/execute` | [A] | `{dry_run: bool, confirm: bool}` — confirm required when `dry_run=false` → `RetentionRunOut` |
| GET | `/runs` | [V] | paginated run history |

Never deletes pinned bundles or bundles with a successful active deployment. Keeps latest N
versions per artifact AND versions newer than X days.

## Audit — `/api/v1/audit-logs`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [A] | paginated; filters `username`, `action`, `result`, `target_server`, `bundle`, `resource_type`, `from`, `to`, `q` |
| GET | `/export?format=csv` | [A] | CSV download (same filters) |
| GET | `/actions` | [A] | → `string[]` distinct actions |

## Dashboard — `/api/v1/dashboard`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/stats` | [V] | → `DashboardStats` |
| GET | `/charts?days=30` | [V] | → `DashboardCharts` (uploads, deployments, storage_growth, top_bundles) |
| GET | `/activity?limit=20` | [V] | → `AuditLogOut[]` recent activity |
| GET | `/recent-uploads?limit=5` | [V] | → `NarBundleOut[]` |
| GET | `/recent-deployments?limit=5` | [V] | → `DeploymentOut[]` |

## Settings — `/api/v1/settings`
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/` | [A] | → `{settings: SettingItem[], config: {app, limits, retention, ...}}` |
| PUT | `/` | [A] | `{values: {key: value}}` → audited |
| GET/POST | `/notifications` | [A] | list / create `NotificationConfigCreate` |
| PUT/DELETE | `/notifications/{id}` | [A] | |
| POST | `/notifications/{id}/test` | [A] | → `Message` |
| GET/POST | `/api-tokens` | [A] | list / create → `ApiTokenCreated` (plain token once) |
| DELETE | `/api-tokens/{id}` | [A] | |

## Health
`GET /health` → `{status: "ok", version, timestamp}` (public).

## Notification events
`upload_completed, deployment_completed, deployment_failed, rollback_completed,
cleanup_completed, nexus_sync_completed`.

## Notes for implementers
- All timestamps UTC ISO-8601. `datetime` fields in DB are naive UTC.
- Secrets (SSH passwords, Nexus passwords) are Fernet-encrypted at rest and never serialized.
- Audit every mutating action with username, IP, user-agent, result.
- SSH operations use Paramiko with `SSH_TIMEOUT`; deployments run in FastAPI BackgroundTasks.
- Path traversal protection: uploaded filenames are sanitized (`werkzeug`-style secure filename).
