"""SSH/SFTP operations against NiFi servers (Paramiko)."""

import json
import logging
import posixpath
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import paramiko

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models.models import NiFiServer

settings = get_settings()
logger = logging.getLogger(__name__)


class SSHError(RuntimeError):
    """Raised on SSH connectivity or command failures."""


class SSHClient:
    """Context-managed SSH/SFTP wrapper for one NiFi server."""

    def __init__(self, server: NiFiServer, timeout: Optional[int] = None):
        self.server = server
        self.timeout = timeout or settings.SSH_TIMEOUT
        self._client: Optional[paramiko.SSHClient] = None

    # ------------------------------------------------------------------
    def connect(self) -> "SSHClient":
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": self.server.ssh_host,
            "port": self.server.ssh_port,
            "username": self.server.ssh_user,
            "timeout": self.timeout,
            "banner_timeout": self.timeout,
            "auth_timeout": self.timeout,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if self.server.ssh_key_path:
            key_path = Path(self.server.ssh_key_path).expanduser()
            if not key_path.exists():
                raise SSHError(f"SSH key not found: {key_path}")
            kwargs["key_filename"] = str(key_path)
        elif self.server.ssh_password_encrypted:
            kwargs["password"] = decrypt_secret(self.server.ssh_password_encrypted)
        else:
            raise SSHError("No SSH credentials configured (key path or password required)")
        try:
            client.connect(**kwargs)
        except paramiko.AuthenticationException as exc:
            raise SSHError(f"SSH authentication failed for {self.server.ssh_user}@{self.server.ssh_host}") from exc
        except (paramiko.SSHException, OSError) as exc:
            raise SSHError(f"SSH connection to {self.server.ssh_host}:{self.server.ssh_port} failed: {exc}") from exc
        self._client = client
        return self

    def __enter__(self) -> "SSHClient":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    def exec_command(self, command: str, timeout: Optional[int] = None) -> Tuple[int, str, str]:
        if not self._client:
            raise SSHError("Not connected")
        _, stdout, stderr = self._client.exec_command(command, timeout=timeout or self.timeout)
        rc = stdout.channel.recv_exit_status()
        return rc, stdout.read().decode(errors="replace").strip(), stderr.read().decode(errors="replace").strip()

    def _sftp(self) -> paramiko.SFTPClient:
        if not self._client:
            raise SSHError("Not connected")
        return self._client.open_sftp()

    @staticmethod
    def _sftp_error(path: str, exc: Exception) -> SSHError:
        """Convert an SFTP OS-level error into an SSHError with context.

        SFTP calls raise OSError subclasses (PermissionError, FileNotFoundError,
        etc.) directly; run_deployment only catches SSHError, so without this
        normalization a permission/storage failure on the server would escape
        as an unhandled exception and leave the deployment record stuck in
        IN_PROGRESS instead of FAILED.
        """
        return SSHError(f"SFTP error on {path!r}: {exc}")

    def file_exists(self, remote_path: str) -> bool:
        with self._sftp() as sftp:
            try:
                sftp.stat(remote_path)
                return True
            except FileNotFoundError:
                return False
            except OSError:
                return False

    def mkdir_p(self, remote_dir: str) -> None:
        parts = [p for p in remote_dir.split("/") if p]
        current = "/" if remote_dir.startswith("/") else ""
        with self._sftp() as sftp:
            for part in parts:
                current = posixpath.join(current, part) if current else part
                try:
                    sftp.stat(current)
                except FileNotFoundError:
                    # Only create when the path is genuinely absent. A
                    # permission-denied stat must NOT trigger mkdir (which would
                    # also fail and mask the real problem); surface it instead.
                    try:
                        sftp.mkdir(current)
                    except OSError as exc:
                        raise self._sftp_error(current, exc) from exc
                except OSError as exc:
                    raise self._sftp_error(current, exc) from exc

    def upload_file(self, local_path: str, remote_path: str) -> None:
        parent = posixpath.dirname(remote_path)
        self.mkdir_p(parent)
        with self._sftp() as sftp:
            try:
                sftp.put(local_path, remote_path)
            except OSError as exc:
                raise self._sftp_error(remote_path, exc) from exc

    def download_file(self, remote_path: str, local_path: str) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with self._sftp() as sftp:
            try:
                sftp.get(remote_path, local_path)
            except OSError as exc:
                raise self._sftp_error(remote_path, exc) from exc

    def remove_file(self, remote_path: str) -> None:
        with self._sftp() as sftp:
            try:
                sftp.remove(remote_path)
            except OSError as exc:
                raise self._sftp_error(remote_path, exc) from exc

    def remote_sha256(self, remote_path: str) -> str:
        rc, out, err = self.exec_command(f"sha256sum {remote_path!r} | awk '{{print $1}}'")
        if rc != 0 or not out:
            raise SSHError(f"sha256sum failed for {remote_path}: {err or out}")
        return out.split()[0]

    def remote_matches_sha256(self, remote_path: str, expected: str) -> bool:
        """True iff the remote file exists and its sha256 equals ``expected``.

        ``sha256sum`` runs on the server (a single fast command) — it does not
        transfer any bytes, so it is cheap compared to backing up/uploading.
        """
        try:
            return self.remote_sha256(remote_path).strip().lower() == expected.strip().lower()
        except SSHError:
            return False

    def list_nars(self, remote_dir: str) -> List[str]:
        rc, out, _ = self.exec_command(f"ls -1 {remote_dir!r}/*.nar 2>/dev/null || true")
        if not out:
            return []
        return [line.strip() for line in out.splitlines() if line.strip().endswith(".nar")]

    def list_remote_nars_detailed(self, remote_dir: str) -> List[Dict]:
        rc, out, _ = self.exec_command(
            f"ls -l --time-style=+%Y-%m-%dT%H:%M:%S {remote_dir!r}/*.nar 2>/dev/null || true"
        )
        if not out:
            return []
        files = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 7 and parts[-1].endswith(".nar"):
                files.append({
                    "filename": parts[-1],
                    "size_bytes": int(parts[4]),
                    "modified": parts[5],
                })
        return files

    def delete_remote_files(self, remote_dir: str, filenames: List[str]) -> List[Dict]:
        results = []
        for name in filenames:
            path = posixpath.join(remote_dir, name)
            try:
                with self._sftp() as sftp:
                    sftp.remove(path)
                results.append({"filename": name, "success": True, "error": None})
            except Exception as e:
                results.append({"filename": name, "success": False, "error": str(e)})
        return results

    def disk_usage(self, path: str) -> Tuple[int, int, int]:
        """Return (total, used, free) bytes for the filesystem containing path."""
        rc, out, err = self.exec_command(f"df -B1 {path!r} | tail -1")
        if rc != 0:
            raise SSHError(f"df failed: {err or out}")
        parts = out.split()
        return int(parts[1]), int(parts[2]), int(parts[3])

    def dir_size(self, path: str) -> int:
        rc, out, _ = self.exec_command(f"du -sb {path!r} 2>/dev/null | cut -f1")
        return int(out) if rc == 0 and out.isdigit() else 0

    def get_health(self) -> dict:
        """Collect disk/cpu/memory/process health metrics."""
        health: dict = {"warnings": []}
        total, used, free = self.disk_usage(self.server.nar_directory)
        health.update(
            disk_total_bytes=total,
            disk_used_bytes=used,
            disk_free_bytes=free,
            disk_used_percent=round(used / total * 100, 1) if total else None,
            nar_dir_size_bytes=self.dir_size(self.server.nar_directory),
        )
        if health["disk_used_percent"] and health["disk_used_percent"] >= 90:
            health["warnings"].append(f"Disk usage critical: {health['disk_used_percent']}%")
        elif health["disk_used_percent"] and health["disk_used_percent"] >= 80:
            health["warnings"].append(f"Disk usage high: {health['disk_used_percent']}%")

        rc, out, _ = self.exec_command("grep 'cpu ' /proc/stat")
        if rc == 0 and out:
            fields = [int(x) for x in out.split()[1:]]
            idle = fields[3] + fields[4]
            total_cpu = sum(fields)
            health["cpu_percent"] = round((1 - idle / total_cpu) * 100, 1) if total_cpu else None

        rc, out, _ = self.exec_command("free -b | awk '/Mem:/ {print $2, $3}'")
        if rc == 0 and out:
            mem_total, mem_used = out.split()
            health["memory_percent"] = round(int(mem_used) / int(mem_total) * 100, 1) if int(mem_total) else None

        rc, out, _ = self.exec_command("cat /proc/uptime | cut -d' ' -f1")
        if rc == 0 and out:
            health["uptime_seconds"] = int(float(out.split()[0]))

        rc, _, _ = self.exec_command("pgrep -f org.apache.nifi.NiFi >/dev/null || pgrep -f nifi >/dev/null")
        health["nifi_status"] = "running" if rc == 0 else "stopped"

        health["nifi_version"] = self._fetch_nifi_version()
        return health

    def _fetch_nifi_version(self) -> Optional[str]:
        if self.server.nifi_api_url:
            try:
                url = self.server.nifi_api_url.rstrip("/")
                resp = urllib.request.urlopen(url, timeout=5)
                data = json.loads(resp.read().decode())
                version = data.get("about", {}).get("version")
                if version:
                    return version
            except Exception:
                pass
        rc, out, _ = self.exec_command(
            f"cat {self.server.nifi_install_directory!r}/VERSION 2>/dev/null"
            f" || ls {self.server.nifi_install_directory!r}/lib/nifi-framework-api-*.jar 2>/dev/null"
            " | grep -oP '\\d+\\.\\d+\\.\\d+' | head -1"
        )
        return out if rc == 0 and out else None


