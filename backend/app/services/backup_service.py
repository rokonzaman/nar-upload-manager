"""Local backup management for replaced NAR files."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import Backup, Deployment, NiFiServer
from app.services.ssh_service import SSHClient

settings = get_settings()
logger = logging.getLogger(__name__)


def backup_remote_file(
    db: Session,
    ssh: SSHClient,
    server: NiFiServer,
    remote_path: str,
    created_by: str,
    deployment: Optional[Deployment] = None,
    artifact: Optional[str] = None,
    version: Optional[str] = None,
    skip_download: bool = False,
    sha256: Optional[str] = None,
    file_size: int = 0,
) -> Backup:
    """Pull a remote file into the local backup directory and register it.

    When ``skip_download`` is True the existing remote file is byte-identical
    to the bundle being deployed, so it is not copied down — yet a Backup
    record is still written and returned so the audit trail records the
    deploy-time state of the file.
    """
    now = datetime.utcnow()
    filename = remote_path.rsplit("/", 1)[-1]
    dest_dir = (
        settings.backup_dir
        / server.name
        / now.strftime("%Y")
        / now.strftime("%m")
        / now.strftime("%d")
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_identical" if skip_download else ""
    dest = dest_dir / f"{int(now.timestamp())}{suffix}_{filename}"

    if not skip_download:
        ssh.download_file(remote_path, str(dest))

        from app.services.nar_service import compute_checksums

        sha256, _, file_size = compute_checksums(dest)

    record = Backup(
        server_id=server.id,
        deployment_id=deployment.id if deployment else None,
        filename=filename,
        original_path=remote_path,
        backup_path=str(dest),
        file_size=file_size,
        sha256=sha256,
        bundle_artifact=artifact,
        bundle_version=version,
        created_by=created_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Backed up %s from %s to %s", remote_path, server.name, dest)
    return record


def restore_backup(db: Session, backup: Backup) -> None:
    """Upload a backup file back to its original location on the server."""
    if backup.server is None:
        raise ValueError("Backup has no associated server")
    if not Path(backup.backup_path).exists():
        raise FileNotFoundError(f"Backup file missing on disk: {backup.backup_path}")
    with SSHClient(backup.server) as ssh:
        ssh.upload_file(backup.backup_path, backup.original_path)
        remote_sha = ssh.remote_sha256(backup.original_path)
    if backup.sha256 and remote_sha != backup.sha256:
        raise ValueError(
            f"Checksum mismatch after restore: expected {backup.sha256}, got {remote_sha}"
        )
    backup.restored_at = datetime.utcnow()
    db.commit()


def cleanup_orphaned_backups(db: Session) -> tuple[int, int]:
    """Delete backup records/files whose server no longer exists or file is missing.

    Returns (deleted_count, freed_bytes).
    """
    deleted, freed = 0, 0
    for backup in db.query(Backup).all():
        path = Path(backup.backup_path)
        if backup.server_id is not None and backup.server is not None and path.exists():
            continue
        if path.exists():
            freed += path.stat().st_size
            path.unlink()
        db.delete(backup)
        deleted += 1
    db.commit()
    return deleted, freed
