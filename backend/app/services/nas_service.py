from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import PurePosixPath

from smbclient import register_session, scandir

from app.config import Settings
from app.schemas.backup import BackupInfo, BackupStatus, NASStatus
from app.services.cache import TimedCache


logger = logging.getLogger(__name__)


class NASService:
    """Service for monitoring backup status on NAS via SMB/Samba."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._connected = False
        self._lock = threading.RLock()
        self._last_attempt: float = 0
        self.cache = TimedCache[NASStatus](ttl_seconds=settings.nas_poll_interval_seconds)

    def _get_share_path(self, *parts: str) -> str:
        """Build UNC path to NAS share."""
        base = f"//{self.settings.nas_host}/{self.settings.nas_share}"
        if self.settings.nas_backup_path:
            base = f"{base}/{self.settings.nas_backup_path}"
        if parts:
            return f"{base}/{'/'.join(parts)}"
        return base

    def _ensure_connection(self) -> bool:
        """Register SMB session if credentials are configured."""
        if not all([self.settings.nas_host, self.settings.nas_user, self.settings.nas_password]):
            return False

        now = time.time()
        if now - self._last_attempt < self.settings.nas_poll_interval_seconds:
            return self._connected

        with self._lock:
            self._last_attempt = now
            if self._connected:
                return True

            try:
                register_session(
                    self.settings.nas_host,
                    username=self.settings.nas_user,
                    password=self.settings.nas_password,
                )
                self._connected = True
                logger.info("Connected to NAS at %s", self.settings.nas_host)
                return True
            except Exception as e:
                logger.warning("Failed to connect to NAS: %s", e)
                self._connected = False
                return False

    def get_backup_status(self, site_names: list[str], force_refresh: bool = False) -> NASStatus:
        """Get backup status for specified sites."""
        def builder() -> NASStatus:
            return self._collect_backup_status(site_names)

        return self.cache.get(builder, force_refresh=force_refresh)

    def _collect_backup_status(self, site_names: list[str]) -> NASStatus:
        """Collect backup information from NAS."""
        if not self._ensure_connection():
            return NASStatus(
                connected=False,
                host=self.settings.nas_host,
                error="NAS credentials not configured or connection failed",
                last_check=datetime.utcnow(),
            )

        try:
            backups: list[BackupInfo] = []
            total_size = 0.0

            for site_name in site_names:
                backup_info = self._get_site_backup_info(site_name)
                backups.append(backup_info)
                if backup_info.backup_size_mb:
                    total_size += backup_info.backup_size_mb

            return NASStatus(
                connected=True,
                host=self.settings.nas_host,
                backups=backups,
                total_backup_size_mb=total_size,
                last_check=datetime.utcnow(),
            )

        except Exception as e:
            logger.error("Failed to collect backup status: %s", e)
            self._connected = False
            return NASStatus(
                connected=False,
                host=self.settings.nas_host,
                error=str(e),
                last_check=datetime.utcnow(),
            )

    def _get_site_backup_info(self, site_name: str) -> BackupInfo:
        """Get backup information for a single site."""
        backup_path = self._get_share_path(site_name)

        try:
            entries = list(scandir(backup_path))

            if not entries:
                return BackupInfo(
                    site_name=site_name,
                    status=BackupStatus.MISSING,
                    backup_path=backup_path,
                )

            most_recent = max(entries, key=lambda e: e.stat().st_mtime)
            mtime = most_recent.stat().st_mtime
            last_backup = datetime.fromtimestamp(mtime)
            hours_since = (datetime.utcnow() - last_backup).total_seconds() / 3600

            if hours_since <= self.settings.nas_stale_threshold_hours:
                status = BackupStatus.CURRENT
            else:
                status = BackupStatus.STALE

            total_size = sum(
                e.stat().st_size for e in entries if e.is_file()
            ) / (1024 * 1024)

            return BackupInfo(
                site_name=site_name,
                status=status,
                last_backup=last_backup,
                backup_size_mb=total_size,
                backup_path=backup_path,
                hours_since_backup=hours_since,
            )

        except FileNotFoundError:
            return BackupInfo(
                site_name=site_name,
                status=BackupStatus.MISSING,
                backup_path=backup_path,
            )
        except Exception as e:
            logger.warning("Failed to get backup info for %s: %s", site_name, e)
            return BackupInfo(
                site_name=site_name,
                status=BackupStatus.UNKNOWN,
                backup_path=backup_path,
            )

    def close(self) -> None:
        """Close SMB connections."""
        with self._lock:
            self._connected = False
