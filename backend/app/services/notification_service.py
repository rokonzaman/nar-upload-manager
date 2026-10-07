"""Notification dispatch: email, Slack, Microsoft Teams, generic webhook."""

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import NotificationConfig, NotificationType

settings = get_settings()
logger = logging.getLogger(__name__)

EVENT_UPLOAD_COMPLETED = "upload_completed"
EVENT_DEPLOYMENT_COMPLETED = "deployment_completed"
EVENT_DEPLOYMENT_FAILED = "deployment_failed"
EVENT_ROLLBACK_COMPLETED = "rollback_completed"
EVENT_CLEANUP_COMPLETED = "cleanup_completed"
EVENT_NEXUS_SYNC_COMPLETED = "nexus_sync_completed"

ALL_EVENTS = [
    EVENT_UPLOAD_COMPLETED,
    EVENT_DEPLOYMENT_COMPLETED,
    EVENT_DEPLOYMENT_FAILED,
    EVENT_ROLLBACK_COMPLETED,
    EVENT_CLEANUP_COMPLETED,
    EVENT_NEXUS_SYNC_COMPLETED,
]


def _send_slack(target: str, title: str, message: str) -> None:
    resp = httpx.post(target, json={"text": f"*{title}*\n{message}"}, timeout=10)
    resp.raise_for_status()


def _send_teams(target: str, title: str, message: str) -> None:
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": title,
        "sections": [{"activityTitle": title, "text": message}],
    }
    resp = httpx.post(target, json=payload, timeout=10)
    resp.raise_for_status()


def _send_webhook(target: str, event: str, title: str, message: str, details: Optional[str]) -> None:
    payload = {"event": event, "title": title, "message": message, "details": details}
    resp = httpx.post(target, json=payload, timeout=10)
    resp.raise_for_status()


def _send_email(target: str, title: str, message: str) -> None:
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP not configured (SMTP_HOST empty)")
    msg = EmailMessage()
    msg["Subject"] = f"[{settings.APP_NAME}] {title}"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = target
    msg.set_content(message)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


def dispatch(config: NotificationConfig, event: str, title: str, message: str, details: Optional[str] = None) -> None:
    """Send one notification; raises on failure."""
    if config.type == NotificationType.SLACK.value:
        _send_slack(config.target, title, message)
    elif config.type == NotificationType.TEAMS.value:
        _send_teams(config.target, title, message)
    elif config.type == NotificationType.EMAIL.value:
        _send_email(config.target, title, message)
    else:
        _send_webhook(config.target, event, title, message, details)


def notify(db: Session, event: str, title: str, message: str, details: Optional[str] = None) -> None:
    """Dispatch an event to all enabled configs subscribed to it. Never raises."""
    try:
        configs = db.query(NotificationConfig).filter(NotificationConfig.is_enabled.is_(True)).all()
        for config in configs:
            subscribed = [e.strip() for e in (config.events or "").split(",") if e.strip()]
            if subscribed and event not in subscribed:
                continue
            try:
                dispatch(config, event, title, message, details)
                logger.info("notification sent event=%s target=%s", event, config.name)
            except Exception as exc:  # noqa: BLE001 - notifications must not break flows
                logger.warning("notification failed config=%s error=%s", config.name, exc)
    except Exception:  # noqa: BLE001
        logger.exception("notification dispatch failed")
