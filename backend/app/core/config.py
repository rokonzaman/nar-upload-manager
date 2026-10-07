"""Application configuration.

All settings are driven by environment variables (see .env.example).
No code changes are required to reconfigure the application.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    APP_NAME: str = "NiFi NAR Manager"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite:///./nar_manager.db"

    # Auth / JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    JWT_ALGORITHM: str = "HS256"
    # Dev mode enables local username/password login so the app runs
    # out-of-the-box without Keycloak. Disable in production.
    AUTH_DEV_MODE: bool = True
    AUTH_RATE_LIMIT_PER_MINUTE: int = 20

    # Keycloak OIDC
    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_SERVER_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "nar-manager"
    KEYCLOAK_CLIENT_ID: str = "nar-manager-frontend"
    KEYCLOAK_CLIENT_SECRET: str = "change-me"
    KEYCLOAK_ADMIN_USERNAME: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = "admin"
    # Role management: when False (default), Keycloak handles authentication only
    # and roles are managed locally in the app (Settings → Users). When True,
    # roles are synced from Keycloak realm roles on every login.
    KEYCLOAK_ROLE_SYNC_ENABLED: bool = False
    # Role assigned to auto-provisioned SSO users (when sync is disabled)
    DEFAULT_USER_ROLE: str = "viewer"
    # Comma-separated usernames that always receive admin at login (bootstrap)
    ADMIN_USERNAMES: str = "admin"

    # NAR storage
    NAR_DIRECTORY: str = "./nar_files"
    BACKUP_DIRECTORY: str = "./backup"
    MAX_UPLOAD_SIZE: int = 1073741824  # 1 GiB
    ALLOWED_EXTENSIONS: str = ".nar"

    # SSH
    SSH_TIMEOUT: int = 30

    # Nexus integration (defaults; servers are managed in DB)
    NEXUS_URL: str = "http://localhost:8081"
    NEXUS_USERNAME: str = "admin"
    NEXUS_PASSWORD: str = "admin123"
    NEXUS_REPOSITORY: str = "nar-releases"

    # Retention policy
    RETENTION_ENABLED: bool = True
    RETENTION_KEEP_LATEST: int = 5
    RETENTION_KEEP_DAYS: int = 90
    RETENTION_DRY_RUN: bool = False
    RETENTION_SCHEDULE: str = "0 0 * * 0"  # cron, weekly Sunday midnight

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/nar-manager.log"

    # NiFi integration (defaults; per-server config lives in DB)
    NIFI_URL: str = "http://localhost:8443"
    NIFI_API_URL: str = "http://localhost:8443/nifi-api"
    NIFI_USERNAME: str = "admin"
    NIFI_PASSWORD: str = "admin123"
    NIFI_ENABLED: bool = False

    # Multi-server environments
    ENVIRONMENTS: str = "DEV,QA,PROD"

    # Scheduler
    SCHEDULER_ENABLED: bool = True

    # Notifications (SMTP; webhooks are managed in DB)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "nar-manager@localhost"
    SMTP_TLS: bool = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()]

    @property
    def environments_list(self) -> List[str]:
        return [e.strip().upper() for e in self.ENVIRONMENTS.split(",") if e.strip()]

    @property
    def admin_usernames_list(self) -> List[str]:
        return [u.strip() for u in self.ADMIN_USERNAMES.split(",") if u.strip()]

    @property
    def nar_dir(self) -> Path:
        p = Path(self.NAR_DIRECTORY)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def backup_dir(self) -> Path:
        p = Path(self.BACKUP_DIRECTORY)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_path(self) -> Path:
        p = Path(self.LOG_FILE)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def keycloak_oidc_base(self) -> str:
        return f"{self.KEYCLOAK_SERVER_URL.rstrip('/')}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect"


@lru_cache
def get_settings() -> Settings:
    return Settings()
