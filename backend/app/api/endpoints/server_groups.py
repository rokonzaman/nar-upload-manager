"""Server group (NiFi cluster) management and group deployments."""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_admin, require_developer, require_viewer
from app.models.models import AuditAction, Deployment, NarBundle, NiFiServer, ServerGroup, User, UserRole
from app.schemas.schemas import (
    DeploymentOut,
    GroupDeployRequest,
    Message,
    NiFiServerOut,
    ServerGroupCreate,
    ServerGroupOut,
    ServerGroupUpdate,
)
from app.services import audit_service, deployment_service
from app.api.endpoints.deployments import _run_deployment_task

router = APIRouter(prefix="/server-groups", tags=["server-groups"])


def _to_out(group: ServerGroup) -> ServerGroupOut:
    out = ServerGroupOut.model_validate(group)
    out.servers = [NiFiServerOut.model_validate(s) for s in group.members]
    out.server_count = len(group.members)
    return out


def _get_group(db: Session, group_id: int) -> ServerGroup:
    group = (
        db.query(ServerGroup)
        .options(joinedload(ServerGroup.members))
        .filter(ServerGroup.id == group_id)
        .first()
    )
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server group not found")
    return group


def _resolve_servers(db: Session, server_ids: List[int]) -> List[NiFiServer]:
    servers = []
    for server_id in server_ids:
        server = db.query(NiFiServer).filter(NiFiServer.id == server_id).first()
        if server is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Server {server_id} not found"
            )
        servers.append(server)
    return servers


@router.get("/", response_model=List[ServerGroupOut])
def list_groups(
    db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> List[ServerGroupOut]:
    groups = (
        db.query(ServerGroup)
        .options(joinedload(ServerGroup.members))
        .order_by(ServerGroup.name)
        .all()
    )
    return [_to_out(g) for g in groups]


@router.post("/", response_model=ServerGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: ServerGroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ServerGroupOut:
    if db.query(ServerGroup).filter(ServerGroup.name == payload.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists")
    group = ServerGroup(
        name=payload.name,
        description=payload.description,
        environment=payload.environment,
    )
    group.members = _resolve_servers(db, payload.server_ids)
    db.add(group)
    db.commit()
    db.refresh(group)
    audit_service.log_action(
        db, request, admin, "GROUP_CREATE", resource_type="server_group",
        resource_id=group.id, target_server=group.name,
        details=f"Members: {[s.name for s in group.members]}",
    )
    return _to_out(_get_group(db, group.id))


@router.get("/{group_id}", response_model=ServerGroupOut)
def get_group(
    group_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> ServerGroupOut:
    return _to_out(_get_group(db, group_id))


@router.put("/{group_id}", response_model=ServerGroupOut)
def update_group(
    group_id: int,
    payload: ServerGroupUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ServerGroupOut:
    group = _get_group(db, group_id)
    data = payload.model_dump(exclude_unset=True, exclude={"server_ids"})
    if "name" in data and data["name"] != group.name:
        if db.query(ServerGroup).filter(ServerGroup.name == data["name"]).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists")
    if "environment" in data and data["environment"]:
        data["environment"] = data["environment"].upper()
    for key, value in data.items():
        setattr(group, key, value)
    if payload.server_ids is not None:
        group.members = _resolve_servers(db, payload.server_ids)
    db.commit()
    audit_service.log_action(
        db, request, admin, "GROUP_UPDATE", resource_type="server_group",
        resource_id=group.id, target_server=group.name,
        details=f"Members: {[s.name for s in group.members]}",
    )
    return _to_out(_get_group(db, group_id))


@router.delete("/{group_id}", response_model=Message)
def delete_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    group = _get_group(db, group_id)
    db.delete(group)
    db.commit()
    audit_service.log_action(
        db, request, admin, "GROUP_DELETE", resource_type="server_group",
        resource_id=group_id, target_server=group.name,
    )
    return Message(message=f"Server group '{group.name}' deleted")


@router.post("/{group_id}/deploy", response_model=List[DeploymentOut], status_code=status.HTTP_201_CREATED)
def deploy_to_group(
    group_id: int,
    payload: GroupDeployRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> List[DeploymentOut]:
    """Deploy one NAR to every node in the group (e.g. all 3 cluster nodes) at once."""
    group = _get_group(db, group_id)
    if not group.members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group '{group.name}' has no member servers",
        )
    bundle = db.query(NarBundle).filter(NarBundle.id == payload.bundle_id).first()
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")

    if user.role != UserRole.ADMIN.value and user.deploy_environments:
        allowed = {e.strip().upper() for e in user.deploy_environments.split(",") if e.strip()}
        for server in group.members:
            if server.environment.upper() not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Deploy to '{server.name}' ({server.environment}) not allowed – your deployment environments are: {user.deploy_environments}",
                )

    deployments = deployment_service.create_deployment_records(
        db,
        bundle,
        list(group.members),
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
        db, request, user, AuditAction.DEPLOY, resource_type="server_group",
        resource_id=group.id, target_server=group.name,
        bundle=bundle.artifact, version=bundle.version,
        details=f"Group deploy to {len(deployments)} node(s): "
        f"{[s.name for s in group.members]} dry_run={payload.dry_run} restart={payload.restart_nifi}",
    )
    refreshed = (
        db.query(Deployment)
        .options(joinedload(Deployment.bundle), joinedload(Deployment.server))
        .filter(Deployment.id.in_([d.id for d in deployments]))
        .all()
    )
    refreshed.sort(key=lambda d: d.id)
    return [DeploymentOut.model_validate(d) for d in refreshed]
