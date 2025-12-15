from __future__ import annotations

import logging
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import paramiko

from app.config import Settings


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
            if hasattr(self.settings, "ssh_known_hosts") and self.settings.ssh_known_hosts:
                known_hosts_paths.insert(0, Path(os.path.expanduser(self.settings.ssh_known_hosts)))

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

            key_path = os.path.expanduser(self.settings.hetzner_key_path)
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

            self._client = client
            return client

    def execute(self, command: str, *, check: bool = False, timeout: int | None = None) -> SSHResult:
        client = self._ensure_client()
        if self.settings.log_ssh_commands:
            logger.debug("SSH exec: %s", command)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
        if check and exit_code != 0:
            raise SSHCommandError(f"Command failed ({exit_code}): {command}\n{err}")
        return SSHResult(stdout=out, stderr=err, exit_code=exit_code)

    def read_file(self, remote_path: str) -> str:
        client = self._ensure_client()
        sftp = client.open_sftp()
        try:
            with sftp.open(remote_path, "r") as remote_file:
                return remote_file.read().decode()
        finally:
            sftp.close()

    def list_directories(self, remote_path: str) -> list[str]:
        client = self._ensure_client()
        sftp = client.open_sftp()
        try:
            entries: Iterable[paramiko.SFTPAttributes] = sftp.listdir_attr(remote_path)
            dirs = [entry.filename for entry in entries if stat.S_ISDIR(entry.st_mode)]
            return sorted(dirs)
        finally:
            sftp.close()

    def close(self):
        with self._lock:
            if self._client:
                self._client.close()
                self._client = None
