from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BackupStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    MISSING = "missing"
    UNKNOWN = "unknown"


class BackupInfo(BaseModel):
    site_name: str
    status: BackupStatus = BackupStatus.UNKNOWN
    last_backup: datetime | None = None
    backup_size_mb: float | None = None
    backup_path: str | None = None
    hours_since_backup: float | None = None


class NASStatus(BaseModel):
    connected: bool = False
    host: str | None = None
    backups: list[BackupInfo] = Field(default_factory=list)
    total_backup_size_mb: float = 0.0
    last_check: datetime | None = None
    error: str | None = None
