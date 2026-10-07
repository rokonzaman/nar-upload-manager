"""Application settings, notification configs and API token endpoints."""

from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import generate_api_token
from app.models.models import ApiToken, AuditAction, NotificationConfig, Setting, User
from app.schemas.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    Message,
    NotificationConfigCreate,
    NotificationConfigOut,
    SettingItem,
    SettingsUpdate,
)
from app.services import audit_service, notification_service

settings = get_settings()
router = APIRouter(prefix="/settings", tags=["settings"])

# Runtime-overridable settings with descriptions
_KNOWN_SETTINGS = {
    "ssh_timeout": "SSH connection timeout in seconds",
    "max_upload_size": "Maximum NAR upload size in bytes",
    "nar_directory": "Local NAR storage directory",
    "backup_directory": "Local backup directory",
    "retention_keep_latest": "Retention: keep latest N versions",
    "retention_keep_days": "Retention: keep versions newer than N days",
    "log_level": "Logging level (DEBUG, INFO, WARNING, ERROR)",
}


def _setting_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row and row.value is not None else default


@router.get("/")
def get_all_settings(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> dict:
    rows = {r.key: r for r in db.query(Setting).all()}
    items: List[SettingItem] = []
    defaults = {
        "ssh_timeout": str(settings.SSH_TIMEOUT),
        "max_upload_size": str(settings.MAX_UPLOAD_SIZE),
        "nar_directory": settings.NAR_DIRECTORY,
        "backup_directory": settings.BACKUP_DIRECTORY,
        "retention_keep_latest": str(settings.RETENTION_KEEP_LATEST),
        "retention_keep_days": str(settings.RETENTION_KEEP_DAYS),
        "log_level": settings.LOG_LEVEL,
    }
    for key, description in _KNOWN_SETTINGS.items():
        row = rows.get(key)
        items.append(
            SettingItem(
                key=key,
                value=row.value if row else defaults.get(key, ""),
                description=(row.description if row and row.description else description),
            )
        )
    return {
        "settings": items,
        "config": {
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "debug": settings.DEBUG,
            "keycloak_enabled": settings.KEYCLOAK_ENABLED,
            "dev_mode": settings.AUTH_DEV_MODE,
            "allowed_extensions": settings.allowed_extensions_list,
            "environments": settings.environments_list,
            "retention_enabled": settings.RETENTION_ENABLED,
            "retention_schedule": settings.RETENTION_SCHEDULE,
        },
    }


@router.put("/")
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    for key, value in payload.values.items():
        if key not in _KNOWN_SETTINGS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown setting '{key}'. Allowed: {sorted(_KNOWN_SETTINGS)}",
            )
        row = db.query(Setting).filter(Setting.key == key).first()
        if row is None:
            row = Setting(key=key, value=value, description=_KNOWN_SETTINGS[key])
            db.add(row)
        else:
            row.value = value
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="settings",
        details=f"Updated settings: {sorted(payload.values)}",
    )
    return {"updated": sorted(payload.values)}


# ---------------------------------------------------------------------------
# Notification configs
# ---------------------------------------------------------------------------
@router.get("/notifications", response_model=List[NotificationConfigOut])
def list_notifications(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> List[NotificationConfigOut]:
    rows = db.query(NotificationConfig).order_by(NotificationConfig.name).all()
    return [NotificationConfigOut.model_validate(r) for r in rows]


@router.post("/notifications", response_model=NotificationConfigOut, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NotificationConfigOut:
    valid_types = {"email", "slack", "teams", "webhook"}
    if payload.type not in valid_types:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(valid_types)}")
    if db.query(NotificationConfig).filter(NotificationConfig.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Notification config name already exists")
    config = NotificationConfig(
        name=payload.name,
        type=payload.type,
        target=payload.target,
        events=",".join(payload.events),
        is_enabled=payload.is_enabled,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="notification",
        resource_id=config.id, details=f"Created notification {config.name} ({config.type})",
    )
    return NotificationConfigOut.model_validate(config)


@router.put("/notifications/{config_id}", response_model=NotificationConfigOut)
def update_notification(
    config_id: int,
    payload: NotificationConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NotificationConfigOut:
    config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="Notification config not found")
    config.name = payload.name
    config.type = payload.type
    config.target = payload.target
    config.events = ",".join(payload.events)
    config.is_enabled = payload.is_enabled
    db.commit()
    db.refresh(config)
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="notification",
        resource_id=config.id, details=f"Updated notification {config.name}",
    )
    return NotificationConfigOut.model_validate(config)


@router.delete("/notifications/{config_id}", response_model=Message)
def delete_notification(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="Notification config not found")
    db.delete(config)
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.CONFIG_CHANGE, resource_type="notification",
        resource_id=config_id, details=f"Deleted notification {config.name}",
    )
    return Message(message="Notification config deleted")


@router.post("/notifications/{config_id}/test", response_model=Message)
def test_notification(
    config_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Message:
    config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="Notification config not found")
    try:
        notification_service.dispatch(
            config,
            "test",
            "Test notification",
            f"This is a test notification from {settings.APP_NAME}.",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Notification failed: {exc}")
    return Message(message="Test notification sent")


@router.get("/notifications/events/list")
def notification_events(_: User = Depends(require_admin)) -> List[str]:
    return notification_service.ALL_EVENTS


# ---------------------------------------------------------------------------
# API tokens (CI/CD)
# ---------------------------------------------------------------------------
@router.get("/api-tokens", response_model=List[ApiTokenOut])
def list_tokens(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> List[ApiTokenOut]:
    return [ApiTokenOut.model_validate(t) for t in db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()]


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: ApiTokenCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ApiTokenCreated:
    if payload.role not in {"admin", "developer", "viewer"}:
        raise HTTPException(status_code=400, detail="role must be admin, developer or viewer")
    if db.query(ApiToken).filter(ApiToken.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Token name already exists")
    plain, prefix, token_hash = generate_api_token()
    expires_at = (
        datetime.utcnow() + timedelta(days=payload.expires_days) if payload.expires_days else None
    )
    record = ApiToken(
        name=payload.name,
        prefix=prefix,
        token_hash=token_hash,
        role=payload.role,
        created_by=admin.username,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    audit_service.log_action(
        db, request, admin, AuditAction.TOKEN_CREATE, resource_type="api_token",
        resource_id=record.id, details=f"Created API token '{record.name}' role={record.role}",
    )
    return ApiTokenCreated(**ApiTokenOut.model_validate(record).model_dump(), token=plain)


@router.delete("/api-tokens/{token_id}", response_model=Message)
def revoke_token(
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    record = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Token not found")
    record.is_active = False
    db.commit()
    audit_service.log_action(
        db, request, admin, AuditAction.TOKEN_DELETE, resource_type="api_token",
        resource_id=record.id, details=f"Revoked API token '{record.name}'",
    )
    return Message(message="Token revoked")
