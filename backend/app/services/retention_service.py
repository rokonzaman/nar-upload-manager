"""Retention policy: preview and execution with protection rules."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.models import (
    BundleStatus,
    Deployment,
    DeploymentStatus,
    NarBundle,
    RetentionPolicy,
    RetentionRun,
)
from app.schemas.schemas import RetentionCandidate, RetentionPolicyIn
from app.services import notification_service

logger = logging.getLogger(__name__)


def get_policy(db: Session) -> RetentionPolicy:
    """Return the singleton retention policy, creating defaults if missing."""
    policy = db.query(RetentionPolicy).first()
    if policy is None:
        from app.core.config import get_settings

        settings = get_settings()
        policy = RetentionPolicy(
            name="default",
            keep_latest=settings.RETENTION_KEEP_LATEST,
            keep_days=settings.RETENTION_KEEP_DAYS,
            is_enabled=settings.RETENTION_ENABLED,
            dry_run=settings.RETENTION_DRY_RUN,
            schedule=settings.RETENTION_SCHEDULE,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


def _deployed_bundle_ids(db: Session) -> set:
    """Bundle ids with at least one successful (not rolled back) deployment."""
    rows = (
        db.query(Deployment.bundle_id)
        .filter(Deployment.status == DeploymentStatus.SUCCESS.value)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _is_protected(bundle: NarBundle, deployed_ids: set) -> Tuple[bool, str]:
    if bundle.is_pinned:
        return True, "Pinned version"
    if bundle.id in deployed_ids:
        return True, "Active deployment"
    if bundle.status == BundleStatus.ARCHIVED.value:
        return True, "Archived"
    return False, ""


def build_candidates(
    db: Session, keep_latest: int, keep_days: int
) -> Tuple[List[RetentionCandidate], List[RetentionCandidate]]:
    """Return (deletable_candidates, protected_candidates)."""
    cutoff = datetime.utcnow() - timedelta(days=keep_days) if keep_days > 0 else None
    deployed_ids = _deployed_bundle_ids(db)

    groups: Dict[Tuple[str, str], List[NarBundle]] = {}
    for bundle in db.query(NarBundle).all():
        groups.setdefault((bundle.bundle_group, bundle.artifact), []).append(bundle)

    deletable: List[RetentionCandidate] = []
    protected: List[RetentionCandidate] = []

    for (group, artifact), bundles in groups.items():
        bundles.sort(key=lambda b: b.uploaded_at, reverse=True)
        for index, bundle in enumerate(bundles):
            is_protected, reason = _is_protected(bundle, deployed_ids)
            within_latest = index < keep_latest
            within_age = cutoff is not None and bundle.uploaded_at >= cutoff

            if is_protected:
                protected.append(
                    RetentionCandidate(
                        bundle_id=bundle.id,
                        bundle_group=group,
                        artifact=artifact,
                        version=bundle.version,
                        file_size=bundle.file_size,
                        uploaded_at=bundle.uploaded_at,
                        reason=reason,
                        protected=True,
                    )
                )
                continue
            if within_latest or within_age:
                continue  # kept by policy
            deletable.append(
                RetentionCandidate(
                    bundle_id=bundle.id,
                    bundle_group=group,
                    artifact=artifact,
                    version=bundle.version,
                    file_size=bundle.file_size,
                    uploaded_at=bundle.uploaded_at,
                    reason=f"Older than latest {keep_latest} versions and older than {keep_days} days",
                )
            )
    return deletable, protected


def execute(
    db: Session,
    policy: Optional[RetentionPolicyIn] = None,
    dry_run: bool = True,
    triggered_by: str = "manual",
) -> RetentionRun:
    """Execute retention. Deletes files + rows unless dry_run. Always records a run."""
    effective = policy or RetentionPolicyIn(
        keep_latest=get_policy(db).keep_latest,
        keep_days=get_policy(db).keep_days,
        is_enabled=True,
        dry_run=dry_run,
        schedule=get_policy(db).schedule,
    )
    candidates, _ = build_candidates(db, effective.keep_latest, effective.keep_days)

    run = RetentionRun(dry_run=dry_run, triggered_by=triggered_by)
    deleted_count, freed = 0, 0
    report_entries = []

    for candidate in candidates:
        bundle = db.query(NarBundle).filter(NarBundle.id == candidate.bundle_id).first()
        if bundle is None:
            continue
        report_entries.append(
            {
                "bundle": f"{candidate.bundle_group}:{candidate.artifact}:{candidate.version}",
                "size": candidate.file_size,
                "reason": candidate.reason,
                "action": "would_delete" if dry_run else "deleted",
            }
        )
        if not dry_run:
            path = Path(bundle.file_path)
            if path.exists():
                try:
                    path.unlink()
                    freed += candidate.file_size
                except OSError as exc:
                    logger.warning("Failed to delete %s: %s", path, exc)
                    continue
            # Remove now-empty parent dirs up to nar_dir
            from app.core.config import get_settings

            parent = path.parent
            root = get_settings().nar_dir
            while parent != root and root in parent.parents:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            db.delete(bundle)
            deleted_count += 1

    run.deleted_count = len(candidates) if dry_run else deleted_count
    run.freed_bytes = sum(c.file_size for c in candidates) if dry_run else freed
    run.completed_at = datetime.utcnow()
    run.report = json.dumps(report_entries, indent=2)
    db.add(run)

    db_policy = get_policy(db)
    db_policy.last_run_at = datetime.utcnow()
    db.commit()
    db.refresh(run)

    notification_service.notify(
        db,
        notification_service.EVENT_CLEANUP_COMPLETED,
        "Retention cleanup completed" + (" (dry run)" if dry_run else ""),
        f"Retention run #{run.id}: {run.deleted_count} bundle(s) "
        f"{'would be' if dry_run else ''} removed, freeing {run.freed_bytes} bytes",
    )
    return run
