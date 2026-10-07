"""Shared FastAPI dependencies: DB session, authentication, RBAC."""

from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    decode_keycloak_token,
    decode_local_token,
    hash_api_token,
    role_from_keycloak_claims,
)
from app.models.models import ApiToken, User, UserRole

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False
)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def resolve_role(username: str, claims_role: str, existing_role: Optional[str], is_new: bool) -> str:
    """Decide a user's role.

    Priority:
    1. ``ADMIN_USERNAMES`` bootstrap list — always admin.
    2. Keycloak realm roles — only when ``KEYCLOAK_ROLE_SYNC_ENABLED`` is True.
    3. Otherwise roles are managed locally in the app: new SSO users get
       ``DEFAULT_USER_ROLE``, existing users keep their locally-assigned role.
    """
    if username in settings.admin_usernames_list:
        return UserRole.ADMIN.value
    if settings.KEYCLOAK_ROLE_SYNC_ENABLED:
        return claims_role
    if is_new:
        return settings.DEFAULT_USER_ROLE
    return existing_role or settings.DEFAULT_USER_ROLE


def _user_from_api_token(db: Session, token: str) -> Optional[User]:
    record = (
        db.query(ApiToken)
        .filter(ApiToken.token_hash == hash_api_token(token), ApiToken.is_active.is_(True))
        .first()
    )
    if record is None:
        return None
    if record.expires_at and record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        return None
    record.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    # Synthetic user scoped to the token's own role (never the creator's role)
    return User(
        username=f"token:{record.name}",
        full_name=f"API Token ({record.name})",
        role=record.role,
        is_active=True,
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> User:
    """Resolve the current user from a Bearer JWT, Keycloak token or API token."""
    # API token support (CI/CD)
    api_token = request.headers.get("X-API-Key")
    if api_token:
        user = _user_from_api_token(db, api_token)
        if user is None:
            raise _CREDENTIALS_EXCEPTION
        request.state.auth_method = "api_token"
        return user

    if not token:
        raise _CREDENTIALS_EXCEPTION

    username: Optional[str] = None
    role: str = UserRole.VIEWER.value
    full_name: Optional[str] = None
    email: Optional[str] = None

    # 1) Try locally-issued token
    try:
        payload = decode_local_token(token)
        username = payload.get("sub")
        role = payload.get("role", UserRole.VIEWER.value)
        request.state.auth_method = "local_jwt"
    except jwt.PyJWTError:
        # 2) Try Keycloak-issued token
        if not settings.KEYCLOAK_ENABLED:
            raise _CREDENTIALS_EXCEPTION
        try:
            claims = decode_keycloak_token(token)
        except Exception:
            raise _CREDENTIALS_EXCEPTION
        username = claims.get("preferred_username") or claims.get("sub")
        role = role_from_keycloak_claims(claims)
        full_name = claims.get("name")
        email = claims.get("email")
        request.state.auth_method = "keycloak"

    if not username:
        raise _CREDENTIALS_EXCEPTION

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        # Auto-provision on first login (Keycloak SSO)
        user = User(
            username=username,
            email=email,
            full_name=full_name or username,
            role=resolve_role(username, role, None, is_new=True),
            is_active=True,
            last_login=datetime.utcnow(),
        )
        db.add(user)
    else:
        user.last_login = datetime.utcnow()
        if request.state.auth_method == "keycloak":
            # Role: locally managed unless KEYCLOAK_ROLE_SYNC_ENABLED
            user.role = resolve_role(username, role, user.role, is_new=False)
            if email:
                user.email = email
            if full_name:
                user.full_name = full_name
    db.commit()
    db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    return user


def require_role(*roles: UserRole):
    """RBAC dependency factory. Usage: Depends(require_role(UserRole.ADMIN))"""

    allowed = {r.value for r in roles}

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {sorted(allowed)}",
            )
        return current_user

    return checker


# Convenience role dependencies
require_admin = require_role(UserRole.ADMIN)
require_developer = require_role(UserRole.ADMIN, UserRole.DEVELOPER)
require_viewer = require_role(UserRole.ADMIN, UserRole.DEVELOPER, UserRole.VIEWER)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str:
    return request.headers.get("User-Agent", "unknown")
