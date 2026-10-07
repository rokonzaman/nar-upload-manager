"""Audit logging service — records every significant action."""

import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.deps import get_client_ip, get_user_agent
from app.models.models import AuditLog, AuditResult, User

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    request: Optional[Request],
    user: Optional[User],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    target_server: Optional[str] = None,
    bundle: Optional[str] = None,
    version: Optional[str] = None,
    result: str = AuditResult.SUCCESS.value,
    error_message: Optional[str] = None,
    details: Optional[str] = None,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> AuditLog:
    """Persist an audit log entry.

    `user` may be None for unauthenticated events (e.g. failed logins);
    in that case pass `username` explicitly.
    """
    entry = AuditLog(
        username=user.username if user else (username or "anonymous"),
        full_name=(user.full_name if user else None) or full_name,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        target_server=target_server,
        bundle=bundle,
        version=version,
        result=result,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
        error_message=error_message,
        details=details,
    )
    db.add(entry)
    db.commit()
    logger.info(
        "audit action=%s user=%s result=%s resource=%s/%s",
        action,
        entry.username,
        result,
        resource_type,
        resource_id,
    )
    return entry
