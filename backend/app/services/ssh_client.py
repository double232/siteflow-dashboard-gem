from __future__ import annotations

import logging
import os
import stat
import threading
from dataclasses import dataclass
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
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            key_path = os.path.expanduser(self.settings.hetzner_key_path)
            if not os.path.exists(key_path):
                raise FileNotFoundError(f"SSH key not found: {key_path}")

            client.connect(
                hostname=self.settings.hetzner_host,
                port=self.settings.hetzner_port,
                username=self.settings.hetzner_user,
                key_filename=key_path,
                timeout=self.settings.ssh_timeout,
            )
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
