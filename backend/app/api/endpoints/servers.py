"""NiFi server management endpoints."""

import time
import urllib.request
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import require_admin, require_developer, require_viewer
from app.core.security import encrypt_secret
from app.models.models import AuditAction, NiFiServer, User
from app.schemas.schemas import (
    DeleteNarFilesRequest,
    Message,
    NiFiServerCreate,
    NiFiServerOut,
    NiFiServerUpdate,
    Page,
    RemoteNarFile,
    RestartResult,
    ServerHealth,
    ServerTestResult,
)
from app.services import audit_service, ssh_service
from app.api.endpoints.common import paginate

import logging

logger = logging.getLogger(__name__)

settings = get_settings()
router = APIRouter(prefix="/servers", tags=["servers"])


def _to_out(server: NiFiServer) -> NiFiServerOut:
    data = NiFiServerOut.model_validate(server)
    data.has_ssh_password = bool(server.ssh_password_encrypted)
    return data


def _get_server(db: Session, server_id: int) -> NiFiServer:
    server = db.query(NiFiServer).filter(NiFiServer.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


@router.get("/environments", response_model=List[str])
def list_environments(_: User = Depends(require_viewer)) -> List[str]:
    return settings.environments_list


@router.get("/", response_model=Page[NiFiServerOut])
def list_servers(
    q: Optional[str] = None,
    environment: Optional[str] = None,
    enabled: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> Page[NiFiServerOut]:
    query = db.query(NiFiServer)
    if q:
        like = f"%{q}%"
        query = query.filter(NiFiServer.name.ilike(like) | NiFiServer.hostname.ilike(like))
    if environment:
        query = query.filter(NiFiServer.environment == environment.upper())
    if enabled is not None:
        query = query.filter(NiFiServer.is_enabled.is_(enabled))
    result = paginate(query.order_by(NiFiServer.name), page, page_size)
    result.items = [_to_out(s) for s in result.items]
    return result


@router.post("/", response_model=NiFiServerOut, status_code=status.HTTP_201_CREATED)
def create_server(
    payload: NiFiServerCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NiFiServerOut:
    if db.query(NiFiServer).filter(NiFiServer.name == payload.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server name already exists")
    data = payload.model_dump(exclude={"ssh_password"})
    server = NiFiServer(**data)
    if payload.ssh_password:
        server.ssh_password_encrypted = encrypt_secret(payload.ssh_password)
    db.add(server)
    db.commit()
    db.refresh(server)
    audit_service.log_action(
        db, request, admin, AuditAction.SERVER_CREATE, resource_type="server",
        resource_id=server.id, target_server=server.name,
    )
    return _to_out(server)


@router.get("/{server_id}", response_model=NiFiServerOut)
def get_server(
    server_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> NiFiServerOut:
    return _to_out(_get_server(db, server_id))


@router.put("/{server_id}", response_model=NiFiServerOut)
def update_server(
    server_id: int,
    payload: NiFiServerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NiFiServerOut:
    server = _get_server(db, server_id)
    data = payload.model_dump(exclude_unset=True, exclude={"ssh_password"})
    if "name" in data and data["name"] != server.name:
        if db.query(NiFiServer).filter(NiFiServer.name == data["name"]).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server name already exists")
    if "environment" in data and data["environment"]:
        data["environment"] = data["environment"].upper()
    for key, value in data.items():
        setattr(server, key, value)
    if payload.ssh_password is not None:
        server.ssh_password_encrypted = encrypt_secret(payload.ssh_password) if payload.ssh_password else None
    db.commit()
    db.refresh(server)
    audit_service.log_action(
        db, request, admin, AuditAction.SERVER_UPDATE, resource_type="server",
        resource_id=server.id, target_server=server.name,
    )
    return _to_out(server)


@router.delete("/{server_id}", response_model=Message)
def delete_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    server = _get_server(db, server_id)
    db.delete(server)
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.SERVER_DELETE, resource_type="server",
        resource_id=server_id, target_server=server.name,
    )
    return Message(message=f"Server '{server.name}' deleted")


@router.post("/{server_id}/test-connection", response_model=ServerTestResult)
def test_server_connection(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ServerTestResult:
    server = _get_server(db, server_id)
    result = ssh_service.test_connection(server)
    audit_service.log_action(
        db, request, admin, "TEST_CONNECTION", resource_type="server",
        resource_id=server.id, target_server=server.name,
        result="success" if result["success"] else "failure",
        error_message=None if result["success"] else result["message"],
    )
    return ServerTestResult(**result)


@router.get("/{server_id}/health", response_model=ServerHealth)
def server_health(
    server_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> ServerHealth:
    server = _get_server(db, server_id)
    base = {"server_id": server.id, "checked_at": datetime.utcnow()}
    try:
        with ssh_service.SSHClient(server, timeout=10) as ssh:
            metrics = ssh.get_health()
        return ServerHealth(reachable=True, **base, **{k: v for k, v in metrics.items()})
    except ssh_service.SSHError as exc:
        return ServerHealth(reachable=False, warnings=[str(exc)], **base)


@router.get("/{server_id}/nar-files", response_model=List[RemoteNarFile])
def list_remote_nar_files(
    server_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> List[RemoteNarFile]:
    server = _get_server(db, server_id)
    try:
        with ssh_service.SSHClient(server, timeout=10) as ssh:
            files = ssh.list_remote_nars_detailed(server.nar_directory)
        return [RemoteNarFile(**f) for f in files]
    except ssh_service.SSHError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.delete("/{server_id}/nar-files", response_model=Message)
def delete_remote_nar_files(
    server_id: int,
    payload: DeleteNarFilesRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    server = _get_server(db, server_id)
    try:
        with ssh_service.SSHClient(server, timeout=30) as ssh:
            results = ssh.delete_remote_files(server.nar_directory, payload.filenames)
    except ssh_service.SSHError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    failures = [r for r in results if not r["success"]]
    if failures:
        audit_service.log_action(
            db, request, admin, AuditAction.NAR_DELETE, resource_type="nar",
            resource_id=server.name, target_server=server.name,
            result="failure",
            error_message="; ".join(f"{f['filename']}: {f['error']}" for f in failures),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete: {', '.join(f['filename'] for f in failures)}",
        )

    deleted = ", ".join(payload.filenames)
    audit_service.log_action(
        db, request, admin, AuditAction.NAR_DELETE, resource_type="nar",
        resource_id=server.name, target_server=server.name,
        result="success",
        details=deleted,
    )
    return Message(message=f"Deleted {len(payload.filenames)} file(s): {deleted}")


@router.post("/{server_id}/restart", response_model=RestartResult)
def restart_server(
    server_id: int,
    request: Request,
    wait_for_bootstrap: bool = Query(False, description="Poll NiFi API URL until reachable (60s timeout)"),
    db: Session = Depends(get_db),
    developer: User = Depends(require_developer),
) -> RestartResult:
    server = _get_server(db, server_id)
    logger.info("Restarting NiFi on %s: %s", server.name, server.restart_command)
    try:
        with ssh_service.SSHClient(server, timeout=120) as ssh:
            rc, out, err = ssh.exec_command(server.restart_command, timeout=120)
    except ssh_service.SSHError as exc:
        logger.error("SSH restart failed for %s: %s", server.name, exc)
        audit_service.log_action(
            db, request, developer, "NIFI_RESTART", resource_type="server",
            resource_id=server.id, target_server=server.name,
            result="failure", error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    success = rc == 0
    audit_service.log_action(
        db, request, developer, "NIFI_RESTART", resource_type="server",
        resource_id=server.id, target_server=server.name,
        result="success" if success else "failure",
        error_message=None if success else (err or out),
    )

    bootstrap_info = ""
    if success and wait_for_bootstrap:
        bootstrap_info = _bootstrap_wait(server, name=server.name, timeout=60.0)

    message = f"Restart command {'succeeded' if success else 'failed'} (exit code {rc})"
    if bootstrap_info:
        message += f" | {bootstrap_info}"
    return RestartResult(
        success=success,
        message=message,
        command=server.restart_command,
        exit_code=rc,
        stdout=out,
        stderr=err,
    )


def _bootstrap_wait(server: "NiFiServer", *, name: str = "", timeout: float = 60.0) -> str:
    if not server.nifi_api_url:
        logger.info("[%s] No NiFi API URL configured, waiting 15s fixed", name)
        time.sleep(15)
        return "no API URL — waited 15s"
    start = time.monotonic()
    url = f"{server.nifi_api_url.rstrip('/')}/system-diagnostics"
    logger.info("[%s] Polling %s every 5s (timeout %.0fs)", name, url, timeout)
    while (time.monotonic() - start) < timeout:
        elapsed = time.monotonic() - start
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            if resp.status == 200:
                logger.info("[%s] NiFi reachable after %.1fs", name, elapsed)
                return f"booted in {elapsed:.1f}s"
        except Exception:
            logger.debug("[%s] Not ready yet (%.1fs elapsed)", name, elapsed)
        time.sleep(5)
    logger.warning("[%s] NiFi did not become reachable within %.0fs", name, timeout)
    return f"bootstrap timed out after {timeout:.0f}s"
