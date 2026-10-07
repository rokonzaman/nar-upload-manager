"""Server group (NiFi cluster) and group deployment tests."""

from tests.conftest import create_server, upload_nar


def _make_cluster(client, admin_headers, enabled=(True, True, True)):
    """Create 3 nodes and a cluster group; return (group, nodes)."""
    nodes = [
        create_server(client, admin_headers, name=f"node-{i}", enabled=enabled[i - 1])
        for i in (1, 2, 3)
    ]
    resp = client.post(
        "/api/v1/server-groups/",
        headers=admin_headers,
        json={
            "name": "prod-cluster",
            "description": "3-node cluster",
            "environment": "PROD",
            "server_ids": [n["id"] for n in nodes],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), nodes


def test_create_group_with_three_nodes(client, admin_headers):
    group, nodes = _make_cluster(client, admin_headers)
    assert group["name"] == "prod-cluster"
    assert group["environment"] == "PROD"
    assert group["server_count"] == 3
    assert {s["name"] for s in group["servers"]} == {"node-1", "node-2", "node-3"}


def test_duplicate_group_name(client, admin_headers):
    _make_cluster(client, admin_headers)
    resp = client.post(
        "/api/v1/server-groups/", headers=admin_headers, json={"name": "prod-cluster"}
    )
    assert resp.status_code == 409


def test_group_with_unknown_server_rejected(client, admin_headers):
    resp = client.post(
        "/api/v1/server-groups/",
        headers=admin_headers,
        json={"name": "bad", "server_ids": [9999]},
    )
    assert resp.status_code == 404


def test_list_and_get_group(client, admin_headers, viewer_headers):
    group, _ = _make_cluster(client, admin_headers)
    groups = client.get("/api/v1/server-groups/", headers=viewer_headers).json()
    assert len(groups) == 1
    detail = client.get(f"/api/v1/server-groups/{group['id']}", headers=viewer_headers).json()
    assert detail["server_count"] == 3


def test_update_group_members(client, admin_headers):
    group, nodes = _make_cluster(client, admin_headers)
    resp = client.put(
        f"/api/v1/server-groups/{group['id']}",
        headers=admin_headers,
        json={"server_ids": [nodes[0]["id"], nodes[1]["id"]]},
    )
    assert resp.status_code == 200
    assert resp.json()["server_count"] == 2


def test_delete_group_keeps_servers(client, admin_headers):
    group, nodes = _make_cluster(client, admin_headers)
    assert client.delete(f"/api/v1/server-groups/{group['id']}", headers=admin_headers).status_code == 200
    # nodes still exist
    assert client.get(f"/api/v1/servers/{nodes[0]['id']}", headers=admin_headers).status_code == 200


def test_group_management_requires_admin(client, developer_headers, viewer_headers):
    assert client.post("/api/v1/server-groups/", headers=viewer_headers, json={"name": "x"}).status_code == 403
    assert client.post("/api/v1/server-groups/", headers=developer_headers, json={"name": "x"}).status_code == 403


def test_deploy_to_group_creates_one_deployment_per_node(client, admin_headers, developer_headers):
    group, nodes = _make_cluster(client, admin_headers, enabled=(False, False, False))
    bundle = upload_nar(client, developer_headers).json()[0]["bundle"]
    resp = client.post(
        f"/api/v1/server-groups/{group['id']}/deploy",
        headers=developer_headers,
        json={"bundle_id": bundle["id"]},
    )
    assert resp.status_code == 201, resp.text
    deployments = resp.json()
    assert len(deployments) == 3
    assert {d["server_id"] for d in deployments} == {n["id"] for n in nodes}


def test_group_deploy_mixed_node_states(client, admin_headers, developer_headers):
    """Enabled node dry-runs OK; disabled nodes fail independently."""
    group, nodes = _make_cluster(client, admin_headers, enabled=(True, False, False))
    bundle = upload_nar(client, developer_headers).json()[0]["bundle"]
    resp = client.post(
        f"/api/v1/server-groups/{group['id']}/deploy",
        headers=developer_headers,
        json={"bundle_id": bundle["id"], "dry_run": True},
    )
    deployments = client.get(
        f"/api/v1/deployments/?bundle_id={bundle['id']}", headers=developer_headers
    ).json()["items"]
    by_server = {d["server_id"]: d for d in deployments}
    assert by_server[nodes[0]["id"]]["status"] == "success"
    assert by_server[nodes[1]["id"]]["status"] == "failed"
    assert by_server[nodes[2]["id"]]["status"] == "failed"


def test_deploy_to_empty_group_rejected(client, admin_headers, developer_headers):
    resp = client.post("/api/v1/server-groups/", headers=admin_headers, json={"name": "empty"})
    group_id = resp.json()["id"]
    bundle = upload_nar(client, developer_headers).json()[0]["bundle"]
    resp = client.post(
        f"/api/v1/server-groups/{group_id}/deploy",
        headers=developer_headers,
        json={"bundle_id": bundle["id"]},
    )
    assert resp.status_code == 400


def test_group_deploy_unknown_bundle(client, admin_headers, developer_headers):
    group, _ = _make_cluster(client, admin_headers)
    resp = client.post(
        f"/api/v1/server-groups/{group['id']}/deploy",
        headers=developer_headers,
        json={"bundle_id": 9999},
    )
    assert resp.status_code == 404


def test_group_deploy_viewer_forbidden(client, admin_headers, viewer_headers):
    group, _ = _make_cluster(client, admin_headers)
    resp = client.post(
        f"/api/v1/server-groups/{group['id']}/deploy",
        headers=viewer_headers,
        json={"bundle_id": 1},
    )
    assert resp.status_code == 403
