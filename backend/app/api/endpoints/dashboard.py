"""Dashboard endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_viewer
from app.models.models import Deployment, NarBundle, User
from app.schemas.schemas import (
    AuditLogOut,
    DashboardCharts,
    DashboardStats,
    DeploymentOut,
    NarBundleOut,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def stats(db: Session = Depends(get_db), _: User = Depends(require_viewer)) -> DashboardStats:
    return dashboard_service.get_stats(db)


@router.get("/charts", response_model=DashboardCharts)
def charts(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> DashboardCharts:
    return dashboard_service.get_charts(db, days)


@router.get("/activity", response_model=List[AuditLogOut])
def activity(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> List[AuditLogOut]:
    return [AuditLogOut.model_validate(a) for a in dashboard_service.get_recent_activity(db, limit)]


@router.get("/recent-uploads", response_model=List[NarBundleOut])
def recent_uploads(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> List[NarBundleOut]:
    rows = db.query(NarBundle).order_by(NarBundle.uploaded_at.desc()).limit(limit).all()
    return [NarBundleOut.model_validate(b) for b in rows]


@router.get("/recent-deployments", response_model=List[DeploymentOut])
def recent_deployments(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> List[DeploymentOut]:
    rows = (
        db.query(Deployment)
        .options(joinedload(Deployment.bundle), joinedload(Deployment.server))
        .order_by(Deployment.created_at.desc())
        .limit(limit)
        .all()
    )
    return [DeploymentOut.model_validate(d) for d in rows]
