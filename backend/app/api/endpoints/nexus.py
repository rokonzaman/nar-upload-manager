"""Nexus Repository Manager integration endpoints."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin, require_developer, require_viewer
from app.core.security import encrypt_secret
from app.models.models import AuditAction, AuditResult, NarBundle, NexusServer, User
from app.schemas.schemas import (
    Message,
    NarBundleOut,
    NexusArtifact,
    NexusDownloadRequest,
    NexusServerCreate,
    NexusServerOut,
    NexusServerUpdate,
    NexusSyncResult,
    ServerTestResult,
)
from app.services import audit_service, nar_service, nexus_service, notification_service

router = APIRouter(prefix="/nexus", tags=["nexus"])


def _to_out(server: NexusServer) -> NexusServerOut:
    out = NexusServerOut.model_validate(server)
    out.has_password = bool(server.password_encrypted)
    return out


def _get_server(db: Session, server_id: int) -> NexusServer:
    server = db.query(NexusServer).filter(NexusServer.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nexus server not found")
    return server


@router.get("/servers", response_model=List[NexusServerOut])
def list_nexus_servers(
    db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> List[NexusServerOut]:
    return [_to_out(s) for s in db.query(NexusServer).order_by(NexusServer.name).all()]


@router.post("/servers", response_model=NexusServerOut, status_code=status.HTTP_201_CREATED)
def create_nexus_server(
    payload: NexusServerCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NexusServerOut:
    if db.query(NexusServer).filter(NexusServer.name == payload.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nexus server name already exists")
    data = payload.model_dump(exclude={"password"})
    server = NexusServer(**data)
    if payload.password:
        server.password_encrypted = encrypt_secret(payload.password)
    db.add(server)
    db.commit()
    db.refresh(server)
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="nexus_server",
        resource_id=server.id, details=f"Created Nexus server {server.name}",
    )
    return _to_out(server)


@router.put("/servers/{server_id}", response_model=NexusServerOut)
def update_nexus_server(
    server_id: int,
    payload: NexusServerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NexusServerOut:
    server = _get_server(db, server_id)
    data = payload.model_dump(exclude_unset=True, exclude={"password"})
    for key, value in data.items():
        setattr(server, key, value)
    if payload.password is not None:
        server.password_encrypted = encrypt_secret(payload.password) if payload.password else None
    db.commit()
    db.refresh(server)
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="nexus_server",
        resource_id=server.id, details=f"Updated Nexus server {server.name}",
    )
    return _to_out(server)


@router.delete("/servers/{server_id}", response_model=Message)
def delete_nexus_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    server = _get_server(db, server_id)
    db.delete(server)
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="nexus_server",
        resource_id=server_id, details=f"Deleted Nexus server {server.name}",
    )
    return Message(message=f"Nexus server '{server.name}' deleted")


@router.post("/servers/{server_id}/test", response_model=ServerTestResult)
def test_nexus_server(
    server_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ServerTestResult:
    server = _get_server(db, server_id)
    result = nexus_service.test_connection(server)
    return ServerTestResult(**result)


@router.get("/servers/{server_id}/repositories")
def list_repositories(
    server_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> list:
    server = _get_server(db, server_id)
    try:
        return nexus_service.list_repositories(server)
    except nexus_service.NexusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.get("/servers/{server_id}/search", response_model=List[NexusArtifact])
def search(
    server_id: int,
    q: Optional[str] = None,
    repository: Optional[str] = None,
    group: Optional[str] = None,
    artifact: Optional[str] = None,
    version: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> List[NexusArtifact]:
    server = _get_server(db, server_id)
    try:
        return nexus_service.search_artifacts(server, q, repository, group, artifact, version, limit)
    except nexus_service.NexusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/download", response_model=NarBundleOut, status_code=status.HTTP_201_CREATED)
def download_and_import(
    payload: NexusDownloadRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> NarBundleOut:
    server = _get_server(db, payload.server_id)
    filename = payload.download_url.rsplit("/", 1)[-1]
    try:
        tmp_path = nexus_service.download_artifact(server, payload.download_url)
    except nexus_service.NexusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    try:
        meta = nar_service.extract_metadata(tmp_path, filename)
        group = payload.group or meta["bundle_group"]
        artifact = payload.artifact or meta["artifact"]
        version = payload.version or meta["version"]

        existing = nar_service.find_duplicate(db, group, artifact, version)
        if existing:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Bundle {group}:{artifact}:{version} already exists in the repository",
            )

        sha256, md5, size = nar_service.compute_checksums(tmp_path)
        final_path = nar_service.bundle_storage_path(group, artifact, version, filename)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_path), str(final_path))

        bundle = NarBundle(
            bundle_group=group,
            artifact=artifact,
            version=version,
            filename=filename,
            file_path=str(final_path),
            file_size=size,
            sha256=sha256,
            md5=md5,
            build_date=meta["build_date"],
            uploaded_by=user.username,
            source="nexus",
        )
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
    finally:
        tmp_path.unlink(missing_ok=True)

    audit_service.log_action(
        db, request, user, AuditAction.NEXUS_DOWNLOAD, resource_type="bundle",
        resource_id=bundle.id, bundle=bundle.artifact, version=bundle.version,
        details=f"From Nexus server {server.name}",
    )
    return NarBundleOut.model_validate(bundle)


@router.post("/servers/{server_id}/sync", response_model=NexusSyncResult)
def sync_nexus_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NexusSyncResult:
    """Import all not-yet-present NAR artifacts from the default repository."""
    server = _get_server(db, server_id)
    result = NexusSyncResult(server_id=server.id, synced=0, skipped=0)
    try:
        artifacts = nexus_service.search_artifacts(
            server, repository=server.default_repository, limit=200
        )
    except nexus_service.NexusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    for item in artifacts:
        if nar_service.find_duplicate(db, item.group, item.artifact, item.version):
            result.skipped += 1
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
                    uploaded_by=admin.username,
                    source="nexus",
                )
            )
            db.commit()
            result.synced += 1
        except Exception as exc:  # noqa: BLE001 - continue sync on per-artifact failure
            result.errors.append(f"{item.artifact}:{item.version}: {exc}")

    server.last_sync_at = datetime.utcnow()
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.NEXUS_SYNC, resource_type="nexus_server",
        resource_id=server.id,
        result=AuditResult.SUCCESS.value if not result.errors else AuditResult.FAILURE.value,
        details=f"synced={result.synced} skipped={result.skipped} errors={len(result.errors)}",
    )
    notification_service.notify(
        db,
        notification_service.EVENT_NEXUS_SYNC_COMPLETED,
        "Nexus sync completed",
        f"Server {server.name}: synced={result.synced}, skipped={result.skipped}, errors={len(result.errors)}",
    )
    return result
