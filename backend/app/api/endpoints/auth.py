"""Authentication endpoints: local dev login, Keycloak OIDC, user management."""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_admin, resolve_role
from app.core.security import (
    create_access_token,
    decode_keycloak_token,
    exchange_keycloak_code,
    hash_password,
    keycloak_authorization_url,
    role_from_keycloak_claims,
    verify_password,
)
from app.models.models import AuditAction, AuditResult, User
from app.schemas.schemas import (
    KeycloakLoginResponse,
    LoginRequest,
    Message,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import audit_service

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

# Simple in-memory sliding-window rate limiter for login attempts
_attempts: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    window = 60.0
    with _lock:
        dq = _attempts[ip]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= settings.AUTH_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
            )
        dq.append(now)


@router.get("/config")
def auth_config() -> dict:
    """Public auth configuration for the frontend."""
    return {
        "dev_mode": settings.AUTH_DEV_MODE,
        "keycloak_enabled": settings.KEYCLOAK_ENABLED,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    """Dev-mode local login (disable AUTH_DEV_MODE in production)."""
    if not settings.AUTH_DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local login disabled. Use Keycloak SSO.",
        )
    from app.core.deps import get_client_ip

    _check_rate_limit(get_client_ip(request))

    user = db.query(User).filter(User.username == payload.username).first()
    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
    ):
        audit_service.log_action(
            db,
            request,
            None,
            AuditAction.LOGIN,
            resource_type="auth",
            result=AuditResult.FAILURE.value,
            error_message="Invalid credentials",
            username=payload.username,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")

    from datetime import datetime

    user.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token(user.username, user.role, {"name": user.full_name})
    audit_service.log_action(db, request, user, AuditAction.LOGIN, resource_type="auth")
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/keycloak/login", response_model=KeycloakLoginResponse)
def keycloak_login(redirect_uri: str = Query(...)) -> KeycloakLoginResponse:
    if not settings.KEYCLOAK_ENABLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keycloak is not enabled")
    import secrets

    return KeycloakLoginResponse(
        authorization_url=keycloak_authorization_url(redirect_uri, secrets.token_urlsafe(16))
    )


class KeycloakCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/keycloak/callback", response_model=TokenResponse)
def keycloak_callback(
    payload: KeycloakCallbackRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    if not settings.KEYCLOAK_ENABLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keycloak is not enabled")
    try:
        tokens = exchange_keycloak_code(payload.code, payload.redirect_uri)
        claims = decode_keycloak_token(tokens["access_token"])
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Code exchange failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")

    username = claims.get("preferred_username") or claims.get("sub")
    role = role_from_keycloak_claims(claims)
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            username=username,
            email=claims.get("email"),
            full_name=claims.get("name") or username,
            role=resolve_role(username, role, None, is_new=True),
            is_active=True,
        )
        db.add(user)
    else:
        # Role: locally managed unless KEYCLOAK_ROLE_SYNC_ENABLED
        user.role = resolve_role(username, role, user.role, is_new=False)
    from datetime import datetime

    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)

    token = create_access_token(user.username, user.role, {"name": user.full_name})
    audit_service.log_action(db, request, user, AuditAction.LOGIN, resource_type="auth", details="keycloak")
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.post("/logout", response_model=Message)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    audit_service.log_action(db, request, current_user, AuditAction.LOGOUT, resource_type="auth")
    return Message(message="Logged out")


@router.get("/users", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> List[UserOut]:
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.username).all()]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        email=payload.email,
        full_name=payload.full_name,
        deploy_environments=payload.deploy_environments,
        is_active=True,
    )
    if user.deploy_environments:
        envs = [e.strip().upper() for e in user.deploy_environments.split(",") if e.strip()]
        user.deploy_environments = ",".join(envs)
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="user",
        resource_id=user.id, details=f"Created user {user.username}",
    )
    return UserOut.model_validate(user)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.role is not None:
        valid = {"admin", "developer", "viewer"}
        if payload.role not in valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role must be one of {valid}")
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.deploy_environments is not None:
        if payload.deploy_environments.strip():
            envs = [e.strip().upper() for e in payload.deploy_environments.split(",") if e.strip()]
            user.deploy_environments = ",".join(envs)
        else:
            user.deploy_environments = None
    db.commit()
    db.refresh(user)
    audit_service.log_action(
        db,
        request,
        admin,
        AuditAction.CONFIG_CHANGE,
        resource_type="user",
        resource_id=user.id,
        details=f"Updated user {user.username}: role={user.role} active={user.is_active} deploy_envs={user.deploy_environments}",
    )
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}", response_model=Message)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    db.delete(user)
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="user",
        resource_id=user_id, details=f"Deleted user {user.username}",
    )
    return Message(message=f"User '{user.username}' deleted")


def ensure_default_admin(db: Session) -> None:
    """Create the initial admin user on first startup (dev mode only)."""
    if not settings.AUTH_DEV_MODE:
        return
    if db.query(User).count() == 0:
        db.add(
            User(
                username="admin",
                full_name="Administrator",
                role="admin",
                password_hash=hash_password("admin123"),
                is_active=True,
            )
        )
        db.commit()
