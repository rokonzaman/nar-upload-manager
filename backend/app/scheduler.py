"""APScheduler integration: retention cleanup + Nexus sync cron jobs."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.models import NexusServer
from app.services import retention_service

settings = get_settings()
logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _retention_job() -> None:
    """Run retention cleanup according to the stored policy."""
    db = SessionLocal()
    try:
        policy = retention_service.get_policy(db)
        if not policy.is_enabled:
            logger.debug("Retention policy disabled; skipping scheduled run")
            return
        logger.info("Running scheduled retention (dry_run=%s)", policy.dry_run)
        run = retention_service.execute(db, dry_run=policy.dry_run, triggered_by="scheduler")
        logger.info("Scheduled retention completed: run=%s deleted=%s", run.id, run.deleted_count)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled retention failed")
    finally:
        db.close()


def _nexus_sync_job(nexus_server_id: int) -> None:
    """Sync one Nexus server (delegates to the sync logic with a system user)."""
    db = SessionLocal()
    try:
        server = db.query(NexusServer).filter(NexusServer.id == nexus_server_id).first()
        if server is None or not server.is_enabled:
            return
        logger.info("Running scheduled Nexus sync for %s", server.name)
        # Reuse endpoint logic without HTTP context
        from app.services import nexus_service, nar_service, notification_service
        from app.models.models import NarBundle
        import shutil

        artifacts = nexus_service.search_artifacts(
            server, repository=server.default_repository, limit=200
        )
        synced = 0
        for item in artifacts:
            if nar_service.find_duplicate(db, item.group, item.artifact, item.version):
                continue
            try:
                tmp_path = nexus_service.download_artifact(server, item.download_url, item.sha256)
                filename = item.download_url.rsplit("/", 1)[-1]
                sha256, md5, size = nar_service.compute_checksums(tmp_path)
                final_path = nar_service.bundle_storage_path(item.group, item.artifact, item.version, filename)
                final_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_path), str(final_path))
                db.add(
                    NarBundle(
                        bundle_group=item.group,
                        artifact=item.artifact,
                        version=item.version,
                        filename=filename,
                        file_path=str(final_path),
                        file_size=size,
                        sha256=sha256,
                        md5=md5,
                        uploaded_by="scheduler",
                        source="nexus",
                    )
                )
                db.commit()
                synced += 1
            except Exception:  # noqa: BLE001
                logger.exception("Failed to sync %s:%s", item.artifact, item.version)
        from datetime import datetime

        server.last_sync_at = datetime.utcnow()
        db.commit()
        notification_service.notify(
            db,
            notification_service.EVENT_NEXUS_SYNC_COMPLETED,
            "Scheduled Nexus sync completed",
            f"Server {server.name}: {synced} artifact(s) imported",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled Nexus sync failed")
    finally:
        db.close()


def _refresh_jobs(scheduler: BackgroundScheduler) -> None:
    """(Re)register cron jobs from the database state."""
    db = SessionLocal()
    try:
        policy = retention_service.get_policy(db)
        scheduler.add_job(
            _retention_job,
            CronTrigger.from_crontab(policy.schedule),
            id="retention",
            replace_existing=True,
            name="Retention cleanup",
        )
        for server in db.query(NexusServer).filter(NexusServer.is_enabled.is_(True)).all():
            if server.sync_schedule:
                scheduler.add_job(
                    _nexus_sync_job,
                    CronTrigger.from_crontab(server.sync_schedule),
                    args=[server.id],
                    id=f"nexus_sync_{server.id}",
                    replace_existing=True,
                    name=f"Nexus sync ({server.name})",
                )
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled")
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _refresh_jobs(_scheduler)
    _scheduler.start()
    logger.info("Scheduler started with jobs: %s", [j.id for j in _scheduler.get_jobs()])
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
