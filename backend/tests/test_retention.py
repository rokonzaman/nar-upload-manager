"""Retention policy tests."""

from tests.conftest import upload_nar


def _seed_versions(client, headers, artifact="nifi-retention-nar", count=5):
    ids = []
    for i in range(count):
        bundle = upload_nar(client, headers, artifact=artifact, version=f"1.{i}.0").json()[0]["bundle"]
        ids.append(bundle["id"])
    return ids


def test_policy_roundtrip(client, admin_headers, viewer_headers):
    resp = client.get("/api/v1/retention/policy", headers=viewer_headers)
    assert resp.status_code == 200
    assert resp.json()["keep_latest"] >= 0

    resp = client.put(
        "/api/v1/retention/policy",
        headers=admin_headers,
        json={"keep_latest": 2, "keep_days": 0, "is_enabled": True, "dry_run": False, "schedule": "0 0 * * 0"},
    )
    assert resp.status_code == 200
    assert resp.json()["keep_latest"] == 2


def test_preview_keeps_latest_n(client, admin_headers, developer_headers):
    ids = _seed_versions(client, developer_headers, count=5)
    client.put(
        "/api/v1/retention/policy",
        headers=admin_headers,
        json={"keep_latest": 2, "keep_days": 0, "is_enabled": True, "dry_run": False, "schedule": "0 0 * * 0"},
    )
    resp = client.post("/api/v1/retention/preview", headers=admin_headers)
    data = resp.json()
    assert data["total_count"] == 3
    candidate_ids = {c["bundle_id"] for c in data["candidates"] if not c["protected"]}
    # the three oldest versions
    assert candidate_ids == set(ids[:3])


def test_pinned_bundle_protected(client, admin_headers, developer_headers):
    ids = _seed_versions(client, developer_headers, count=3)
    client.put(f"/api/v1/bundles/{ids[0]}", headers=developer_headers, json={"is_pinned": True})
    client.put(
        "/api/v1/retention/policy",
        headers=admin_headers,
        json={"keep_latest": 1, "keep_days": 0, "is_enabled": True, "dry_run": False, "schedule": "0 0 * * 0"},
    )
    preview = client.post("/api/v1/retention/preview", headers=admin_headers).json()
    protected_ids = {c["bundle_id"] for c in preview["candidates"] if c["protected"]}
    deletable_ids = {c["bundle_id"] for c in preview["candidates"] if not c["protected"]}
    assert ids[0] in protected_ids
    assert ids[0] not in deletable_ids


def test_execute_dry_run_deletes_nothing(client, admin_headers, developer_headers):
    _seed_versions(client, developer_headers, count=4)
    client.put(
        "/api/v1/retention/policy",
        headers=admin_headers,
        json={"keep_latest": 1, "keep_days": 0, "is_enabled": True, "dry_run": False, "schedule": "0 0 * * 0"},
    )
    resp = client.post(
        "/api/v1/retention/execute", headers=admin_headers, json={"dry_run": True, "confirm": False}
    )
    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 3
    assert client.get("/api/v1/bundles/", headers=admin_headers).json()["total"] == 4


def test_execute_requires_confirmation(client, admin_headers, developer_headers):
    _seed_versions(client, developer_headers, count=3)
    resp = client.post(
        "/api/v1/retention/execute", headers=admin_headers, json={"dry_run": False, "confirm": False}
    )
    assert resp.status_code == 400


def test_execute_deletes_and_records_run(client, admin_headers, developer_headers):
    _seed_versions(client, developer_headers, count=4)
    client.put(
        "/api/v1/retention/policy",
        headers=admin_headers,
        json={"keep_latest": 1, "keep_days": 0, "is_enabled": True, "dry_run": False, "schedule": "0 0 * * 0"},
    )
    resp = client.post(
        "/api/v1/retention/execute", headers=admin_headers, json={"dry_run": False, "confirm": True}
    )
    data = resp.json()
    assert data["deleted_count"] == 3
    assert data["freed_bytes"] > 0
    assert client.get("/api/v1/bundles/", headers=admin_headers).json()["total"] == 1

    runs = client.get("/api/v1/retention/runs", headers=admin_headers).json()
    assert runs["total"] == 1
    assert runs["items"][0]["deleted_count"] == 3


def test_deployed_bundle_protected(client, admin_headers, developer_headers):
    ids = _seed_versions(client, developer_headers, count=3)
    # simulate a successful deployment by direct DB manipulation
    from app.core.database import SessionLocal
    from app.models.models import Deployment, DeploymentStatus, NiFiServer

    db = SessionLocal()
    server = NiFiServer(
        name="dep-server", hostname="h", ssh_host="h", ssh_user="u", environment="DEV"
    )
    db.add(server)
    db.commit()
    db.add(
        Deployment(
            bundle_id=ids[0], server_id=server.id, status=DeploymentStatus.SUCCESS.value, deployed_by="admin"
        )
    )
    db.commit()
    db.close()

    client.put(
        "/api/v1/retention/policy",
        headers=admin_headers,
        json={"keep_latest": 0, "keep_days": 0, "is_enabled": True, "dry_run": False, "schedule": "0 0 * * 0"},
    )
    preview = client.post("/api/v1/retention/preview", headers=admin_headers).json()
    deletable = {c["bundle_id"] for c in preview["candidates"] if not c["protected"]}
    assert ids[0] not in deletable


def test_retention_requires_admin(client, developer_headers):
    assert client.post("/api/v1/retention/preview", headers=developer_headers).status_code == 403
