"""Audit log tests."""

from tests.conftest import create_server, upload_nar


def test_actions_are_audited(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    resp = client.get("/api/v1/audit-logs/", headers=admin_headers)
    data = resp.json()
    assert data["total"] >= 1
    actions = {i["action"] for i in data["items"]}
    assert "UPLOAD" in actions
    entry = next(i for i in data["items"] if i["action"] == "UPLOAD")
    assert entry["username"] == "developer"
    assert entry["result"] == "success"
    assert entry["ip_address"]


def test_failed_login_audited(client, admin_headers):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    resp = client.get("/api/v1/audit-logs/?action=LOGIN&result=failure", headers=admin_headers)
    assert resp.json()["total"] == 1


def test_filter_by_username(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    resp = client.get("/api/v1/audit-logs/?username=developer", headers=admin_headers)
    assert all(i["username"] == "developer" for i in resp.json()["items"])


def test_export_csv(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    resp = client.get("/api/v1/audit-logs/export?format=csv", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("id,timestamp,username")
    assert len(lines) >= 2


def test_actions_list(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    create_server(client, admin_headers, name="audit-srv")
    resp = client.get("/api/v1/audit-logs/actions", headers=admin_headers)
    actions = resp.json()
    assert "UPLOAD" in actions
    assert "SERVER_CREATE" in actions


def test_audit_admin_only(client, developer_headers, viewer_headers):
    assert client.get("/api/v1/audit-logs/", headers=developer_headers).status_code == 403
    assert client.get("/api/v1/audit-logs/", headers=viewer_headers).status_code == 403
