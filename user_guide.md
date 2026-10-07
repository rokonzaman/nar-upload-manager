# NiFi NAR Upload Manager — User Guide

## Overview

The **NiFi NAR Upload Manager** is a web application for uploading, managing, and deploying
Apache NiFi NAR bundles to remote NiFi servers over SSH/SFTP. It supports single-server and
cluster (group) deployments, rollback, retention policies, Nexus integration, audit logging,
and role-based access control with optional Keycloak SSO.

**Base URL**: `http://<host>:3000`  
**API**: `http://<host>:8000/api/v1`  
**Technology**: FastAPI backend, Next.js 14 frontend, SQLite database, Docker Compose

---

## Access & Authentication

### Local Login (Dev Mode)

When running in dev mode (`DEV_MODE=true`), log in with the built-in admin account
(default: `admin` / `admin`, change immediately after first login).

### Keycloak SSO

If Keycloak is enabled, click **Login with SSO** on the login page. On first login your
account is auto-provisioned with the **viewer** role. An admin must promote your role via
**Settings → Users**.

Quick-reference for new SSO users:

| Condition | Assigned Role |
|---|---|
| Username is in `ADMIN_USERNAMES` list | `admin` |
| `KEYCLOAK_ROLE_SYNC_ENABLED=true` and you have `nar-admin` realm role | `admin` |
| `KEYCLOAK_ROLE_SYNC_ENABLED=true` and you have `nar-developer` realm role | `developer` |
| Everything else | `viewer` (default) |

### Roles

| Role | Permissions |
|---|---|
| **admin** | Full access: all CRUD, settings, user management, audit |
| **developer** | Upload, deploy, rollback, download, server restart |
| **viewer** | Browse servers, repository, deployments, backups, health |

---

## Navigation

The sidebar provides access to all sections:

| Section | Description |
|---|---|
| **Dashboard** | Overview stats, charts, recent activity |
| **Servers** | Manage NiFi servers, groups, health, NAR repos |
| **Repository** | Browse and manage local NAR bundles |
| **Upload** | Upload new NAR files to the repository |
| **Deployments** | View deployment history and status |
| **Backups** | Browse and restore NAR backups |
| **Nexus** | Nexus repository integration |
| **Retention** | Automatic cleanup policies |
| **Audit Logs** | Full audit trail (admin only) |
| **Settings** | Users, notifications, API tokens (admin only) |

---

## 1. Dashboard

The home page shows key metrics at a glance:

- Total servers, bundles, deployments, backups
- Storage consumption and pending cleanup items
- Upload and deployment trend charts (30 days)
- Recent uploads and deployments

## 2. Servers

### Registering a Server

1. Go to **Servers** and click **Add Server** (admin only)
2. Fill in the form:

| Field | Description |
|---|---|
| **Name** | Display name (e.g. `nifi-prod-01`) |
| **Hostname** | Human-readable identifier |
| **SSH Host** | IP or FQDN for SSH connection |
| **SSH Port** | SSH port (default: 22) |
| **SSH User** | Remote user (e.g. `ansible`) |
| **SSH Key Path** | Path to private key (e.g. `~/.ssh/id_ansible`) |
| **SSH Password** | Alternative to key auth |
| **NAR Directory** | Remote path where NARs are deployed (e.g. `/opt/nifi/lib`) |
| **Backup Directory** | Remote path for backups before overwrite |
| **NiFi Install Directory** | Root install path (e.g. `/opt/nifi`) |
| **Restart Command** | Command to restart NiFi (e.g. `sudo systemctl restart nifi`) |
| **NiFi API URL** | NiFi REST API base URL (e.g. `https://host:8443/nifi-api`) |
| **Environment** | DEV / QA / UAT / PROD |
| **Enabled** | Whether the server accepts deployments |

### Server Actions (dropdown menu per row)

| Action | Role | Description |
|---|---|---|
| **Health** | viewer+ | Live SSH metrics: disk, memory, CPU, NiFi status, version |
| **NAR Repository** | admin | Browse and delete remote NAR files on the server |
| **Test Connection** | admin | Verify SSH connectivity and latency |
| **Restart NiFi** | developer+ | Run `Restart Command` via SSH with optional bootstrap wait |
| **Edit** | admin | Modify server configuration |
| **Delete** | admin | Remove server registration |

