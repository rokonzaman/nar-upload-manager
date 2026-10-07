"""Backup management endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_admin, require_developer, require_viewer
from app.models.models import AuditAction, AuditResult, Backup, User
from app.schemas.schemas import BackupOut, Message, Page
from app.services import audit_service, backup_service
from app.api.endpoints.common import paginate

router = APIRouter(prefix="/backups", tags=["backups"])


def _to_out(backup: Backup) -> BackupOut:
    out = BackupOut.model_validate(backup)
    out.server_name = backup.server.name if backup.server else None
    return out


@router.get("/", response_model=Page[BackupOut])
def list_backups(
    server_id: Optional[int] = None,
    artifact: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> Page[BackupOut]:
    query = db.query(Backup).options(joinedload(Backup.server))
    if server_id:
        query = query.filter(Backup.server_id == server_id)
    if artifact:
        query = query.filter(Backup.bundle_artifact.ilike(f"%{artifact}%"))
    if q:
        query = query.filter(Backup.filename.ilike(f"%{q}%"))
    result = paginate(query.order_by(Backup.created_at.desc()), page, page_size)
    result.items = [_to_out(b) for b in result.items]
    return result


@router.post("/{backup_id}/restore", response_model=Message)
def restore(
    backup_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> Message:
    backup = db.query(Backup).options(joinedload(Backup.server)).filter(Backup.id == backup_id).first()
    if backup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    try:
        backup_service.restore_backup(db, backup)
    except (ValueError, FileNotFoundError) as exc:
        audit_service.log_action(
            db, request, user, AuditAction.BACKUP_RESTORE, resource_type="backup",
            resource_id=backup_id, target_server=backup.server.name if backup.server else None,
            result=AuditResult.FAILURE.value, error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit_service.log_action(
        db, request, user, AuditAction.BACKUP_RESTORE, resource_type="backup",
        resource_id=backup_id, target_server=backup.server.name if backup.server else None,
        bundle=backup.bundle_artifact, version=backup.bundle_version,
    )
    return Message(message=f"Backup restored to {backup.original_path}")


@router.delete("/{backup_id}", response_model=Message)
def delete_backup(
    backup_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if backup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    path = Path(backup.backup_path)
    if path.exists():
        path.unlink()
    db.delete(backup)
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.DELETE, resource_type="backup", resource_id=backup_id,
    )
    return Message(message="Backup deleted")


@router.post("/cleanup-orphans")
def cleanup_orphans(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    deleted, freed = backup_service.cleanup_orphaned_backups(db)
    audit_service.log_action(
        db, request, admin, "BACKUP_CLEANUP", resource_type="backup",
        details=f"deleted={deleted} freed_bytes={freed}",
    )
    return {"deleted": deleted, "freed_bytes": freed}
