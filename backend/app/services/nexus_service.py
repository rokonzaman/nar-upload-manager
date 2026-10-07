"""Nexus Repository Manager integration (REST API v3)."""

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models.models import NexusServer
from app.schemas.schemas import NexusArtifact

settings = get_settings()
logger = logging.getLogger(__name__)


class NexusError(RuntimeError):
    """Raised on Nexus API failures."""


def _auth(server: NexusServer) -> Optional[Tuple[str, str]]:
    if server.username and server.password_encrypted:
        return server.username, decrypt_secret(server.password_encrypted)
    return None


def _client(server: NexusServer, timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(
        base_url=server.url.rstrip("/"),
        auth=_auth(server),
        timeout=timeout,
        headers={"Accept": "application/json"},
    )


def test_connection(server: NexusServer) -> Dict[str, Any]:
    """Check connectivity and authentication against a Nexus server."""
    try:
        with _client(server, timeout=10) as client:
            resp = client.get("/service/rest/v1/status")
            if resp.status_code == 200:
                version = None
                try:
                    resp2 = client.get("/service/rest/v1/status/writable")
                    version = resp2.status_code == 200
                except httpx.HTTPError:
                    pass
                return {"success": True, "message": "Nexus is reachable", "nifi_version": None, "latency_ms": None}
            return {"success": False, "message": f"Nexus returned HTTP {resp.status_code}", "latency_ms": None}
    except httpx.HTTPError as exc:
        return {"success": False, "message": f"Connection failed: {exc}", "latency_ms": None}


def list_repositories(server: NexusServer) -> List[Dict[str, str]]:
    with _client(server) as client:
        resp = client.get("/service/rest/v1/repositories")
        if resp.status_code != 200:
            raise NexusError(f"Failed to list repositories: HTTP {resp.status_code}")
        return [
            {"name": r.get("name"), "format": r.get("format"), "type": r.get("type"), "url": r.get("url")}
            for r in resp.json()
        ]


def search_artifacts(
    server: NexusServer,
    q: Optional[str] = None,
    repository: Optional[str] = None,
    group: Optional[str] = None,
    artifact: Optional[str] = None,
    version: Optional[str] = None,
    limit: int = 50,
) -> List[NexusArtifact]:
    """Search NAR assets via /service/rest/v1/search/assets."""
    params: Dict[str, str] = {}
    if q:
        params["q"] = q
    if repository:
        params["repository"] = repository
    if group:
        params["group"] = group
    if artifact:
        params["name"] = artifact
    if version:
        params["version"] = version

    results: List[NexusArtifact] = []
    token: Optional[str] = None
    with _client(server) as client:
        while len(results) < limit:
            if token:
                params["continuationToken"] = token
            resp = client.get("/service/rest/v1/search/assets", params=params)
            if resp.status_code != 200:
                raise NexusError(f"Nexus search failed: HTTP {resp.status_code} — {resp.text[:200]}")
            data = resp.json()
            for item in data.get("items", []):
                download_url = item.get("downloadUrl", "")
                if not download_url.endswith(".nar"):
                    continue
                checksum = (item.get("checksum") or {}).get("sha256")
                results.append(
                    NexusArtifact(
                        repository=item.get("repository", repository or ""),
                        group=item.get("group", ""),
                        artifact=item.get("name", ""),
                        version=item.get("version", ""),
                        download_url=download_url,
                        sha256=checksum,
                        size=item.get("fileSize"),
                    )
                )
                if len(results) >= limit:
                    break
            token = data.get("continuationToken")
            if not token:
                break
    return results


def download_artifact(server: NexusServer, download_url: str, expected_sha256: Optional[str] = None) -> Path:
    """Download an artifact to a temp file, verifying its sha256 when provided."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".nar", dir=settings.nar_dir)
    tmp_path = Path(tmp.name)
    sha = hashlib.sha256()
    try:
        with tmp:
            with _client(server, timeout=120) as client:
                with client.stream("GET", download_url) as resp:
                    if resp.status_code != 200:
                        raise NexusError(f"Download failed: HTTP {resp.status_code}")
                    for chunk in resp.iter_bytes(1024 * 1024):
                        sha.update(chunk)
                        tmp.write(chunk)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    if expected_sha256 and sha.hexdigest() != expected_sha256:
        tmp_path.unlink(missing_ok=True)
        raise NexusError(
            f"Checksum mismatch for downloaded artifact (expected {expected_sha256}, got {sha.hexdigest()})"
        )
    return tmp_path
