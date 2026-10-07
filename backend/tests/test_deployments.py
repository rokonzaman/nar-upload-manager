"""Deployment pipeline tests (no real SSH — failures are exercised)."""

from tests.conftest import create_server, upload_nar


def _bundle(client, headers):
    return upload_nar(client, headers).json()[0]["bundle"]


def test_dry_run_deployment_succeeds(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    server = create_server(client, admin_headers, enabled=True)
    resp = client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [server["id"]], "dry_run": True},
    )
    assert resp.status_code == 201
    deployment = resp.json()[0]
    detail = client.get(f"/api/v1/deployments/{deployment['id']}", headers=developer_headers).json()
    assert detail["status"] == "success"
    assert detail["dry_run"] is True
    assert "Dry run" in detail["log"]


def test_deployment_to_disabled_server_fails(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    server = create_server(client, admin_headers, enabled=False)
    resp = client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [server["id"]]},
    )
    deployment = resp.json()[0]
    detail = client.get(f"/api/v1/deployments/{deployment['id']}", headers=developer_headers).json()
    assert detail["status"] == "failed"
    assert "disabled" in detail["error_message"]
    assert "Step 1/7" in detail["log"]


def test_deployment_unreachable_server_fails_gracefully(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    server = create_server(client, admin_headers, enabled=True)
    resp = client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [server["id"]]},
    )
    detail = client.get(f"/api/v1/deployments/{resp.json()[0]['id']}", headers=developer_headers).json()
    assert detail["status"] == "failed"
    assert detail["error_message"]


def test_multi_server_deployment_creates_one_per_server(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    s1 = create_server(client, admin_headers, name="s1", enabled=False)
    s2 = create_server(client, admin_headers, name="s2", enabled=False)
    resp = client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [s1["id"], s2["id"]]},
    )
    assert len(resp.json()) == 2


def test_deployment_unknown_bundle(client, developer_headers):
    resp = client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": 4242, "server_ids": [1]},
    )
    assert resp.status_code == 404


def test_compatibility_report(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    server = create_server(client, admin_headers, enabled=False)
    resp = client.post(
        "/api/v1/deployments/compatibility",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [server["id"]]},
    )
    data = resp.json()[0]
    assert data["compatible"] is False
    assert any(w["level"] == "error" for w in data["warnings"])


def test_rollback_requires_successful_deployment(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    server = create_server(client, admin_headers, enabled=False)
    deployment = client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [server["id"]]},
    ).json()[0]
    resp = client.post(f"/api/v1/deployments/{deployment['id']}/rollback", headers=developer_headers)
    assert resp.status_code == 400


def test_deployments_list_filter(client, developer_headers, admin_headers):
    bundle = _bundle(client, developer_headers)
    server = create_server(client, admin_headers, enabled=False)
    client.post(
        "/api/v1/deployments/",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "server_ids": [server["id"]]},
    )
    resp = client.get("/api/v1/deployments/?status=failed", headers=developer_headers)
    assert resp.json()["total"] == 1
    resp = client.get("/api/v1/deployments/?status=success", headers=developer_headers)
    assert resp.json()["total"] == 0
