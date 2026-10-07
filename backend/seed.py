"""Seed the database with demo data. Idempotent — safe to run multiple times.

Usage: python seed.py
"""

import hashlib
import io
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models.models import (
    AuditLog,
    NarBundle,
    NiFiServer,
    RetentionPolicy,
    Setting,
    User,
)
from app.services import retention_service

settings = get_settings()


def make_nar_bytes(group: str, artifact: str, version: str) -> bytes:
    """Build a minimal but valid .nar (zip with META-INF/MANIFEST.MF)."""
    manifest = (
        "Manifest-Version: 1.0\n"
        f"Nar-Group: {group}\n"
        f"Nar-Id: {artifact}\n"
        f"Nar-Version: {version}\n"
        f"Build-Date: {datetime.utcnow().strftime('%Y-%m-%d')}\n"
        "Created-By: NiFi NAR Manager Seed\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/MANIFEST.MF", manifest)
        zf.writestr(f"META-INF/bundled-dependencies/{artifact}.jar", b"demo-jar-content")
        zf.writestr(f"META-INF/docs/{artifact}/index.html", b"<html>demo</html>")
    return buffer.getvalue()


def seed_users(db) -> None:
    users = [
        ("admin", "admin123", "admin", "Administrator", "admin@example.com"),
        ("developer", "developer123", "developer", "Demo Developer", "dev@example.com"),
        ("viewer", "viewer123", "viewer", "Demo Viewer", "viewer@example.com"),
    ]
    for username, password, role, full_name, email in users:
        if db.query(User).filter(User.username == username).first() is None:
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    full_name=full_name,
                    email=email,
                    is_active=True,
                )
            )
    db.commit()
    print("users: ok")


def seed_servers(db) -> None:
    servers = [
        {
            "name": "nifi-dev",
            "hostname": "nifi-dev.example.com",
            "ssh_host": "nifi-dev.example.com",
            "environment": "DEV",
            "description": "Development NiFi instance",
        },
        {
            "name": "nifi-qa",
            "hostname": "nifi-qa.example.com",
            "ssh_host": "nifi-qa.example.com",
            "environment": "QA",
            "description": "QA NiFi cluster node 1",
        },
        {
            "name": "nifi-prod-node1",
            "hostname": "nifi-prod-node1.example.com",
            "ssh_host": "nifi-prod-node1.example.com",
            "environment": "PROD",
            "description": "Production NiFi cluster node 1",
        },
        {
            "name": "nifi-prod-node2",
            "hostname": "nifi-prod-node2.example.com",
            "ssh_host": "nifi-prod-node2.example.com",
            "environment": "PROD",
            "description": "Production NiFi cluster node 2",
        },
        {
            "name": "nifi-prod-node3",
            "hostname": "nifi-prod-node3.example.com",
            "ssh_host": "nifi-prod-node3.example.com",
            "environment": "PROD",
            "description": "Production NiFi cluster node 3",
        },
    ]
    for data in servers:
        if db.query(NiFiServer).filter(NiFiServer.name == data["name"]).first() is None:
            db.add(
                NiFiServer(
                    **data,
                    ssh_port=22,
                    ssh_user="nifi",
                    ssh_key_path="~/.ssh/id_rsa",
                    nar_directory="/opt/nifi/lib",
                    backup_directory="/opt/nifi/nar-backup",
                    nifi_install_directory="/opt/nifi",
                    restart_command="sudo systemctl restart nifi",
                    nifi_api_url=f"https://{data['hostname']}:8443/nifi-api",
                    is_enabled=False,  # demo servers are not reachable
                )
            )
    db.commit()
    print("servers: ok")


def seed_server_groups(db) -> None:
    """Demo: a 3-node PROD cluster group."""
    from app.models.models import ServerGroup

    if db.query(ServerGroup).filter(ServerGroup.name == "nifi-prod-cluster").first() is not None:
        return
    nodes = (
        db.query(NiFiServer)
        .filter(NiFiServer.name.in_(["nifi-prod-node1", "nifi-prod-node2", "nifi-prod-node3"]))
        .all()
    )
    if len(nodes) == 3:
        db.add(
            ServerGroup(
                name="nifi-prod-cluster",
                description="3-node production NiFi cluster — deploys go to all nodes",
                environment="PROD",
                members=nodes,
            )
        )
        db.commit()
    print("server groups: ok")


def seed_bundles(db) -> None:
    bundles = [
        ("org.example.nifi", "nifi-example-processors-nar", "1.0.0", 35),
        ("org.example.nifi", "nifi-example-processors-nar", "1.1.0", 7),
        ("org.example.nifi", "nifi-utils-nar", "2.3.0", 3),
    ]
    for group, artifact, version, age_days in bundles:
        if (
            db.query(NarBundle)
            .filter(
                NarBundle.bundle_group == group,
                NarBundle.artifact == artifact,
                NarBundle.version == version,
            )
            .first()
            is not None
        ):
            continue
        content = make_nar_bytes(group, artifact, version)
        filename = f"{artifact}-{version}.nar"
        dest = settings.nar_dir / group / artifact / version / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        db.add(
            NarBundle(
                bundle_group=group,
                artifact=artifact,
                version=version,
                filename=filename,
                file_path=str(dest),
                file_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                md5=hashlib.md5(content, usedforsecurity=False).hexdigest(),
                uploaded_by="admin",
                uploaded_at=datetime.utcnow() - timedelta(days=age_days),
                build_date=datetime.utcnow() - timedelta(days=age_days),
                source="local",
                tags="demo",
            )
        )
    db.commit()
    print("bundles: ok")


def seed_settings(db) -> None:
    defaults = {
        "ssh_timeout": str(settings.SSH_TIMEOUT),
        "max_upload_size": str(settings.MAX_UPLOAD_SIZE),
        "log_level": settings.LOG_LEVEL,
    }
    for key, value in defaults.items():
        if db.query(Setting).filter(Setting.key == key).first() is None:
            db.add(Setting(key=key, value=value))
    db.commit()
    print("settings: ok")


def seed_audit(db) -> None:
    if db.query(AuditLog).count() > 0:
        return
    db.add(
        AuditLog(
            username="admin",
            full_name="Administrator",
            action="SEED",
            resource_type="system",
            result="success",
            details="Database seeded with demo data",
            ip_address="127.0.0.1",
        )
    )
    db.commit()
    print("audit: ok")


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        seed_users(db)
        seed_servers(db)
        seed_server_groups(db)
        retention_service.get_policy(db)
        print("retention policy: ok")
        seed_settings(db)
        seed_bundles(db)
        seed_audit(db)
    finally:
        db.close()
    print("Seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
