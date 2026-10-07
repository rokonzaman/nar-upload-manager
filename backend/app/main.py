"""FastAPI application factory."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.api.router import api_router

settings = get_settings()


def configure_logging() -> None:
    """Console + rotating file logging."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)
    try:
        file_handler = RotatingFileHandler(
            settings.log_path, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        root.warning("Cannot open log file %s; console logging only", settings.log_path)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Enterprise-grade Apache NiFi NAR Upload Manager: upload, version, "
            "deploy, back up and audit custom NiFi NAR bundles across environments."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        contact={"name": "Platform Engineering"},
        license_info={"name": "Proprietary"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logging.getLogger("app").exception("Unhandled error on %s %s", request.method, request.url)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health", tags=["health"])
    def health() -> dict:
        from datetime import datetime

        return {"status": "ok", "version": __version__, "timestamp": datetime.utcnow().isoformat()}

    app.include_router(api_router)

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()
        db = SessionLocal()
        try:
            # Ensure default admin + default retention policy exist
            from app.api.endpoints.auth import ensure_default_admin
            from app.services import retention_service

            ensure_default_admin(db)
            retention_service.get_policy(db)
        finally:
            db.close()
        if settings.SCHEDULER_ENABLED:
            from app.scheduler import start_scheduler

            start_scheduler()

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        from app.scheduler import shutdown_scheduler

        shutdown_scheduler()

    return app


app = create_app()
