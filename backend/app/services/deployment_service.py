"""Deployment pipeline: validate → backup → upload → verify → restart → history."""

import logging
import posixpath
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session
from app.models.models import (
    AuditAction,
    AuditResult,
    Deployment,
    DeploymentStatus,
    NarBundle,
    NiFiServer,
)
from app.schemas.schemas import CompatibilityReport, CompatibilityWarning
from app.services import backup_service, notification_service
from app.services.ssh_service import SSHClient, SSHError

logger = logging.getLogger(__name__)


def _log(deployment: Deployment, message: str) -> None:
    """Append a timestamped line to the deployment log."""
    line = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    deployment.log = f"{deployment.log}\n{line}" if deployment.log else line
    logger.info("deployment=%s %s", deployment.id, message)


def create_deployment_records(
    db: Session,
    bundle: NarBundle,
    servers: List[NiFiServer],
    *,
    dry_run: bool = False,
    backup: bool = True,
    restart_nifi: bool = False,
    notes: Optional[str] = None,
    target_directory: Optional[str] = None,
    deployed_by: str,
) -> List[Deployment]:
    """Create one PENDING deployment record per server (used by single and group deploys)."""
    records: List[Deployment] = []
    for server in servers:
        deployment = Deployment(
            bundle_id=bundle.id,
            server_id=server.id,
            status=DeploymentStatus.PENDING.value,
            dry_run=dry_run,
            backup_created=backup,
            restart_nifi=restart_nifi,
            target_directory=target_directory,
            deployed_by=deployed_by,
            notes=notes,
        )
        db.add(deployment)
        records.append(deployment)
    db.commit()
    for deployment in records:
        db.refresh(deployment)
    return records


def _fail(db: Session, deployment: Deployment, message: str) -> None:
    _log(deployment, f"ERROR: {message}")
    deployment.status = DeploymentStatus.FAILED.value
    deployment.error_message = message
    deployment.completed_at = datetime.utcnow()
    db.commit()
    notification_service.notify(
        db,
        notification_service.EVENT_DEPLOYMENT_FAILED,
        "Deployment failed",
        f"Deployment #{deployment.id} failed: {message}",
    )


def check_compatibility(db: Session, bundle: NarBundle, server: NiFiServer) -> CompatibilityReport:
    """Run pre-deployment compatibility checks."""
    warnings: List[CompatibilityWarning] = []
    compatible = True

    from pathlib import Path

    if not Path(bundle.file_path).exists():
        warnings.append(CompatibilityWarning(level="error", message="Bundle file missing on disk"))
        compatible = False

    if not server.is_enabled:
        warnings.append(CompatibilityWarning(level="error", message=f"Server '{server.name}' is disabled"))
        compatible = False

    # Duplicate deployments of the exact same checksum
    prior = (
        db.query(Deployment)
        .filter(
            Deployment.server_id == server.id,
            Deployment.status == DeploymentStatus.SUCCESS.value,
        )
        .all()
    )
    deployed_bundle_ids = {d.bundle_id for d in prior}
    for other_id in deployed_bundle_ids:
        if other_id == bundle.id:
            warnings.append(
                CompatibilityWarning(level="info", message="This exact version was previously deployed to this server")
            )

    # Other versions of the same artifact already deployed → conflict warning
    others = (
        db.query(NarBundle)
        .filter(
            NarBundle.artifact == bundle.artifact,
            NarBundle.bundle_group == bundle.bundle_group,
            NarBundle.id.in_(deployed_bundle_ids),
            NarBundle.id != bundle.id,
        )
        .all()
    )
    for other in others:
        warnings.append(
            CompatibilityWarning(
                level="warning",
                message=f"Version {other.version} of {other.artifact} is currently deployed and will be replaced",
            )
        )

    # Try to fetch the NiFi version for a compatibility hint
    try:
        with SSHClient(server, timeout=5) as ssh:
            rc, out, _ = ssh.exec_command(
                f"cat {server.nifi_install_directory!r}/VERSION 2>/dev/null || true"
            )
            if rc == 0 and out:
                warnings.append(CompatibilityWarning(level="info", message=f"Target NiFi version: {out}"))
    except SSHError as exc:
        warnings.append(CompatibilityWarning(level="warning", message=f"Cannot reach server for version check: {exc}"))

    return CompatibilityReport(bundle_id=bundle.id, server_id=server.id, compatible=compatible, warnings=warnings)


