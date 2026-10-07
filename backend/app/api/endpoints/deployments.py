"""Deployment endpoints: create (multi-server), history, rollback, compatibility."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal, get_db
from app.core.deps import require_developer, require_viewer
from app.models.models import (
    AuditAction,
    AuditResult,
    Deployment,
    DeploymentStatus,
    NarBundle,
    NiFiServer,
    User,
    UserRole,
)
from app.schemas.schemas import (
    CompatibilityReport,
    DeploymentCreate,
    DeploymentOut,
    Message,
    Page,
)
from app.services import audit_service, deployment_service
from app.api.endpoints.common import paginate

router = APIRouter(prefix="/deployments", tags=["deployments"])


def _get_deployment(db: Session, deployment_id: int) -> Deployment:
    deployment = (
        db.query(Deployment)
        .options(joinedload(Deployment.bundle), joinedload(Deployment.server))
        .filter(Deployment.id == deployment_id)
        .first()
    )
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return deployment


def _run_deployment_task(deployment_id: int) -> None:
    """Background task entrypoint with its own DB session."""
    db = SessionLocal()
    try:
        deployment_service.run_deployment(db, deployment_id)
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if deployment is not None:
            audit_service.log_action(
                db,
                None,
                None,
                AuditAction.DEPLOY,
                resource_type="deployment",
                resource_id=deployment.id,
                target_server=deployment.server.name if deployment.server else None,
                bundle=deployment.bundle.artifact if deployment.bundle else None,
                version=deployment.bundle.version if deployment.bundle else None,
                result=(
                    AuditResult.SUCCESS.value
                    if deployment.status == DeploymentStatus.SUCCESS.value
                    else AuditResult.FAILURE.value
                ),
                error_message=deployment.error_message,
                username=deployment.deployed_by,
            )
    finally:
        db.close()


@router.get("/", response_model=Page[DeploymentOut])
def list_deployments(
    status_filter: Optional[str] = Query(None, alias="status"),
    server_id: Optional[int] = None,
    bundle_id: Optional[int] = None,
    user: Optional[str] = None,
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> Page[DeploymentOut]:
    query = db.query(Deployment).options(
        joinedload(Deployment.bundle), joinedload(Deployment.server)
    )
    if status_filter:
        query = query.filter(Deployment.status == status_filter)
    if server_id:
        query = query.filter(Deployment.server_id == server_id)
    if bundle_id:
        query = query.filter(Deployment.bundle_id == bundle_id)
    if user:
        query = query.filter(Deployment.deployed_by.ilike(f"%{user}%"))
    if from_date:
        query = query.filter(Deployment.created_at >= from_date)
    if to_date:
        query = query.filter(Deployment.created_at <= to_date)
    result = paginate(query.order_by(Deployment.created_at.desc()), page, page_size)
    result.items = [DeploymentOut.model_validate(d) for d in result.items]
    return result


@router.post("/", response_model=List[DeploymentOut], status_code=status.HTTP_201_CREATED)
def create_deployments(
    payload: DeploymentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> List[DeploymentOut]:
    bundle = db.query(NarBundle).filter(NarBundle.id == payload.bundle_id).first()
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")

    servers: List[NiFiServer] = []
    for server_id in payload.server_ids:
        server = db.query(NiFiServer).filter(NiFiServer.id == server_id).first()
        if server is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Server {server_id} not found")
        servers.append(server)

    if user.role != UserRole.ADMIN.value and user.deploy_environments:
        allowed = {e.strip().upper() for e in user.deploy_environments.split(",") if e.strip()}
        for server in servers:
            if server.environment.upper() not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Deploy to '{server.name}' ({server.environment}) not allowed – your deployment environments are: {user.deploy_environments}",
                )

    deployments = deployment_service.create_deployment_records(
        db,
        bundle,
        servers,
        dry_run=payload.dry_run,
        backup=payload.backup,
        restart_nifi=payload.restart_nifi,
        notes=payload.notes,
        target_directory=payload.target_directory,
        deployed_by=user.username,
    )
    for deployment in deployments:
        background_tasks.add_task(_run_deployment_task, deployment.id)

    audit_service.log_action(
        db, request, user, AuditAction.DEPLOY, resource_type="deployment",
        resource_id=",".join(str(d.id) for d in deployments),
        bundle=bundle.artifact, version=bundle.version,
        details=f"Servers: {payload.server_ids} dry_run={payload.dry_run} restart={payload.restart_nifi}",
    )
    db.expire_all()
    return [
        DeploymentOut.model_validate(_get_deployment(db, d.id)) for d in deployments
    ]


@router.get("/{deployment_id}", response_model=DeploymentOut)
def get_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> DeploymentOut:
    return DeploymentOut.model_validate(_get_deployment(db, deployment_id))


@router.post("/{deployment_id}/rollback", response_model=DeploymentOut)
def rollback(
    deployment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> DeploymentOut:
    try:
        deployment = deployment_service.rollback_deployment(db, deployment_id, user.username)
    except ValueError as exc:
        audit_service.log_action(
            db, request, user, AuditAction.ROLLBACK, resource_type="deployment",
            resource_id=deployment_id, result=AuditResult.FAILURE.value, error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit_service.log_action(
        db, request, user, AuditAction.ROLLBACK, resource_type="deployment",
        resource_id=deployment.id, target_server=deployment.server.name,
        bundle=deployment.bundle.artifact, version=deployment.bundle.version,
    )
    return DeploymentOut.model_validate(_get_deployment(db, deployment_id))


class CompatibilityRequest(BaseModel):
    bundle_id: int
    server_ids: List[int]


@router.post("/compatibility", response_model=List[CompatibilityReport])
def compatibility(
    payload: CompatibilityRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> List[CompatibilityReport]:
    bundle = db.query(NarBundle).filter(NarBundle.id == payload.bundle_id).first()
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")
    reports: List[CompatibilityReport] = []
    for server_id in payload.server_ids:
        server = db.query(NiFiServer).filter(NiFiServer.id == server_id).first()
        if server is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Server {server_id} not found")
        reports.append(deployment_service.check_compatibility(db, bundle, server))
    return reports
