"""Role management with external Keycloak: roles are app-managed by default."""

import pytest

from app.core import deps


def _enable_keycloak(monkeypatch, claims: dict) -> None:
    """Simulate an external Keycloak validating bearer tokens."""
    monkeypatch.setattr(deps.settings, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(deps, "decode_keycloak_token", lambda token: claims)


def _sso_headers() -> dict:
    # Any string works — local decode fails, Keycloak decode is mocked
    return {"Authorization": "Bearer sso-token"}


def test_sso_user_provisioned_with_default_role(monkeypatch, client):
    """New SSO users get DEFAULT_USER_ROLE, ignoring Keycloak realm roles."""
    _enable_keycloak(
        monkeypatch,
        {
            "preferred_username": "sso-alice",
            "name": "Alice",
            "email": "alice@example.com",
            "realm_access": {"roles": ["nar-admin"]},  # ignored: sync disabled
        },
    )
    resp = client.get("/api/v1/auth/me", headers=_sso_headers())
    assert resp.status_code == 200
    assert resp.json()["username"] == "sso-alice"
    assert resp.json()["role"] == "viewer"


def test_local_role_change_persists_across_sso_logins(monkeypatch, client, admin_headers):
    """An admin-managed role is NOT overwritten on subsequent SSO logins."""
    _enable_keycloak(
        monkeypatch,
        {"preferred_username": "sso-bob", "realm_access": {"roles": ["nar-viewer"]}},
    )
    assert client.get("/api/v1/auth/me", headers=_sso_headers()).json()["role"] == "viewer"

    # Admin promotes bob to developer in the app
    users = client.get("/api/v1/auth/users", headers=admin_headers).json()
    bob = next(u for u in users if u["username"] == "sso-bob")
    resp = client.put(f"/api/v1/auth/users/{bob['id']}", headers=admin_headers, json={"role": "developer"})
    assert resp.status_code == 200

    # Second SSO login — role stays developer
    assert client.get("/api/v1/auth/me", headers=_sso_headers()).json()["role"] == "developer"


def test_admin_usernames_bootstrap(monkeypatch, client):
    """Usernames in ADMIN_USERNAMES always receive the admin role."""
    monkeypatch.setattr(deps.settings, "ADMIN_USERNAMES", "sso-carol, sso-dave")
    _enable_keycloak(monkeypatch, {"preferred_username": "sso-carol", "realm_access": {"roles": []}})
    assert client.get("/api/v1/auth/me", headers=_sso_headers()).json()["role"] == "admin"

    # And an existing user's role is upgraded to admin on next login
    _enable_keycloak(monkeypatch, {"preferred_username": "sso-dave", "realm_access": {"roles": []}})
    assert client.get("/api/v1/auth/me", headers=_sso_headers()).json()["role"] == "admin"


def test_keycloak_role_sync_opt_in(monkeypatch, client):
    """With KEYCLOAK_ROLE_SYNC_ENABLED=true, realm roles drive the app role."""
    monkeypatch.setattr(deps.settings, "KEYCLOAK_ROLE_SYNC_ENABLED", True)
    _enable_keycloak(
        monkeypatch,
        {"preferred_username": "sso-erin", "realm_access": {"roles": ["nar-developer"]}},
    )
    assert client.get("/api/v1/auth/me", headers=_sso_headers()).json()["role"] == "developer"

    # Role changes in Keycloak are picked up on next login
    _enable_keycloak(
        monkeypatch,
        {"preferred_username": "sso-erin", "realm_access": {"roles": ["nar-admin"]}},
    )
    assert client.get("/api/v1/auth/me", headers=_sso_headers()).json()["role"] == "admin"


def test_sso_profile_fields_updated(monkeypatch, client):
    """Email and full name still sync from the IdP even with local roles."""
    _enable_keycloak(
        monkeypatch,
        {"preferred_username": "sso-frank", "name": "Frank Miller", "email": "frank@example.com"},
    )
    me = client.get("/api/v1/auth/me", headers=_sso_headers()).json()
    assert me["email"] == "frank@example.com"
    assert me["full_name"] == "Frank Miller"
    assert me["role"] == "viewer"


@pytest.mark.parametrize("role", ["nar-admin", "nar-developer", "nar-viewer"])
def test_disabled_keycloak_rejects(monkeypatch, client, admin_headers, role):
    """Bearer tokens are rejected when Keycloak is disabled and token is not local."""
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-local-jwt"})
    assert resp.status_code == 401
