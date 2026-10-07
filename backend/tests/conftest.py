"""Test fixtures. Environment variables MUST be set before importing app modules."""

import io
import os
import tempfile
import zipfile

_TMP = tempfile.mkdtemp(prefix="nar_manager_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["NAR_DIRECTORY"] = f"{_TMP}/nar"
os.environ["BACKUP_DIRECTORY"] = f"{_TMP}/backup"
os.environ["LOG_FILE"] = f"{_TMP}/logs/test.log"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["AUTH_DEV_MODE"] = "true"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "1000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import User  # noqa: E402

USERS = {
    "admin": ("admin123", "admin"),
    "developer": ("developer123", "developer"),
    "viewer": ("viewer123", "viewer"),
}


def make_nar_bytes(group="org.apache.nifi", artifact="nifi-test-nar", version="1.0.0") -> bytes:
    """Build a valid in-memory .nar file."""
    manifest = (
        "Manifest-Version: 1.0\n"
        f"Nar-Group: {group}\n"
        f"Nar-Id: {artifact}\n"
        f"Nar-Version: {version}\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", manifest)
        zf.writestr("META-INF/bundled-dependencies/lib.jar", b"content")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def reset_db():
    """Full table reset between tests."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for username, (password, role) in USERS.items():
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    full_name=username.title(),
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def admin_token(client) -> str:
    return _login(client, "admin", USERS["admin"][0])


@pytest.fixture()
def developer_token(client) -> str:
    return _login(client, "developer", USERS["developer"][0])


@pytest.fixture()
def viewer_token(client) -> str:
    return _login(client, "viewer", USERS["viewer"][0])


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, admin_token) -> dict:
    return auth_headers(admin_token)


@pytest.fixture()
def developer_headers(client, developer_token) -> dict:
    return auth_headers(developer_token)


@pytest.fixture()
def viewer_headers(client, viewer_token) -> dict:
    return auth_headers(viewer_token)


def upload_nar(client, headers, artifact="nifi-test-nar", version="1.0.0", replace=False, group="org.apache.nifi"):
    """Helper: upload a generated NAR and return the response."""
    content = make_nar_bytes(group=group, artifact=artifact, version=version)
    return client.post(
        f"/api/v1/bundles/upload?replace={str(replace).lower()}",
        headers=headers,
        files=[("files", (f"{artifact}-{version}.nar", content, "application/octet-stream"))],
    )


def create_server(client, headers, name="test-server", enabled=True, **overrides):
    payload = {
        "name": name,
        "hostname": f"{name}.local",
        "ssh_host": "127.0.0.1",
        "ssh_port": 1,  # connection refused instantly — no real SSH in tests
        "ssh_user": "nifi",
        "ssh_password": "secret",
        "environment": "DEV",
        "is_enabled": enabled,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/servers/", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()
