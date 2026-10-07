"""NAR bundle repository tests."""

from tests.conftest import make_nar_bytes, upload_nar


def test_upload_extracts_metadata(client, developer_headers):
    resp = upload_nar(client, developer_headers, artifact="nifi-cool-nar", version="2.1.0")
    assert resp.status_code == 200
    result = resp.json()[0]
    assert result["success"] is True
    bundle = result["bundle"]
    assert bundle["artifact"] == "nifi-cool-nar"
    assert bundle["version"] == "2.1.0"
    assert bundle["bundle_group"] == "org.apache.nifi"
    assert len(bundle["sha256"]) == 64
    assert len(bundle["md5"]) == 32
    assert bundle["file_size"] > 0


def test_upload_rejects_bad_extension(client, developer_headers):
    resp = client.post(
        "/api/v1/bundles/upload",
        headers=developer_headers,
        files=[("files", ("evil.txt", b"not-a-nar", "text/plain"))],
    )
    assert resp.status_code == 200
    assert resp.json()[0]["success"] is False
    assert "Invalid file type" in resp.json()[0]["error"]


def test_upload_rejects_path_traversal_filename(client, developer_headers):
    content = make_nar_bytes()
    resp = client.post(
        "/api/v1/bundles/upload",
        headers=developer_headers,
        files=[("files", ("../../etc/passwd.nar", content, "application/octet-stream"))],
    )
    assert resp.status_code == 200
    result = resp.json()[0]
    # sanitized to a plain basename, upload succeeds into the managed directory
    if result["success"]:
        assert "/" not in result["bundle"]["filename"]
        assert ".." not in result["bundle"]["filename"]


def test_duplicate_upload_conflict(client, developer_headers):
    assert upload_nar(client, developer_headers).json()[0]["success"] is True
    resp = upload_nar(client, developer_headers)
    assert resp.json()[0]["success"] is False
    assert "already exists" in resp.json()[0]["error"]


def test_replace_existing_version(client, developer_headers):
    assert upload_nar(client, developer_headers).json()[0]["success"] is True
    resp = upload_nar(client, developer_headers, replace=True)
    result = resp.json()[0]
    assert result["success"] is True
    assert result["replaced"] is True
    # still only one version registered
    listing = client.get("/api/v1/bundles/", headers=developer_headers).json()
    assert listing["total"] == 1


def test_grouped_listing(client, developer_headers):
    upload_nar(client, developer_headers, artifact="nifi-a-nar", version="1.0.0")
    upload_nar(client, developer_headers, artifact="nifi-a-nar", version="1.1.0")
    upload_nar(client, developer_headers, artifact="nifi-b-nar", version="3.0.0")
    resp = client.get("/api/v1/bundles/grouped", headers=developer_headers)
    groups = resp.json()
    assert len(groups) == 2
    a = next(g for g in groups if g["artifact"] == "nifi-a-nar")
    assert [v["version"] for v in a["versions"]] == ["1.1.0", "1.0.0"]
    assert a["latest_version"] == "1.1.0"


def test_download_bundle(client, developer_headers, viewer_headers):
    bundle = upload_nar(client, developer_headers).json()[0]["bundle"]
    resp = client.get(f"/api/v1/bundles/{bundle['id']}/download", headers=viewer_headers)
    assert resp.status_code == 200
    assert resp.headers["X-SHA256"] == bundle["sha256"]
    assert len(resp.content) == bundle["file_size"]


def test_pinned_bundle_cannot_be_deleted(client, developer_headers, admin_headers):
    bundle = upload_nar(client, developer_headers).json()[0]["bundle"]
    client.put(f"/api/v1/bundles/{bundle['id']}", headers=developer_headers, json={"is_pinned": True})
    resp = client.delete(f"/api/v1/bundles/{bundle['id']}", headers=developer_headers)
    assert resp.status_code == 409


def test_delete_bundle(client, developer_headers):
    bundle = upload_nar(client, developer_headers).json()[0]["bundle"]
    assert client.delete(f"/api/v1/bundles/{bundle['id']}", headers=developer_headers).status_code == 200
    assert client.get(f"/api/v1/bundles/{bundle['id']}", headers=developer_headers).status_code == 404


def test_bulk_delete(client, developer_headers):
    b1 = upload_nar(client, developer_headers, version="1.0.0").json()[0]["bundle"]
    b2 = upload_nar(client, developer_headers, version="2.0.0").json()[0]["bundle"]
    resp = client.post(
        "/api/v1/bundles/bulk-delete", headers=developer_headers, json={"ids": [b1["id"], b2["id"], 9999]}
    )
    data = resp.json()
    assert set(data["succeeded"]) == {b1["id"], b2["id"]}
    assert "9999" in data["failed"] or 9999 in data["failed"]


def test_compare_bundles(client, developer_headers):
    b1 = upload_nar(client, developer_headers, version="1.0.0").json()[0]["bundle"]
    b2 = upload_nar(client, developer_headers, version="2.0.0").json()[0]["bundle"]
    resp = client.post(
        "/api/v1/bundles/compare", headers=developer_headers, json={"id_a": b1["id"], "id_b": b2["id"]}
    )
    data = resp.json()
    assert data["same_artifact"] is True
    assert data["same_checksum"] is False
    assert "Nar-Version" in data["manifest_diff"]["changed"]


def test_search_and_sort(client, developer_headers):
    upload_nar(client, developer_headers, artifact="nifi-apple-nar", version="1.0.0")
    upload_nar(client, developer_headers, artifact="nifi-banana-nar", version="1.0.0")
    resp = client.get("/api/v1/bundles/?q=apple", headers=developer_headers)
    assert resp.json()["total"] == 1
    resp = client.get(
        "/api/v1/bundles/?sort_by=artifact&sort_order=desc", headers=developer_headers
    )
    artifacts = [i["artifact"] for i in resp.json()["items"]]
    assert artifacts == sorted(artifacts, reverse=True)