def run_deployment(db: Session, deployment_id: int) -> None:
    """Execute the full deployment pipeline for one deployment record."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if deployment is None:
        logger.error("Deployment %s not found", deployment_id)
        return

    bundle: NarBundle = deployment.bundle
    server: NiFiServer = deployment.server
    deployment.status = DeploymentStatus.IN_PROGRESS.value
    deployment.started_at = datetime.utcnow()
    db.commit()

    target_dir = deployment.target_directory or server.nar_directory
    remote_path = posixpath.join(target_dir, bundle.filename)
    deployment.deployed_path = remote_path

    _log(deployment, f"Starting deployment of {bundle.artifact}:{bundle.version} to {server.name} ({server.ssh_host})")
    _log(deployment, f"Target: {remote_path} (dry_run={deployment.dry_run}, backup={deployment.backup_created}, restart={deployment.restart_nifi})")
    db.commit()

    # Step 1: validate NAR locally
    from pathlib import Path

    local_path = Path(bundle.file_path)
    if not local_path.exists():
        _fail(db, deployment, f"Bundle file missing on disk: {bundle.file_path}")
        return
    _log(deployment, f"Step 1/7: Local validation OK (sha256={bundle.sha256[:16]}..., {bundle.file_size} bytes)")
    db.commit()

    # Step 2: compatibility
    report = check_compatibility(db, bundle, server)
    for w in report.warnings:
        _log(deployment, f"Step 2/7: [{w.level.upper()}] {w.message}")
    if not report.compatible:
        errors = "; ".join(w.message for w in report.warnings if w.level == "error")
        _fail(db, deployment, f"Compatibility checks failed: {errors or 'unknown error'}")
        return
    _log(deployment, "Step 2/7: Compatibility checks passed")
    db.commit()

    if deployment.dry_run:
        _log(deployment, "Dry run: no changes made. All checks completed.")
        deployment.status = DeploymentStatus.SUCCESS.value
        deployment.completed_at = datetime.utcnow()
        db.commit()
        notification_service.notify(
            db,
            notification_service.EVENT_DEPLOYMENT_COMPLETED,
            "Dry-run deployment completed",
            f"Dry-run deployment #{deployment.id} of {bundle.artifact}:{bundle.version} to {server.name} completed",
        )
        return

    try:
        with SSHClient(server) as ssh:
            # Same-version redeploy short-circuit: if the existing remote file
            # is byte-identical to the bundle, there is nothing to protect or
            # transfer — skip the backup download AND the upload, still write a
            # backup record for the audit trail, then flow to restart/verify.
            # Matching is done via a single fast `sha256sum` on the server
            # (no bytes cross the wire), so this roughly makes a redeploy
            # instant instead of re-shovelling ~2x the file over a slow link.
            identical = False
            if ssh.file_exists(remote_path):
                identical = ssh.remote_matches_sha256(remote_path, bundle.sha256)
                if identical:
                    _log(deployment, "Step 3/7: Existing file is byte-identical — skipping backup download and upload")
                    backup_record = backup_service.backup_remote_file(
                        db,
                        ssh,
                        server,
                        remote_path,
                        created_by=deployment.deployed_by,
                        deployment=deployment,
                        artifact=bundle.artifact,
                        version=bundle.version,
                        skip_download=True,
                        sha256=bundle.sha256,
                        file_size=bundle.file_size,
                    )
                    deployment.backup_path = backup_record.backup_path
                    deployment.checksum_verified = True
                    _log(
                        deployment,
                        f"Step 3/7: Backup recorded w/o transfer at {backup_record.backup_path} (identical file)",
                    )
                else:
                    _log(deployment, f"Step 3/7: Existing file found at {remote_path}, creating backup")
                    backup = backup_service.backup_remote_file(
                        db,
                        ssh,
                        server,
                        remote_path,
                        created_by=deployment.deployed_by,
                        deployment=deployment,
                        artifact=bundle.artifact,
                        version=bundle.version,
                    )
                    deployment.backup_path = backup.backup_path
                    _log(deployment, f"Step 3/7: Backup stored at {backup.backup_path}")
                    ssh.remove_file(remote_path)
                    _log(deployment, "Step 3/7: Removed old remote file")
            else:
                _log(deployment, "Step 3/7: No existing file on target, backup not needed")
            db.commit()

            if not identical:
                # Step 4: upload via SFTP
                ssh.upload_file(str(local_path), remote_path)
                _log(deployment, f"Step 4/7: Uploaded {bundle.filename} via SFTP")
                db.commit()

                # Step 5: verify remote checksum
                remote_sha = ssh.remote_sha256(remote_path)
                if remote_sha != bundle.sha256:
                    raise SSHError(
                        f"Remote checksum mismatch (expected {bundle.sha256}, got {remote_sha})"
                    )
                deployment.checksum_verified = True
                _log(deployment, "Step 5/7: Remote checksum verified")
            else:
                _log(
                    deployment,
                    "Step 4/7: Upload skipped (identical file already present on target)",
                )
                _log(deployment, "Step 5/7: Checksum verified against identical remote file")
            db.commit()

            # Step 6: optional restart
            if deployment.restart_nifi:
                rc, out, err = ssh.exec_command(server.restart_command, timeout=120)
                if rc != 0:
                    raise SSHError(f"Restart command failed (rc={rc}): {err or out}")
                _log(deployment, f"Step 6/7: NiFi restart issued: {server.restart_command}")
            else:
                _log(deployment, "Step 6/7: Restart skipped (not requested)")
            db.commit()

            # Step 7: verify deployment
            if not ssh.file_exists(remote_path):
                raise SSHError("Post-deployment verification failed: file not present")
            _log(deployment, "Step 7/7: Deployment verified on target")
    except SSHError as exc:
        _fail(db, deployment, str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — never leave a deploy hanging IN_PROGRESS
        logger.exception("Deployment %s failed with an unexpected error", deployment.id)
        _fail(db, deployment, f"Unexpected error: {exc}")
        return

    deployment.status = DeploymentStatus.SUCCESS.value
    deployment.completed_at = datetime.utcnow()
    db.commit()
    _log(deployment, "Deployment completed successfully")
    db.commit()

    notification_service.notify(
        db,
        notification_service.EVENT_DEPLOYMENT_COMPLETED,
        "Deployment completed",
        f"{bundle.artifact}:{bundle.version} deployed to {server.name} by {deployment.deployed_by}",
    )


def rollback_deployment(db: Session, deployment_id: int, username: str) -> Deployment:
    """Restore the backup created by a deployment (one-click rollback)."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if deployment is None:
        raise ValueError("Deployment not found")
    if deployment.status != DeploymentStatus.SUCCESS.value:
        raise ValueError(f"Only successful deployments can be rolled back (status={deployment.status})")
    if not deployment.backup_path:
        raise ValueError("No backup was created during this deployment — nothing to restore")

    from app.models.models import Backup

    backup = (
        db.query(Backup)
        .filter(Backup.deployment_id == deployment.id)
        .order_by(Backup.created_at.desc())
        .first()
    )
    if backup is None:
        raise ValueError("Backup record not found")

    backup_service.restore_backup(db, backup)

    deployment.status = DeploymentStatus.ROLLED_BACK.value
    deployment.completed_at = datetime.utcnow()
    _log(deployment, f"Rolled back by {username}: restored {backup.backup_path} -> {backup.original_path}")
    db.commit()

    notification_service.notify(
        db,
        notification_service.EVENT_ROLLBACK_COMPLETED,
        "Rollback completed",
        f"Deployment #{deployment.id} rolled back on {deployment.server.name} by {username}",
    )
    return deployment
