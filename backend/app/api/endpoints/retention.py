"""Retention policy endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin, require_viewer
from app.models.models import AuditAction, RetentionRun, User
from app.schemas.schemas import (
    Page,
    RetentionExecuteRequest,
    RetentionPolicyIn,
    RetentionPolicyOut,
    RetentionPreview,
    RetentionRunOut,
)
from app.services import audit_service, retention_service
from app.api.endpoints.common import paginate

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get("/policy", response_model=RetentionPolicyOut)
def get_policy(
    db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> RetentionPolicyOut:
    return RetentionPolicyOut.model_validate(retention_service.get_policy(db))


@router.put("/policy", response_model=RetentionPolicyOut)
def update_policy(
    payload: RetentionPolicyIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RetentionPolicyOut:
    policy = retention_service.get_policy(db)
    for key, value in payload.model_dump().items():
        setattr(policy, key, value)
    db.commit()
    db.refresh(policy)
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="retention_policy",
        resource_id=policy.id,
        details=f"keep_latest={policy.keep_latest} keep_days={policy.keep_days} "
        f"enabled={policy.is_enabled} dry_run={policy.dry_run} schedule={policy.schedule}",
    )
    return RetentionPolicyOut.model_validate(policy)


@router.post("/preview", response_model=RetentionPreview)
def preview(
    payload: Optional[RetentionPolicyIn] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> RetentionPreview:
    policy = retention_service.get_policy(db)
    effective = payload or RetentionPolicyIn(
        keep_latest=policy.keep_latest,
        keep_days=policy.keep_days,
        is_enabled=policy.is_enabled,
        dry_run=policy.dry_run,
        schedule=policy.schedule,
    )
    candidates, protected = retention_service.build_candidates(
        db, effective.keep_latest, effective.keep_days
    )
    return RetentionPreview(
        candidates=candidates + protected,
        total_count=len(candidates),
        total_size_bytes=sum(c.file_size for c in candidates),
        policy=effective,
    )


@router.post("/execute", response_model=RetentionRunOut)
def execute(
    payload: RetentionExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RetentionRunOut:
    if not payload.dry_run and not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion requires confirm=true (run a dry run first to review the report)",
        )
    run = retention_service.execute(db, dry_run=payload.dry_run, triggered_by=admin.username)
    audit_service.log_action(
        db, request, admin, AuditAction.RETENTION_CLEANUP, resource_type="retention_run",
        resource_id=run.id,
        details=f"dry_run={run.dry_run} deleted={run.deleted_count} freed={run.freed_bytes}",
    )
    return RetentionRunOut.model_validate(run)


@router.get("/runs", response_model=Page[RetentionRunOut])
def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> Page[RetentionRunOut]:
    result = paginate(db.query(RetentionRun).order_by(RetentionRun.started_at.desc()), page, page_size)
    result.items = [RetentionRunOut.model_validate(r) for r in result.items]
    return result
