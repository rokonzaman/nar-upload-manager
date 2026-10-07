"""NiFi server CRUD tests."""

from tests.conftest import create_server


def test_create_server(client, admin_headers):
    data = create_server(client, admin_headers)
    assert data["name"] == "test-server"
    assert data["environment"] == "DEV"
    assert data["has_ssh_password"] is True
    assert "ssh_password" not in data
    assert "ssh_password_encrypted" not in data


def test_duplicate_server_name(client, admin_headers):
    create_server(client, admin_headers)
    resp = client.post(
        "/api/v1/servers/",
        headers=admin_headers,
        json={"name": "test-server", "hostname": "h", "ssh_host": "h", "ssh_user": "u"},
    )
    assert resp.status_code == 409


def test_list_servers_filter(client, admin_headers):
    create_server(client, admin_headers, name="srv-dev", environment="DEV")
    create_server(client, admin_headers, name="srv-prod", environment="prod")
    resp = client.get("/api/v1/servers/?environment=PROD", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "srv-prod"
    assert data["items"][0]["environment"] == "PROD"


def test_update_server(client, admin_headers):
    server = create_server(client, admin_headers)
    resp = client.put(
        f"/api/v1/servers/{server['id']}",
        headers=admin_headers,
        json={"description": "updated", "environment": "qa", "is_enabled": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "updated"
    assert data["environment"] == "QA"
    assert data["is_enabled"] is False


def test_delete_server(client, admin_headers):
    server = create_server(client, admin_headers)
    assert client.delete(f"/api/v1/servers/{server['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/v1/servers/{server['id']}", headers=admin_headers).status_code == 404


def test_invalid_port_rejected(client, admin_headers):
    resp = client.post(
        "/api/v1/servers/",
        headers=admin_headers,
        json={"name": "bad", "hostname": "h", "ssh_host": "h", "ssh_user": "u", "ssh_port": 70000},
    )
    assert resp.status_code == 422


def test_environments_endpoint(client, viewer_headers):
    resp = client.get("/api/v1/servers/environments", headers=viewer_headers)
    assert resp.status_code == 200
    assert "DEV" in resp.json()
    assert "PROD" in resp.json()


def test_health_unreachable_server(client, admin_headers):
    server = create_server(client, admin_headers)
    resp = client.get(f"/api/v1/servers/{server['id']}/health", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reachable"] is False
    assert data["warnings"]


def test_connection_test_unreachable(client, admin_headers):
    server = create_server(client, admin_headers)
    resp = client.post(f"/api/v1/servers/{server['id']}/test-connection", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is False
