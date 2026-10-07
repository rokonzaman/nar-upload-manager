"""Security helpers: JWT (local + Keycloak), password hashing, secret encryption."""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
import jwt
from cryptography.fernet import Fernet

from app.core.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, stdlib only)
# ---------------------------------------------------------------------------
_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        _, iterations, salt, expected = hashed.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Local JWT (dev mode / service tokens)
# ---------------------------------------------------------------------------

def create_access_token(
    subject: str,
    role: str,
    extra: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": settings.APP_NAME,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_local_token(token: str) -> Dict[str, Any]:
    """Decode a locally-issued JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Keycloak OIDC (RS256 via JWKS)
# ---------------------------------------------------------------------------
_jwks_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL = 300


def _fetch_jwks() -> Dict[str, Any]:
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL:
        return _jwks_cache["keys"]
    url = f"{settings.keycloak_oidc_base}/certs"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    _jwks_cache["keys"] = resp.json()
    _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def decode_keycloak_token(token: str) -> Dict[str, Any]:
    """Validate a Keycloak-issued access token against the realm JWKS."""
    jwks = _fetch_jwks()
    unverified_header = jwt.get_unverified_header(token)
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == unverified_header.get("kid")), None)
    if key_data is None:
        _jwks_cache["keys"] = None  # force refresh once
        jwks = _fetch_jwks()
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == unverified_header.get("kid")), None)
    if key_data is None:
        raise jwt.InvalidTokenError("Unknown signing key")
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        options={"verify_aud": False},
        issuer=f"{settings.KEYCLOAK_SERVER_URL.rstrip('/')}/realms/{settings.KEYCLOAK_REALM}",
        leeway=120,
    )


def role_from_keycloak_claims(claims: Dict[str, Any]) -> str:
    """Map Keycloak realm roles to application roles."""
    realm_roles = set((claims.get("realm_access") or {}).get("roles") or [])
    if "nar-admin" in realm_roles:
        return "admin"
    if "nar-developer" in realm_roles:
        return "developer"
    return "viewer"


def keycloak_authorization_url(redirect_uri: str, state: str) -> str:
    return (
        f"{settings.keycloak_oidc_base}/auth"
        f"?client_id={settings.KEYCLOAK_CLIENT_ID}"
        f"&response_type=code&scope=openid%20profile%20email"
        f"&redirect_uri={redirect_uri}&state={state}"
    )


def exchange_keycloak_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    resp = httpx.post(
        f"{settings.keycloak_oidc_base}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Secret encryption at rest (Fernet, key derived from SECRET_KEY)
# ---------------------------------------------------------------------------

def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


# ---------------------------------------------------------------------------
# API tokens (CI/CD integration)
# ---------------------------------------------------------------------------

def generate_api_token() -> tuple[str, str, str]:
    """Return (plain_token, prefix, sha256_hash). Store only the hash."""
    token = f"nrm_{secrets.token_urlsafe(32)}"
    return token, token[:12], hashlib.sha256(token.encode()).hexdigest()


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