### Server Groups (Clusters)

Use groups to deploy a NAR to all nodes in a NiFi cluster at once.

1. Switch to the **Groups** tab under Servers
2. Click **New Group** (admin only)
3. Name the group, select environment, and check member servers
4. Save

**Group Actions:**

| Action | Role | Description |
|---|---|---|
| **Deploy NAR** | developer+ | Search and deploy a bundle to all group nodes |
| **Restart** | developer+ | Restart all nodes **sequentially** — each node is restarted, then NiFi bootstrap is confirmed via API poll (60s timeout) before proceeding to the next node |

### Health Dialog

Shows live server metrics collected over SSH:

- Disk usage (total, used, free, percentage) with warnings at 80% and 90%
- Memory usage
- CPU usage
- NiFi process status (running / stopped)
- NiFi version (fetched from NiFi API URL if configured, otherwise from `VERSION` file)
- NAR directory size
- System uptime

### NAR Repository (Remote)

Browse `.nar` files on the remote server. Admin users can select and delete files.

## 3. Repository (Local Bundle Management)

The repository stores all uploaded NAR bundles locally. They are organized by
`bundle_group` → `artifact` → versions.

### Key Features

- **Search** by artifact name, version, or group
- **Expand/collapse** version trees to see all versions of an artifact
- **Compare** two bundles side-by-side (checksum, size diff, manifest diff)
- **Pin** a bundle to protect it from retention cleanup
- **Download** a bundle to your local machine
- **Delete** individual or bulk bundles
- **Replace** an existing version with a new file

### Bundle Details

Each bundle stores:
- Group, artifact, version (parsed from filename: `{group}-{artifact}-{version}.nar`)
- SHA256 and MD5 checksums
- File size, upload timestamp, uploader
- Tags and description
- Manifest metadata (extracted from `META-INF/MANIFEST.MF` inside the NAR)

## 4. Upload

Upload new NAR files to the local repository.

1. Go to **Upload**
2. Drag and drop one or more `.nar` files, or click to browse
3. Optionally enable **Replace** to overwrite existing versions
4. Click **Upload**

### Rules

- File extension: `.nar` only
- Maximum size: configured via `MAX_UPLOAD_SIZE` setting
- Checksums (SHA256 + MD5) are computed during upload
- Duplicate (same group + artifact + version) is rejected unless `replace=true`
- Metadata is extracted from the NAR zip's `META-INF/MANIFEST.MF`

### Upload Results

Each file shows:
- Success / failure status
- Bundle metadata on success
- Error message on failure
- Whether an existing bundle was replaced

## 5. Deployments

### Creating a Deployment

1. Go to **Deployments** and click **New Deployment**
2. Select a bundle from the repository
3. Select one or more target servers
4. Configure options:

| Option | Description |
|---|---|
| **Backup** | Create a backup of the existing remote NAR before deploying (default: on) |
| **Restart NiFi** | Run `restart_command` after upload (default: off) |
| **Dry Run** | Validate checks only — no file transfer or restart |
| **Target Directory** | Override the server's default NAR directory |
| **Notes** | Deployment notes for audit trail |

### Deployment Pipeline (7 steps)

1. **Validate** — local file exists, checksums valid
2. **Compatibility** — pre-deployment checks (duplicate version warnings, target NiFi version)
3. **Backup** — copy existing remote file to backup directory
4. **Upload** — SFTP transfer to target server
5. **Verify** — remote SHA256 comparison
6. **Restart** — optional NiFi restart via configured command
7. **Verify deployment** — confirm file exists on target

### Group Deployments

In **Servers → Groups**, deploy a bundle to all member nodes simultaneously.
One deployment record is created per node; each runs independently with full logging.

### Rollback

From the deployment details page, click **Rollback** to restore the backup created
during deployment. Only successful deployments with a backup can be rolled back.

### Statuses

- `pending` — Created, waiting to start
- `in_progress` — Currently running
- `success` — Completed successfully
- `failed` — Failed (check error message and log)
- `rolled_back` — Backup was restored
- `cancelled` — Cancelled before completion

## 6. Backups

