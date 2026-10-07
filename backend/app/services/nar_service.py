"""NAR file handling: validation, checksums, metadata extraction, storage."""

import hashlib
import io
import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.models.models import NarBundle

settings = get_settings()
logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024  # 1 MiB
_DEFAULT_GROUP = "org.apache.nifi"

# nifi-example-processors-nar-1.2.3.nar -> (nifi-example-processors-nar, 1.2.3)
_FILENAME_RE = re.compile(r"^(?P<artifact>.+?)-(?P<version>\d[^/]*)\.nar$", re.IGNORECASE)


class NarValidationError(ValueError):
    """Raised when a NAR file fails validation."""


def secure_filename(filename: str) -> str:
    """Sanitize an uploaded filename (path traversal protection)."""
    name = filename.replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if name in ("", ".", ".."):
        raise NarValidationError("Invalid filename")
    return name


def validate_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions_list:
        raise NarValidationError(
            f"Invalid file type '{ext}'. Allowed: {', '.join(settings.allowed_extensions_list)}"
        )


def compute_checksums(path: Path) -> Tuple[str, str, int]:
    """Return (sha256, md5, size) for a file, read in chunks."""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            sha256.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return sha256.hexdigest(), md5.hexdigest(), size


def read_manifest(path: Path) -> Dict[str, str]:
    """Read META-INF/MANIFEST.MF from a NAR (zip) file. Returns {} when absent."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.upper().endswith("META-INF/MANIFEST.MF")]
            if not names:
                return {}
            raw = zf.read(names[0]).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return {}

    manifest: Dict[str, str] = {}
    current_key: Optional[str] = None
    for line in raw.splitlines():
        if line.startswith(" ") and current_key:
            manifest[current_key] += line[1:]  # continuation line
        elif ":" in line:
            key, _, value = line.partition(":")
            current_key = key.strip()
            manifest[current_key] = value.strip()
    return manifest


def extract_metadata(path: Path, filename: str) -> Dict[str, Optional[str]]:
    """Extract group/artifact/version from the manifest, falling back to the filename."""
    manifest = read_manifest(path)
    group = (
        manifest.get("Nar-Group")
        or manifest.get("Bundle-Group")
        or manifest.get("Implementation-Vendor-Id")
    )
    artifact = manifest.get("Nar-Id") or manifest.get("Bundle-SymbolicName") or manifest.get("Bundle-Name")
    version = manifest.get("Nar-Version") or manifest.get("Bundle-Version") or manifest.get("Implementation-Version")
    build_date = manifest.get("Build-Timestamp") or manifest.get("Build-Date")

    if not artifact or not version:
        match = _FILENAME_RE.match(filename)
        if match:
            artifact = artifact or match.group("artifact")
            version = version or match.group("version")

    if not artifact:
        artifact = filename[: -len(".nar")] if filename.lower().endswith(".nar") else filename
    if not version:
        version = "0.0.0"
    if not group:
        group = _DEFAULT_GROUP

    parsed_build: Optional[datetime] = None
    if build_date:
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed_build = datetime.strptime(build_date, fmt)
                break
            except ValueError:
                continue

    return {
        "bundle_group": group,
        "artifact": artifact,
        "version": version,
        "build_date": parsed_build,
        "manifest": manifest,
    }


def bundle_storage_path(group: str, artifact: str, version: str, filename: str) -> Path:
    """Absolute storage path for a bundle inside the NAR directory."""
    safe = secure_filename(filename)
    return settings.nar_dir / group / artifact / version / safe


def save_upload(file: UploadFile, dest: Path) -> None:
    """Stream an UploadFile to disk enforcing MAX_UPLOAD_SIZE."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > settings.MAX_UPLOAD_SIZE:
                    raise NarValidationError(
                        f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE} bytes"
                    )
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if written == 0:
        dest.unlink(missing_ok=True)
        raise NarValidationError("Empty file")


def find_duplicate(db, group: str, artifact: str, version: str) -> Optional[NarBundle]:
    return (
        db.query(NarBundle)
        .filter(
            NarBundle.bundle_group == group,
            NarBundle.artifact == artifact,
            NarBundle.version == version,
        )
        .first()
    )


def create_bundle_from_upload(
    db, file: UploadFile, uploaded_by: str, replace: bool = False, source: str = "local"
) -> Tuple[NarBundle, bool]:
    """Validate, store and register an uploaded NAR. Returns (bundle, replaced)."""
    if not file.filename:
        raise NarValidationError("Missing filename")
    filename = secure_filename(file.filename)
    validate_extension(filename)

    tmp_path = settings.nar_dir / ".tmp" / f"{datetime.utcnow().timestamp()}_{filename}"
    save_upload(file, tmp_path)

    try:
        sha256, md5, size = compute_checksums(tmp_path)
        meta = extract_metadata(tmp_path, filename)
        group, artifact, version = meta["bundle_group"], meta["artifact"], meta["version"]

        existing = find_duplicate(db, group, artifact, version)
        replaced = False
        if existing:
            if not replace:
                raise NarValidationError(
                    f"Bundle {group}:{artifact}:{version} already exists. Use replace=true to overwrite."
                )
            # Replace: remove old file, reuse row
            old_path = Path(existing.file_path)
            if old_path.exists() and old_path != tmp_path:
                old_path.unlink()
            final_path = bundle_storage_path(group, artifact, version, filename)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_path), str(final_path))
            existing.filename = filename
            existing.file_path = str(final_path)
            existing.file_size = size
            existing.sha256 = sha256
            existing.md5 = md5
            existing.build_date = meta["build_date"]
            existing.uploaded_by = uploaded_by
            existing.uploaded_at = datetime.utcnow()
            existing.source = source
            db.commit()
            db.refresh(existing)
            return existing, True

        final_path = bundle_storage_path(group, artifact, version, filename)
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
            uploaded_by=uploaded_by,
            source=source,
        )
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        return bundle, replaced
    finally:
        tmp_path.unlink(missing_ok=True)


def compare_manifests(path_a: Path, path_b: Path) -> Dict[str, Dict[str, str]]:
    """Return added/removed/changed manifest keys between two NAR files."""
    a, b = read_manifest(path_a), read_manifest(path_b)
    added = {k: v for k, v in b.items() if k not in a}
    removed = {k: v for k, v in a.items() if k not in b}
    changed = {k: f"{a[k]} -> {b[k]}" for k in a if k in b and a[k] != b[k]}
    return {"added": added, "removed": removed, "changed": changed}


def nar_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")
