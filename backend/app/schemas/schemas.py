"""Pydantic v2 request/response schemas — the REST API contract."""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


class Message(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Auth / Users
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool
    deploy_environments: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class KeycloakLoginResponse(BaseModel):
    authorization_url: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=6)
    role: str = "viewer"
    email: Optional[str] = None
    full_name: Optional[str] = None
    deploy_environments: Optional[str] = None


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    deploy_environments: Optional[str] = None


# ---------------------------------------------------------------------------
# NiFi Servers
# ---------------------------------------------------------------------------
class NiFiServerBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    hostname: str
    ssh_host: str
    ssh_port: int = 22
    ssh_user: str
    ssh_key_path: Optional[str] = None
    ssh_password: Optional[str] = None  # write-only, stored encrypted
    nar_directory: str = "/opt/nifi/lib"
    backup_directory: str = "/opt/nifi/nar-backup"
    nifi_install_directory: str = "/opt/nifi"
    restart_command: str = "sudo docker compose -f /opt/nifi/docker-compose.yml restart"
    nifi_api_url: Optional[str] = None
    environment: str = "DEV"
    is_enabled: bool = True
    description: Optional[str] = None

    @field_validator("environment")
    @classmethod
    def env_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("ssh_port")
    @classmethod
    def valid_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Invalid SSH port")
        return v


class NiFiServerCreate(NiFiServerBase):
    pass


class NiFiServerUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    ssh_key_path: Optional[str] = None
    ssh_password: Optional[str] = None
    nar_directory: Optional[str] = None
    backup_directory: Optional[str] = None
    nifi_install_directory: Optional[str] = None
    restart_command: Optional[str] = None
    nifi_api_url: Optional[str] = None
    environment: Optional[str] = None
    is_enabled: Optional[bool] = None
    description: Optional[str] = None


class NiFiServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hostname: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_key_path: Optional[str] = None
    has_ssh_password: bool = False
    nar_directory: str
    backup_directory: str
    nifi_install_directory: str
    restart_command: str
    nifi_api_url: Optional[str] = None
    environment: str
    is_enabled: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ServerTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None
    nifi_version: Optional[str] = None


class ServerHealth(BaseModel):
    server_id: int
    reachable: bool
    disk_total_bytes: Optional[int] = None
    disk_used_bytes: Optional[int] = None
    disk_free_bytes: Optional[int] = None
    disk_used_percent: Optional[float] = None
    nar_dir_size_bytes: Optional[int] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    nifi_status: Optional[str] = None  # running | stopped | unknown
    nifi_version: Optional[str] = None
    uptime_seconds: Optional[int] = None
    warnings: List[str] = []
    checked_at: datetime


# ---------------------------------------------------------------------------
# Server Groups (NiFi clusters)
# ---------------------------------------------------------------------------
class ServerGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    environment: str = "PROD"
    server_ids: List[int] = []

    @field_validator("environment")
    @classmethod
    def env_upper(cls, v: str) -> str:
        return v.upper()


class ServerGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    server_ids: Optional[List[int]] = None


class ServerGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    environment: str
    created_at: datetime
    servers: List["NiFiServerOut"] = []
    server_count: int = 0


class GroupDeployRequest(BaseModel):
    bundle_id: int
    backup: bool = True
    restart_nifi: bool = False
    dry_run: bool = False
    notes: Optional[str] = None
    target_directory: Optional[str] = None


# ---------------------------------------------------------------------------
# NAR Bundles (repository)
# ---------------------------------------------------------------------------
class NarBundleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bundle_group: str
    artifact: str
    version: str
    filename: str
    file_size: int
    sha256: str
    md5: str
    status: str
    is_pinned: bool
    tags: str = ""
    description: Optional[str] = None
    build_date: Optional[datetime] = None
    uploaded_by: str
    uploaded_at: datetime
    source: str


class BundleUpdate(BaseModel):
    artifact: Optional[str] = None
    tags: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    is_pinned: Optional[bool] = None


class BundleGroup(BaseModel):
    """Version tree node for the repository browser."""

    bundle_group: str
    artifact: str
    versions: List[NarBundleOut]
    latest_version: str
    total_size: int


class BulkIds(BaseModel):
    ids: List[int]


class BulkActionResult(BaseModel):
    succeeded: List[int] = []
    failed: Dict[int, str] = {}


class BundleCompareResult(BaseModel):
    bundle_a: NarBundleOut
    bundle_b: NarBundleOut
    same_group: bool
    same_artifact: bool
    same_checksum: bool
    size_diff_bytes: int
    manifest_diff: Dict[str, Any] = {}


class UploadResult(BaseModel):
    filename: str
    success: bool
    bundle: Optional[NarBundleOut] = None
    error: Optional[str] = None
    replaced: bool = False


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------
class DeploymentCreate(BaseModel):
    bundle_id: int
    server_ids: List[int] = Field(min_length=1)
    target_directory: Optional[str] = None  # defaults to server.nar_directory
    backup: bool = True
    restart_nifi: bool = False
    dry_run: bool = False
    notes: Optional[str] = None