def test_connection(server: NiFiServer) -> dict:
    """Attempt an SSH handshake; return latency and basic info."""
    started = time.monotonic()
    try:
        with SSHClient(server, timeout=10) as ssh:
            rc, out, _ = ssh.exec_command("echo ok")
            latency = (time.monotonic() - started) * 1000
            if rc != 0 or out != "ok":
                return {"success": False, "message": "Connected but echo test failed", "latency_ms": latency}
            nifi_version = None
            try:
                if server.nifi_api_url:
                    try:
                        url = server.nifi_api_url.rstrip("/")
                        resp = urllib.request.urlopen(url, timeout=5)
                        data = json.loads(resp.read().decode())
                        version = data.get("about", {}).get("version")
                        if version:
                            nifi_version = version
                    except Exception:
                        pass
                if not nifi_version:
                    rc, ver, _ = ssh.exec_command(
                        f"cat {server.nifi_install_directory!r}/VERSION 2>/dev/null || true"
                    )
                    nifi_version = ver or None
            except SSHError:
                pass
            return {
                "success": True,
                "message": f"SSH connection to {server.ssh_host}:{server.ssh_port} successful",
                "latency_ms": round(latency, 1),
                "nifi_version": nifi_version,
            }
    except SSHError as exc:
        return {"success": False, "message": str(exc), "latency_ms": None}
