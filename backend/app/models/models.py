"""SQLAlchemy ORM models."""

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


server_group_members = Table(
    "server_group_members",
    Base.metadata,
    Column("group_id", ForeignKey("server_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("server_id", ForeignKey("nifi_servers.id", ondelete="CASCADE"), primary_key=True),
)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class BundleStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class AuditResult(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class NotificationType(str, enum.Enum):
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"


class AuditAction:
    """Canonical audit action names."""

    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    DELETE = "DELETE"
    RENAME = "RENAME"
    DEPLOY = "DEPLOY"
    ROLLBACK = "ROLLBACK"
    RESTART_NIFI = "RESTART_NIFI"
    RETENTION_CLEANUP = "RETENTION_CLEANUP"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    BACKUP_RESTORE = "BACKUP_RESTORE"
    NEXUS_SYNC = "NEXUS_SYNC"
    NEXUS_DOWNLOAD = "NEXUS_DOWNLOAD"
    NAR_DELETE = "NAR_DELETE"
    SERVER_CREATE = "SERVER_CREATE"
    SERVER_UPDATE = "SERVER_UPDATE"
    SERVER_DELETE = "SERVER_DELETE"
    TOKEN_CREATE = "TOKEN_CREATE"
    TOKEN_DELETE = "TOKEN_DELETE"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER.value)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deploy_environments: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class NiFiServer(Base):
    __tablename__ = "nifi_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    ssh_host: Mapped[str] = mapped_column(String(255))
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(100))
    ssh_key_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ssh_password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nar_directory: Mapped[str] = mapped_column(String(500), default="/opt/nifi/lib")
    backup_directory: Mapped[str] = mapped_column(String(500), default="/opt/nifi/nar-backup")
    nifi_install_directory: Mapped[str] = mapped_column(String(500), default="/opt/nifi")
    restart_command: Mapped[str] = mapped_column(String(500), default="sudo docker compose -f /opt/nifi/docker-compose.yml restart")
    nifi_api_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    environment: Mapped[str] = mapped_column(String(20), default="DEV", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deployments: Mapped[List["Deployment"]] = relationship(back_populates="server")
    backups: Mapped[List["Backup"]] = relationship(back_populates="server")
    groups: Mapped[List["ServerGroup"]] = relationship(
        secondary=server_group_members, back_populates="members"
    )


class ServerGroup(Base):
    """A named group of NiFi servers (e.g. a 3-node cluster) for group deployments."""

    __tablename__ = "server_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    environment: Mapped[str] = mapped_column(String(20), default="PROD", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[List["NiFiServer"]] = relationship(
        secondary=server_group_members, back_populates="groups"
    )


class NarBundle(Base):
    __tablename__ = "nar_bundles"
    __table_args__ = (
        UniqueConstraint("bundle_group", "artifact", "version", name="uq_bundle_gav"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_group: Mapped[str] = mapped_column(String(255), index=True)
    artifact: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000), unique=True)
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    md5: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default=BundleStatus.ACTIVE.value)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    build_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(150))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    source: Mapped[str] = mapped_column(String(20), default="local")  # local | nexus

    deployments: Mapped[List["Deployment"]] = relationship(back_populates="bundle")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("nar_bundles.id"), index=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("nifi_servers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=DeploymentStatus.PENDING.value, index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_created: Mapped[bool] = mapped_column(Boolean, default=False)
    restart_nifi: Mapped[bool] = mapped_column(Boolean, default=False)
    checksum_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    target_directory: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    deployed_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    backup_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    deployed_by: Mapped[str] = mapped_column(String(150))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    bundle: Mapped["NarBundle"] = relationship(back_populates="deployments")
    server: Mapped["NiFiServer"] = relationship(back_populates="deployments")


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[Optional[int]] = mapped_column(ForeignKey("nifi_servers.id"), nullable=True, index=True)
    deployment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deployments.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(500))
    original_path: Mapped[str] = mapped_column(String(1000))
    backup_path: Mapped[str] = mapped_column(String(1000), unique=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bundle_artifact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    bundle_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    server: Mapped[Optional["NiFiServer"]] = relationship(back_populates="backups")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    username: Mapped[str] = mapped_column(String(150), index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_server: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    bundle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    result: Mapped[str] = mapped_column(String(20), default=AuditResult.SUCCESS.value, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class NexusServer(Base):
    __tablename__ = "nexus_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    url: Mapped[str] = mapped_column(String(500))
    username: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_repository: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_schedule: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # cron
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, default="default")
    keep_latest: Mapped[int] = mapped_column(Integer, default=5)
    keep_days: Mapped[int] = mapped_column(Integer, default=90)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule: Mapped[str] = mapped_column(String(50), default="0 0 * * 0")
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RetentionRun(Base):
    __tablename__ = "retention_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_by: Mapped[str] = mapped_column(String(150), default="scheduler")
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    freed_bytes: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20), default=NotificationType.WEBHOOK.value)
    target: Mapped[str] = mapped_column(String(1000))  # webhook URL or email address
    events: Mapped[str] = mapped_column(String(500), default="")  # comma separated
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    prefix: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.DEVELOPER.value)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
