"""Dashboard aggregations: stats, charts, recent activity."""

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    AuditLog,
    Backup,
    BundleStatus,
    Deployment,
    DeploymentStatus,
    NarBundle,
    NiFiServer,
)
from app.schemas.schemas import (
    DashboardCharts,
    DashboardStats,
    TimeSeriesPoint,
    TopBundle,
)
from app.services import retention_service


def get_stats(db: Session) -> DashboardStats:
    total_servers = db.query(NiFiServer).count()
    enabled_servers = db.query(NiFiServer).filter(NiFiServer.is_enabled.is_(True)).count()
    total_bundles = db.query(NarBundle).count()
    active_versions = db.query(NarBundle).filter(NarBundle.status == BundleStatus.ACTIVE.value).count()
    storage_bytes = db.query(func.coalesce(func.sum(NarBundle.file_size), 0)).scalar() or 0
    total_deployments = db.query(Deployment).count()
    failed_deployments = (
        db.query(Deployment).filter(Deployment.status == DeploymentStatus.FAILED.value).count()
    )
    total_backups = db.query(Backup).count()
    backup_bytes = db.query(func.coalesce(func.sum(Backup.file_size), 0)).scalar() or 0

    policy = retention_service.get_policy(db)
    candidates, _ = retention_service.build_candidates(db, policy.keep_latest, policy.keep_days)

    return DashboardStats(
        total_servers=total_servers,
        enabled_servers=enabled_servers,
        total_bundles=total_bundles,
        active_versions=active_versions,
        storage_bytes=int(storage_bytes),
        total_deployments=total_deployments,
        failed_deployments=failed_deployments,
        pending_cleanup=len(candidates),
        total_backups=total_backups,
        backup_bytes=int(backup_bytes),
    )


def _date_series(days: int) -> List[str]:
    today = datetime.utcnow().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def get_charts(db: Session, days: int = 30) -> DashboardCharts:
    series = _date_series(days)
    start = datetime.utcnow() - timedelta(days=days)

    def bucket(rows, date_attr) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {d: {"count": 0, "bytes": 0} for d in series}
        for value, size in rows:
            key = value.date().isoformat() if isinstance(value, datetime) else str(value)[:10]
            if key in out:
                out[key]["count"] += 1
                out[key]["bytes"] += int(size or 0)
        return out

    upload_rows = (
        db.query(NarBundle.uploaded_at, NarBundle.file_size)
        .filter(NarBundle.uploaded_at >= start)
        .all()
    )
    uploads_bucket = bucket(upload_rows, "uploaded_at")
    uploads = [TimeSeriesPoint(date=d, count=v["count"], bytes=v["bytes"]) for d, v in uploads_bucket.items()]

    deploy_rows = (
        db.query(Deployment.created_at).filter(Deployment.created_at >= start).all()
    )
    deploy_bucket: Dict[str, Dict[str, int]] = {d: {"count": 0, "bytes": 0} for d in series}
    for (value,) in deploy_rows:
        key = value.date().isoformat()
        if key in deploy_bucket:
            deploy_bucket[key]["count"] += 1
    deployments = [
        TimeSeriesPoint(date=d, count=v["count"], bytes=0) for d, v in deploy_bucket.items()
    ]

    # Storage growth: cumulative bytes of bundles uploaded up to each day
    all_uploads = db.query(NarBundle.uploaded_at, NarBundle.file_size).order_by(NarBundle.uploaded_at).all()
    growth: List[TimeSeriesPoint] = []
    cumulative = 0
    idx = 0
    for day in series:
        while idx < len(all_uploads) and all_uploads[idx][0].date().isoformat() <= day:
            cumulative += int(all_uploads[idx][1] or 0)
            idx += 1
        growth.append(TimeSeriesPoint(date=day, count=0, bytes=cumulative))

    top_rows = (
        db.query(
            NarBundle.artifact,
            NarBundle.bundle_group,
            func.count(Deployment.id).label("deployment_count"),
        )
        .join(Deployment, Deployment.bundle_id == NarBundle.id)
        .group_by(NarBundle.artifact, NarBundle.bundle_group)
        .order_by(func.count(Deployment.id).desc())
        .limit(10)
        .all()
    )
    top_bundles = [
        TopBundle(artifact=r[0], bundle_group=r[1], deployment_count=r[2]) for r in top_rows
    ]

    return DashboardCharts(
        uploads=uploads,
        deployments=deployments,
        storage_growth=growth,
        top_bundles=top_bundles,
    )


def get_recent_activity(db: Session, limit: int = 20) -> List[AuditLog]:
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
