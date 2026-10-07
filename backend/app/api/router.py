"""Aggregated API router."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.api.endpoints import (
    audit,
    auth,
    backups,
    bundles,
    dashboard,
    deployments,
    nexus,
    retention,
    server_groups,
    servers,
    settings as settings_endpoint,
)

settings = get_settings()

api_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_router.include_router(auth.router)
api_router.include_router(servers.router)
api_router.include_router(server_groups.router)
api_router.include_router(bundles.router)
api_router.include_router(deployments.router)
api_router.include_router(backups.router)
api_router.include_router(nexus.router)
api_router.include_router(retention.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings_endpoint.router)
