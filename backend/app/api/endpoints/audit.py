"""Audit log endpoints with search, filtering and CSV export."""

import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.models import AuditLog, User
from app.schemas.schemas import AuditLogOut, Page
from app.api.endpoints.common import paginate

router = APIRouter(prefix="/audit-logs", tags=["audit"])

_CSV_COLUMNS = [
    "id", "timestamp", "username", "full_name", "action", "resource_type", "resource_id",
    "target_server", "bundle", "version", "result", "ip_address", "user_agent",
    "error_message", "details",
]


def _filtered_query(
    db: Session,
    username: Optional[str],
    action: Optional[str],
    result: Optional[str],
    target_server: Optional[str],
    bundle: Optional[str],
    resource_type: Optional[str],
    from_date: Optional[datetime],
    to_date: Optional[datetime],
    q: Optional[str],
):
    query = db.query(AuditLog)
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username}%"))
    if action:
        query = query.filter(AuditLog.action == action)
    if result:
        query = query.filter(AuditLog.result == result)
    if target_server:
        query = query.filter(AuditLog.target_server.ilike(f"%{target_server}%"))
    if bundle:
        query = query.filter(AuditLog.bundle.ilike(f"%{bundle}%"))
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if from_date:
        query = query.filter(AuditLog.timestamp >= from_date)
    if to_date:
        query = query.filter(AuditLog.timestamp <= to_date)
    if q:
        like = f"%{q}%"
        query = query.filter(
            AuditLog.details.ilike(like)
            | AuditLog.error_message.ilike(like)
            | AuditLog.bundle.ilike(like)
        )
    return query


@router.get("/", response_model=Page[AuditLogOut])
def list_audit_logs(
    username: Optional[str] = None,
    action: Optional[str] = None,
    result: Optional[str] = None,
    target_server: Optional[str] = None,
    bundle: Optional[str] = None,
    resource_type: Optional[str] = None,
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Page[AuditLogOut]:
    query = _filtered_query(
        db, username, action, result, target_server, bundle, resource_type, from_date, to_date, q
    )
    page_result = paginate(query.order_by(AuditLog.timestamp.desc()), page, page_size)
    page_result.items = [AuditLogOut.model_validate(a) for a in page_result.items]
    return page_result


@router.get("/export")
def export_audit_logs(
    username: Optional[str] = None,
    action: Optional[str] = None,
    result: Optional[str] = None,
    target_server: Optional[str] = None,
    bundle: Optional[str] = None,
    resource_type: Optional[str] = None,
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    q: Optional[str] = None,
    format: str = "csv",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    if format != "csv":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Only csv export is supported")
    query = _filtered_query(
        db, username, action, result, target_server, bundle, resource_type, from_date, to_date, q
    )
    rows = query.order_by(AuditLog.timestamp.desc()).limit(10000).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_COLUMNS)
    for row in rows:
        writer.writerow([getattr(row, col) for col in _CSV_COLUMNS])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


@router.get("/actions", response_model=List[str])
def list_actions(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> List[str]:
    rows = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [r[0] for r in rows]