class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bundle_id: int
    server_id: int
    status: str
    dry_run: bool
    backup_created: bool
    restart_nifi: bool
    checksum_verified: bool
    target_directory: Optional[str] = None
    deployed_path: Optional[str] = None
    backup_path: Optional[str] = None
    deployed_by: str
    notes: Optional[str] = None
    error_message: Optional[str] = None
    log: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    bundle: Optional[NarBundleOut] = None
    server: Optional[NiFiServerOut] = None


class CompatibilityWarning(BaseModel):
    level: str  # info | warning | error
    message: str


class CompatibilityReport(BaseModel):
    bundle_id: int
    server_id: int
    compatible: bool
    warnings: List[CompatibilityWarning] = []


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
class BackupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    server_id: Optional[int] = None
    deployment_id: Optional[int] = None
    filename: str
    original_path: str
    backup_path: str
    file_size: int
    sha256: Optional[str] = None
    bundle_artifact: Optional[str] = None
    bundle_version: Optional[str] = None
    created_by: str
    created_at: datetime
    restored_at: Optional[datetime] = None
    server_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Nexus
# ---------------------------------------------------------------------------
class NexusServerCreate(BaseModel):
    name: str
    url: str
    username: Optional[str] = None
    password: Optional[str] = None  # write-only, stored encrypted
    default_repository: Optional[str] = None
    is_enabled: bool = True
    sync_schedule: Optional[str] = None


class NexusServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    default_repository: Optional[str] = None
    is_enabled: Optional[bool] = None
    sync_schedule: Optional[str] = None


class NexusServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    username: Optional[str] = None
    has_password: bool = False
    default_repository: Optional[str] = None
    is_enabled: bool
    sync_schedule: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    created_at: datetime


class NexusArtifact(BaseModel):
    repository: str
    group: str
    artifact: str
    version: str
    download_url: str
    sha256: Optional[str] = None
    size: Optional[int] = None


class NexusDownloadRequest(BaseModel):
    server_id: int
    repository: str
    group: str
    artifact: str
    version: str
    download_url: str


class NexusSyncResult(BaseModel):
    server_id: int
    synced: int
    skipped: int
    errors: List[str] = []


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
class RetentionPolicyIn(BaseModel):
    keep_latest: int = Field(default=5, ge=0)
    keep_days: int = Field(default=90, ge=0)
    is_enabled: bool = True
    dry_run: bool = False
    schedule: str = "0 0 * * 0"


class RetentionPolicyOut(RetentionPolicyIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    last_run_at: Optional[datetime] = None
    updated_at: datetime


class RetentionCandidate(BaseModel):
    bundle_id: int
    bundle_group: str
    artifact: str
    version: str
    file_size: int
    uploaded_at: datetime
    reason: str
    protected: bool = False  # pinned or actively deployed


class RetentionPreview(BaseModel):
    candidates: List[RetentionCandidate]
    total_count: int
    total_size_bytes: int
    policy: RetentionPolicyIn


class RetentionExecuteRequest(BaseModel):
    dry_run: bool = True
    confirm: bool = False


class RetentionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    dry_run: bool
    triggered_by: str
    deleted_count: int
    freed_bytes: int
    report: Optional[str] = None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    username: str
    full_name: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    target_server: Optional[str] = None
    bundle: Optional[str] = None
    version: Optional[str] = None
    result: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[str] = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class DashboardStats(BaseModel):
    total_servers: int
    enabled_servers: int
    total_bundles: int
    active_versions: int
    storage_bytes: int
    total_deployments: int
    failed_deployments: int
    pending_cleanup: int
    total_backups: int
    backup_bytes: int


class ChartPoint(BaseModel):
    label: str
    value: float


class TimeSeriesPoint(BaseModel):
    date: str
    count: int = 0
    bytes: int = 0


class TopBundle(BaseModel):
    artifact: str
    bundle_group: str
    deployment_count: int


class DashboardCharts(BaseModel):
    uploads: List[TimeSeriesPoint]
    deployments: List[TimeSeriesPoint]
    storage_growth: List[TimeSeriesPoint]
    top_bundles: List[TopBundle]


# ---------------------------------------------------------------------------
# Settings / Notifications / API tokens
# ---------------------------------------------------------------------------
class SettingItem(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None


class SettingsUpdate(BaseModel):
    values: Dict[str, str]


class NotificationConfigCreate(BaseModel):
    name: str
    type: str  # email | slack | teams | webhook
    target: str
    events: List[str] = []
    is_enabled: bool = True


class NotificationConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    target: str
    events: str
    is_enabled: bool
    created_at: datetime


class ApiTokenCreate(BaseModel):
    name: str
    role: str = "developer"
    expires_days: Optional[int] = None


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    role: str
    created_by: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool


class ApiTokenCreated(ApiTokenOut):
    token: str  # plain token, shown exactly once


# ---------------------------------------------------------------------------
# Remote NAR repository management
# ---------------------------------------------------------------------------
class RemoteNarFile(BaseModel):
    filename: str
    size_bytes: int
    modified: Optional[str] = None


class RestartResult(BaseModel):
    success: bool
    message: str
    command: str
    exit_code: int
    stdout: str
    stderr: str


class GroupRestartNode(BaseModel):
    server_name: str
    server_id: int
    restart: RestartResult
    bootstrap_wait_seconds: float
    bootstrap_success: bool


class DeleteNarFilesRequest(BaseModel):
    filenames: List[str] = Field(min_length=1, description="One or more NAR filenames to delete")
