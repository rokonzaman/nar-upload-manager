"""NAR bundle repository endpoints."""

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_developer, require_viewer
from app.models.models import AuditAction, AuditResult, Deployment, DeploymentStatus, NarBundle, User
from app.schemas.schemas import (
    BulkActionResult,
    BulkIds,
    BundleCompareResult,
    BundleGroup,
    BundleUpdate,
    Message,
    NarBundleOut,
    Page,
    UploadResult,
)
from app.services import audit_service, nar_service, notification_service
from app.api.endpoints.common import paginate

router = APIRouter(prefix="/bundles", tags=["bundles"])


def _get_bundle(db: Session, bundle_id: int) -> NarBundle:
    bundle = db.query(NarBundle).filter(NarBundle.id == bundle_id).first()
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")
    return bundle


def _active_deployment_exists(db: Session, bundle_id: int) -> bool:
    return (
        db.query(Deployment)
        .filter(
            Deployment.bundle_id == bundle_id,
            Deployment.status == DeploymentStatus.SUCCESS.value,
        )
        .first()
        is not None
    )


# ---------------------------------------------------------------------------
# Listing / browsing
# ---------------------------------------------------------------------------
@router.get("/", response_model=Page[NarBundleOut])
def list_bundles(
    q: Optional[str] = None,
    group: Optional[str] = None,
    artifact: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    tag: Optional[str] = None,
    source: Optional[str] = None,
    pinned: Optional[bool] = None,
    sort_by: str = "uploaded_at",
    sort_order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> Page[NarBundleOut]:
    query = db.query(NarBundle)
    if q:
        like = f"%{q}%"
        query = query.filter(
            NarBundle.artifact.ilike(like)
            | NarBundle.bundle_group.ilike(like)
            | NarBundle.version.ilike(like)
        )
    if group:
        query = query.filter(NarBundle.bundle_group == group)
    if artifact:
        query = query.filter(NarBundle.artifact == artifact)
    if status_filter:
        query = query.filter(NarBundle.status == status_filter)
    if tag:
        query = query.filter(NarBundle.tags.ilike(f"%{tag}%"))
    if source:
        query = query.filter(NarBundle.source == source)
    if pinned is not None:
        query = query.filter(NarBundle.is_pinned.is_(pinned))

    sort_col = {
        "uploaded_at": NarBundle.uploaded_at,
        "file_size": NarBundle.file_size,
        "version": NarBundle.version,
        "artifact": NarBundle.artifact,
    }.get(sort_by, NarBundle.uploaded_at)
    query = query.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())

    result = paginate(query, page, page_size)
    result.items = [NarBundleOut.model_validate(b) for b in result.items]
    return result