Every deployment with backup enabled creates a point-in-time snapshot of the replaced
remote NAR file.

### Backup Management

- Browse backups by server, artifact, or search term
- **Restore** a backup to its originating server (one-click)
- **Delete** individual backups (admin only)
- **Cleanup Orphans** — delete backup records for files no longer accessible (admin only)

## 7. Nexus Integration

Connect to Nexus repository servers to search and download artifacts directly.

### Setup

1. Go to **Nexus** and add a server
2. Provide URL and credentials
3. Test the connection

### Features

- **Search** Nexus repositories by name, group, artifact, version
- **Download** artifacts directly into the local repository (auto-caches)
- **Sync** — batch sync configured Nexus repository contents

## 8. Retention

Automate cleanup of old NAR bundles to manage disk space.

### Policy

Configure under **Retention**:

| Setting | Description |
|---|---|
| **Keep Latest** | Number of latest versions per artifact to keep |
| **Keep Days** | Keep versions newer than this many days |
| **Dry Run** | Preview-only mode (no actual deletion) |
| **Schedule** | Cron expression for automatic runs |

### Safety Rules

- **Pinned bundles** are never deleted
- **Bundles with active/successful deployments** are never deleted

### Preview & Execute

- **Preview** shows which bundles would be deleted and total freed space
- **Execute** runs the cleanup (requires explicit confirmation when not dry-run)
- View run history with deleted counts and freed bytes

## 9. Audit Logs (Admin Only)

Every mutating action is recorded:

- User, timestamp, IP address, user-agent
- Action type (upload, deploy, delete, rollback, etc.)
- Target resource (server, bundle, backup, etc.)
- Result (success / failure) with error message if failed
- Bundle name and version for deployment-related actions

### Features

- **Filter** by username, action, result, server, resource type, date range, keyword search
- **Export** to CSV for external analysis
- View distinct action types for filtering

## 10. Settings (Admin Only)

### General

View and edit application settings (SMTP host, retention defaults, SSH timeout, etc.).
All changes are audited.

### Users

- **List** all users (local + SSO-provisioned)
- **Create** local users with password (dev mode)
- **Edit** user role and active status
- Roles: `admin`, `developer`, `viewer`

### Notifications

Configure notification channels for deployment events:

| Type | Description |
|---|---|
| **Email** | SMTP email notifications |
| **Slack** | Slack incoming webhook (also works with **Mattermost**) |
| **Teams** | Microsoft Teams webhook |
| **Webhook** | Generic HTTP POST (JSON payload) |

Available events:
`upload_completed`, `deployment_completed`, `deployment_failed`,
`rollback_completed`, `cleanup_completed`, `nexus_sync_completed`

### API Tokens

Create API tokens for automation. Tokens are shown once at creation — copy them immediately.
Specify role and optional expiry. Tokens are passed as `Authorization: Bearer <token>`.

---

## SSH Setup

The application connects to NiFi servers over SSH/SFTP using Paramiko.

### Requirements

- **Passwordless sudo** for the SSH user on the target server
- **SSH private key** placed in `ssh-key/` directory (mounted to `/home/narmgr/.ssh/` in the container)
- **Key path** configured in the server settings (e.g. `~/.ssh/id_ansible`)

### Testing SSH

```bash
docker exec -u narmgr nar-manager-backend \
  ssh -i /home/narmgr/.ssh/id_ansible ansible@server-host "whoami"
```

---

## Quick Reference — Common Tasks

| Task | Navigation |
|---|---|
| Upload a NAR | Upload → drag file → Upload |
| Deploy to one server | Repository → select bundle → Deploy |
| Deploy to cluster | Servers → Groups → Deploy NAR |
| View deployment log | Deployments → click deployment row |
| Rollback | Deployments → click deployment → Rollback |
| Check server health | Servers → ... menu → Health |
| Restart NiFi (single) | Servers → ... menu → Restart NiFi |
| Restart NiFi (cluster) | Servers → Groups → Restart (node by node) |
| Delete remote NARs | Servers → ... menu → NAR Repository → select → Delete |
| Add user / change role | Settings → Users |
| Set up notification | Settings → Notifications → Add |
| Create API token | Settings → API Tokens → Generate |