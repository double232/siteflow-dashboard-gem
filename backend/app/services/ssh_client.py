from __future__ import annotations

import logging
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import paramiko

from app.config import Settings
from app.utils.path_utils import resolve_local_path


logger = logging.getLogger(__name__)


class SSHCommandError(RuntimeError):
    pass


@dataclass
class SSHResult:
    stdout: str
    stderr: str
    exit_code: int


class SSHClientManager:
    """Thread-safe SSH utility that keeps a reusable Paramiko client."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: paramiko.SSHClient | None = None
        self._lock = threading.RLock()

    def _reset_client(self) -> None:
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                finally:
                    self._client = None

    def _ensure_client(self) -> paramiko.SSHClient:
        with self._lock:
            if self._client:
                return self._client

            client = paramiko.SSHClient()

            # Load system known_hosts for host key verification
            # Check multiple possible locations
            known_hosts_paths = [
                Path.home() / ".ssh" / "known_hosts",
                Path("/etc/ssh/ssh_known_hosts"),
            ]

            # Also check for custom known_hosts from settings
            custom_known_hosts = resolve_local_path(getattr(self.settings, "ssh_known_hosts", None))
            if custom_known_hosts:
                known_hosts_paths.insert(0, Path(custom_known_hosts))

            loaded_known_hosts = False
            for kh_path in known_hosts_paths:
                if kh_path.exists():
                    try:
                        client.load_host_keys(str(kh_path))
                        logger.info(f"Loaded SSH known_hosts from {kh_path}")
                        loaded_known_hosts = True
                        break
                    except Exception as e:
                        logger.warning(f"Failed to load known_hosts from {kh_path}: {e}")

            if not loaded_known_hosts:
                # Fall back to RejectPolicy - will fail if host key not known
                # This is safer than AutoAddPolicy as it prevents MITM
                logger.warning(
                    "No known_hosts file found. SSH connections will fail for unknown hosts. "
                    "Add the server's host key to ~/.ssh/known_hosts or set SSH_KNOWN_HOSTS env var."
                )
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                # Use RejectPolicy - require host to be in known_hosts
                client.set_missing_host_key_policy(paramiko.RejectPolicy())

            key_path = resolve_local_path(self.settings.hetzner_key_path)
            if not os.path.exists(key_path):
                raise FileNotFoundError(f"SSH key not found: {key_path}")

            try:
                client.connect(
                    hostname=self.settings.hetzner_host,
                    port=self.settings.hetzner_port,
                    username=self.settings.hetzner_user,
                    key_filename=key_path,
                    timeout=self.settings.ssh_timeout,
                )
            except paramiko.SSHException as e:
                if "not found in known_hosts" in str(e).lower() or "host key" in str(e).lower():
                    raise SSHCommandError(
                        f"SSH host key verification failed for {self.settings.hetzner_host}. "
                        f"Add the host key to known_hosts: ssh-keyscan -H {self.settings.hetzner_host} >> ~/.ssh/known_hosts"
                    ) from e
                raise

            transport = client.get_transport()
            if transport:
                transport.set_keepalive(30)

            self._client = client
            return client

    def _run_with_retry(self, operation):
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                return operation(self._ensure_client())
            except (paramiko.SSHException, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "SSH operation %s failed (attempt %d/2): %s",
                    getattr(operation, "__name__", operation.__class__.__name__),
                    attempt + 1,
                    exc,
                )
                self._reset_client()
        if last_exc:
            raise last_exc
        raise RuntimeError("SSH operation failed without raising exception")

    def execute(self, command: str, *, check: bool = False, timeout: int | None = None) -> SSHResult:
        def _operation(client: paramiko.SSHClient) -> SSHResult:
            if self.settings.log_ssh_commands:
                logger.debug("SSH exec: %s", command)
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            exit_code = stdout.channel.recv_exit_status()
            if check and exit_code != 0:
                raise SSHCommandError(f"Command failed ({exit_code}): {command}\n{err}")
            return SSHResult(stdout=out, stderr=err, exit_code=exit_code)

        return self._run_with_retry(_operation)

    def read_file(self, remote_path: str) -> str:
        def _operation(client: paramiko.SSHClient) -> str:
            sftp = client.open_sftp()
            try:
                with sftp.open(remote_path, "r") as remote_file:
                    return remote_file.read().decode()
            finally:
                sftp.close()

        return self._run_with_retry(_operation)

    def list_directories(self, remote_path: str) -> list[str]:
        def _operation(client: paramiko.SSHClient) -> list[str]:
            sftp = client.open_sftp()
            try:
                entries: Iterable[paramiko.SFTPAttributes] = sftp.listdir_attr(remote_path)
                dirs = [entry.filename for entry in entries if stat.S_ISDIR(entry.st_mode)]
                return sorted(dirs)
            finally:
                sftp.close()

        return self._run_with_retry(_operation)

    def close(self):
        self._reset_client()
