"""Dashboard, settings, API tokens and Nexus tests."""

from tests.conftest import create_server, upload_nar


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def test_dashboard_stats(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    create_server(client, admin_headers, name="dash-srv")
    resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
    data = resp.json()
    assert data["total_servers"] == 1
    assert data["total_bundles"] == 1
    assert data["storage_bytes"] > 0
    assert data["active_versions"] == 1


def test_dashboard_charts(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    resp = client.get("/api/v1/dashboard/charts?days=7", headers=admin_headers)
    data = resp.json()
    assert len(data["uploads"]) == 7
    assert len(data["deployments"]) == 7
    assert len(data["storage_growth"]) == 7
    today_uploads = data["uploads"][-1]["count"]
    assert today_uploads == 1


def test_dashboard_recent(client, admin_headers, developer_headers):
    upload_nar(client, developer_headers)
    uploads = client.get("/api/v1/dashboard/recent-uploads", headers=admin_headers).json()
    assert len(uploads) == 1
    activity = client.get("/api/v1/dashboard/activity", headers=admin_headers).json()
    assert any(a["action"] == "UPLOAD" for a in activity)


# ---------------------------------------------------------------------------
# Settings & API tokens
# ---------------------------------------------------------------------------
def test_settings_get_and_update(client, admin_headers):
    resp = client.get("/api/v1/settings/", headers=admin_headers)
    assert resp.status_code == 200
    keys = {s["key"] for s in resp.json()["settings"]}
    assert "ssh_timeout" in keys

    resp = client.put(
        "/api/v1/settings/", headers=admin_headers, json={"values": {"ssh_timeout": "60"}}
    )
    assert resp.status_code == 200
    resp = client.get("/api/v1/settings/", headers=admin_headers)
    value = next(s for s in resp.json()["settings"] if s["key"] == "ssh_timeout")
    assert value["value"] == "60"


def test_settings_unknown_key_rejected(client, admin_headers):
    resp = client.put(
        "/api/v1/settings/", headers=admin_headers, json={"values": {"bogus": "x"}}
    )
    assert resp.status_code == 400


def test_api_token_full_flow(client, admin_headers):
    resp = client.post(
        "/api/v1/settings/api-tokens",
        headers=admin_headers,
        json={"name": "ci-token", "role": "viewer", "expires_days": 30},
    )
    assert resp.status_code == 201
    token = resp.json()["token"]
    assert token.startswith("nrm_")

    # Use the token
    resp = client.get("/api/v1/servers/", headers={"X-API-Key": token})
    assert resp.status_code == 200

    # Viewer-role token cannot create servers
    resp = client.post(
        "/api/v1/servers/",
        headers={"X-API-Key": token},
        json={"name": "x", "hostname": "x", "ssh_host": "x", "ssh_user": "x"},
    )
    assert resp.status_code == 403

    # Revoke → no longer usable
    tokens = client.get("/api/v1/settings/api-tokens", headers=admin_headers).json()
    token_id = tokens[0]["id"]
    assert client.delete(f"/api/v1/settings/api-tokens/{token_id}", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/servers/", headers={"X-API-Key": token}).status_code == 401


def test_notification_crud(client, admin_headers):
    resp = client.post(
        "/api/v1/settings/notifications",
        headers=admin_headers,
        json={
            "name": "ops-slack",
            "type": "slack",
            "target": "https://hooks.slack.com/services/xxx",
            "events": ["deployment_failed"],
            "is_enabled": True,
        },
    )
    assert resp.status_code == 201
    config_id = resp.json()["id"]
    assert resp.json()["events"] == "deployment_failed"

    resp = client.put(
        f"/api/v1/settings/notifications/{config_id}",
        headers=admin_headers,
        json={
            "name": "ops-slack",
            "type": "webhook",
            "target": "https://example.com/hook",
            "events": [],
            "is_enabled": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "webhook"

    assert client.delete(f"/api/v1/settings/notifications/{config_id}", headers=admin_headers).status_code == 200


# ---------------------------------------------------------------------------
# Nexus
# ---------------------------------------------------------------------------
def test_nexus_server_crud(client, admin_headers, viewer_headers):
    resp = client.post(
        "/api/v1/nexus/servers",
        headers=admin_headers,
        json={"name": "nexus-main", "url": "http://nexus.local:8081", "username": "admin", "password": "secret"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["has_password"] is True
    assert "password" not in data

    servers = client.get("/api/v1/nexus/servers", headers=viewer_headers).json()
    assert len(servers) == 1

    assert client.delete(f"/api/v1/nexus/servers/{data['id']}", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/nexus/servers", headers=viewer_headers).json() == []


def test_nexus_search_with_mock(client, admin_headers, monkeypatch):
    from app.schemas.schemas import NexusArtifact
    from app.services import nexus_service

    client.post(
        "/api/v1/nexus/servers",
        headers=admin_headers,
        json={"name": "nexus-mock", "url": "http://nexus.local:8081"},
    )
    server_id = client.get("/api/v1/nexus/servers", headers=admin_headers).json()[0]["id"]

    def fake_search(server, q, repository, group, artifact, version, limit):
        return [
            NexusArtifact(
                repository="nar-releases",
                group="org.apache.nifi",
                artifact="nifi-demo-nar",
                version="9.9.9",
                download_url="http://nexus.local/repository/nar-releases/nifi-demo-nar-9.9.9.nar",
                sha256="abc",
            )
        ]

    monkeypatch.setattr(nexus_service, "search_artifacts", fake_search)
    resp = client.get(f"/api/v1/nexus/servers/{server_id}/search?q=demo", headers=admin_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["artifact"] == "nifi-demo-nar"
