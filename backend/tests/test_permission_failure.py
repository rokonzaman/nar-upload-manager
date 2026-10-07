"""Verify SFTP permission errors are recorded as FAILED, not left IN_PROGRESS.

The deployment pipeline previously only caught SSHError; an SFTP PermissionError
(mkdir/put denied on the server) escaped as an unhandled exception, surfacing as
an HTTP 500 and leaving the deployment record stuck IN_PROGRESS forever.
These tests confirm that permission/storage errors now normalize to SSHError
and the deployment is marked FAILED with a readable error message.
"""

from tests.conftest import create_server, upload_nar

from app.core.database import SessionLocal
from app.models.models import DeploymentStatus, NiFiServer
from app.services import deployment_service
from app.services import ssh_service


class DeniedSFTP:
    """An SFTP client that raises PermissionError on stat/mkdir/put."""

    def __init__(self, fs):
        self.fs = fs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def stat(self, path):
        raise FileNotFoundError(path)

    def mkdir(self, path):
        raise PermissionError(path)

    def put(self, local, remote):
        raise PermissionError(remote)

    def remove(self, path):
        raise PermissionError(path)

    def get(self, remote, local):
        raise PermissionError(remote)


def test_permission_denied_marks_deployment_failed(
    client, developer_headers, admin_headers, monkeypatch
):
    resp = upload_nar(client, developer_headers, artifact="crgb-bulk-data", version="1.0.1")
    bundle = resp.json()[0]["bundle"]
    server = create_server(client, admin_headers, name="nifi-denied", enabled=True)

    # Patch the real SSHClient so connect() fast-returns and _sftp() yields a
    # permission-denied client. This exercises the real mkdir_p/upload_file
    # normalization (OSError -> SSHError) instead of a hand-faked SSH class.
    monkeypatch.setattr(ssh_service.SSHClient, "connect", lambda self: self)
    monkeypatch.setattr(
        ssh_service.SSHClient,
        "_sftp",
        lambda self: DeniedSFTP({}),
    )

    db = SessionLocal()
    try:
        srv = db.query(NiFiServer).filter(NiFiServer.id == server["id"]).one()
        bnd = (
            db.query(deployment_service.NarBundle)
            .filter(deployment_service.NarBundle.id == bundle["id"])
            .one()
        )
        dep = deployment_service.create_deployment_records(
            db, bnd, [srv], deployed_by="developer"
        )[0]

        deployment_service.run_deployment(db, dep.id)
        db.refresh(dep)

        # MUST be FAILED with a readable permission message, never IN_PROGRESS.
        assert dep.status == DeploymentStatus.FAILED.value
        assert dep.error_message and "SFTP error" in dep.error_message
        assert dep.completed_at is not None
    finally:
        db.close()