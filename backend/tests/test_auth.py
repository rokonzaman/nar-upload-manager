"""Auth, RBAC and rate-limiting tests."""

from app.api.endpoints import auth as auth_module


def test_login_success(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"
    assert data["access_token"]


def test_login_bad_password(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401


def test_me(client, admin_headers):
    resp = client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_auth_config_public(client):
    resp = client.get("/api/v1/auth/config")
    assert resp.status_code == 200
    assert resp.json()["dev_mode"] is True


def test_logout_audited(client, admin_headers):
    resp = client.post("/api/v1/auth/logout", headers=admin_headers)
    assert resp.status_code == 200
    logs = client.get("/api/v1/audit-logs/?action=LOGOUT", headers=admin_headers).json()
    assert logs["total"] == 1


def test_viewer_cannot_create_server(client, viewer_headers):
    resp = client.post(
        "/api/v1/servers/",
        headers=viewer_headers,
        json={
            "name": "x",
            "hostname": "x",
            "ssh_host": "x",
            "ssh_user": "x",
        },
    )
    assert resp.status_code == 403


def test_viewer_cannot_upload(client, viewer_headers):
    resp = client.post(
        "/api/v1/bundles/upload",
        headers=viewer_headers,
        files=[("files", ("a.nar", b"x", "application/octet-stream"))],
    )
    assert resp.status_code == 403


def test_users_admin_only(client, admin_headers, developer_headers):
    assert client.get("/api/v1/auth/users", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/auth/users", headers=developer_headers).status_code == 403


def test_admin_can_change_role(client, admin_headers):
    users = client.get("/api/v1/auth/users", headers=admin_headers).json()
    viewer = next(u for u in users if u["username"] == "viewer")
    resp = client.put(
        f"/api/v1/auth/users/{viewer['id']}", headers=admin_headers, json={"role": "developer"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "developer"


def test_login_rate_limit(client, monkeypatch):
    auth_module._attempts.clear()
    monkeypatch.setattr(auth_module.settings, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"})
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"})
    assert resp.status_code == 429