@router.get("/grouped", response_model=List[BundleGroup])
def list_grouped(
    db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> List[BundleGroup]:
    bundles = db.query(NarBundle).order_by(NarBundle.uploaded_at.desc()).all()
    grouped: Dict[tuple, List[NarBundle]] = {}
    for bundle in bundles:
        grouped.setdefault((bundle.bundle_group, bundle.artifact), []).append(bundle)
    out: List[BundleGroup] = []
    for (group, artifact), versions in sorted(grouped.items(), key=lambda kv: kv[0][1]):
        out.append(
            BundleGroup(
                bundle_group=group,
                artifact=artifact,
                versions=[NarBundleOut.model_validate(v) for v in versions],
                latest_version=versions[0].version,
                total_size=sum(v.file_size for v in versions),
            )
        )
    return out


@router.get("/stats/storage")
def storage_stats(
    db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> dict:
    bundles = db.query(NarBundle).all()
    by_group: Dict[str, int] = {}
    for b in bundles:
        by_group[b.bundle_group] = by_group.get(b.bundle_group, 0) + b.file_size
    return {
        "total_bytes": sum(by_group.values()),
        "count": len(bundles),
        "by_group": [{"label": k, "value": v} for k, v in sorted(by_group.items())],
    }


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=List[UploadResult])
async def upload_bundles(
    request: Request,
    files: List[UploadFile],
    replace: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> List[UploadResult]:
    results: List[UploadResult] = []
    for file in files:
        try:
            bundle, replaced = nar_service.create_bundle_from_upload(
                db, file, uploaded_by=user.username, replace=replace
            )
            results.append(
                UploadResult(
                    filename=file.filename or "?",
                    success=True,
                    bundle=NarBundleOut.model_validate(bundle),
                    replaced=replaced,
                )
            )
            audit_service.log_action(
                db, request, user, AuditAction.UPLOAD, resource_type="bundle",
                resource_id=bundle.id, bundle=bundle.artifact, version=bundle.version,
                details=f"Uploaded {file.filename} ({bundle.file_size} bytes)"
                + (" (replaced existing)" if replaced else ""),
            )
            notification_service.notify(
                db,
                notification_service.EVENT_UPLOAD_COMPLETED,
                "NAR upload completed",
                f"{bundle.artifact}:{bundle.version} uploaded by {user.username}",
            )
        except nar_service.NarValidationError as exc:
            results.append(UploadResult(filename=file.filename or "?", success=False, error=str(exc)))
            audit_service.log_action(
                db, request, user, AuditAction.UPLOAD, resource_type="bundle",
                result=AuditResult.FAILURE.value, error_message=str(exc),
                details=f"filename={file.filename}",
            )
    return results


# ---------------------------------------------------------------------------
# Single bundle operations
# ---------------------------------------------------------------------------
@router.get("/{bundle_id}", response_model=NarBundleOut)
def get_bundle(
    bundle_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)
) -> NarBundleOut:
    return NarBundleOut.model_validate(_get_bundle(db, bundle_id))


@router.put("/{bundle_id}", response_model=NarBundleOut)
def update_bundle(
    bundle_id: int,
    payload: BundleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> NarBundleOut:
    bundle = _get_bundle(db, bundle_id)
    data = payload.model_dump(exclude_unset=True)
    renamed = data.get("artifact") and data["artifact"] != bundle.artifact
    for key, value in data.items():
        setattr(bundle, key, value)
    db.commit()
    db.refresh(bundle)
    if renamed:
        audit_service.log_action(
            db, request, user, AuditAction.RENAME, resource_type="bundle",
            resource_id=bundle.id, bundle=bundle.artifact, version=bundle.version,
        )
    else:
        audit_service.log_action(
            db, request, user, "UPDATE_BUNDLE", resource_type="bundle",
            resource_id=bundle.id, bundle=bundle.artifact, version=bundle.version,
            details=str(data),
        )
    return NarBundleOut.model_validate(bundle)


@router.delete("/{bundle_id}", response_model=Message)
def delete_bundle(
    bundle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> Message:
    bundle = _get_bundle(db, bundle_id)
    if bundle.is_pinned:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bundle is pinned")
    if _active_deployment_exists(db, bundle.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bundle has an active deployment and cannot be deleted",
        )
    path = Path(bundle.file_path)
    if path.exists():
        path.unlink()
    db.delete(bundle)
    db.commit()
    audit_service.log_action(
        db, request, user, AuditAction.DELETE, resource_type="bundle",
        resource_id=bundle_id, bundle=bundle.artifact, version=bundle.version,
    )
    return Message(message=f"Deleted {bundle.artifact}:{bundle.version}")


@router.post("/bulk-delete", response_model=BulkActionResult)
def bulk_delete(
    payload: BulkIds,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> BulkActionResult:
    result = BulkActionResult()
    for bundle_id in payload.ids:
        bundle = db.query(NarBundle).filter(NarBundle.id == bundle_id).first()
        if bundle is None:
            result.failed[bundle_id] = "Not found"
            continue
        if bundle.is_pinned:
            result.failed[bundle_id] = "Pinned"
            continue
        if _active_deployment_exists(db, bundle.id):
            result.failed[bundle_id] = "Active deployment"
            continue
        path = Path(bundle.file_path)
        if path.exists():
            path.unlink()
        db.delete(bundle)
        result.succeeded.append(bundle_id)
        audit_service.log_action(
            db, request, user, AuditAction.DELETE, resource_type="bundle",
            resource_id=bundle_id, bundle=bundle.artifact, version=bundle.version,
            details="bulk delete",
        )
    db.commit()
    return result


@router.get("/{bundle_id}/download")
def download_bundle(
    bundle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
) -> FileResponse:
    bundle = _get_bundle(db, bundle_id)
    path = Path(bundle.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    audit_service.log_action(
        db, request, user, AuditAction.DOWNLOAD, resource_type="bundle",
        resource_id=bundle.id, bundle=bundle.artifact, version=bundle.version,
    )
    return FileResponse(
        path,
        filename=bundle.filename,
        media_type="application/octet-stream",
        headers={"X-SHA256": bundle.sha256},
    )


@router.post("/{bundle_id}/replace", response_model=NarBundleOut)
async def replace_bundle(
    bundle_id: int,
    request: Request,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
) -> NarBundleOut:
    bundle = _get_bundle(db, bundle_id)
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")
    try:
        filename = nar_service.secure_filename(file.filename)
        nar_service.validate_extension(filename)
    except nar_service.NarValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    tmp_path = Path(bundle.file_path).parent / f".replace_{filename}"
    try:
        nar_service.save_upload(file, tmp_path)
        sha256, md5, size = nar_service.compute_checksums(tmp_path)
        old_path = Path(bundle.file_path)
        final_path = old_path.parent / filename
        if old_path.exists() and old_path != final_path:
            old_path.unlink()
        tmp_path.replace(final_path)
        bundle.filename = filename
        bundle.file_path = str(final_path)
        bundle.file_size = size
        bundle.sha256 = sha256
        bundle.md5 = md5
        db.commit()
        db.refresh(bundle)
    except nar_service.NarValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)

    audit_service.log_action(
        db, request, user, "REPLACE_BUNDLE", resource_type="bundle",
        resource_id=bundle.id, bundle=bundle.artifact, version=bundle.version,
    )
    return NarBundleOut.model_validate(bundle)


class CompareRequest(BaseModel):
    id_a: int
    id_b: int


@router.post("/compare", response_model=BundleCompareResult)
def compare_bundles(
    payload: CompareRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
) -> BundleCompareResult:
    a = _get_bundle(db, payload.id_a)
    b = _get_bundle(db, payload.id_b)
    diff = nar_service.compare_manifests(Path(a.file_path), Path(b.file_path))
    return BundleCompareResult(
        bundle_a=NarBundleOut.model_validate(a),
        bundle_b=NarBundleOut.model_validate(b),
        same_group=a.bundle_group == b.bundle_group,
        same_artifact=a.artifact == b.artifact,
        same_checksum=a.sha256 == b.sha256,
        size_diff_bytes=b.file_size - a.file_size,
        manifest_diff=diff,
    )
