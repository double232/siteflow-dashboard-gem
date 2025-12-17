from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobType(str, Enum):
    DB = "db"
    UPLOADS = "uploads"
    VERIFY = "verify"
    SNAPSHOT = "snapshot"
    SYSTEM = "system"  # Full system backup
    SITE = "site"  # Combined site backup (db + uploads)


class BackupStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class BackupRunIn(BaseModel):
    """Payload from backup scripts."""

    site: str = Field(..., description="Site name or 'system' for global jobs")
    job_type: JobType
    status: BackupStatus
    started_at: datetime
    ended_at: datetime
    bytes_written: Optional[int] = None
    backup_id: Optional[str] = Field(None, description="Restic snapshot ID or Hetzner snapshot ID")
    repo: Optional[str] = Field(None, description="Restic repository path")
    error: Optional[str] = None


class BackupRunOut(BaseModel):
    """Stored backup run record."""

    id: int
    site: str
    job_type: JobType
    status: BackupStatus
    started_at: datetime
    ended_at: datetime
    bytes_written: Optional[int] = None
    backup_id: Optional[str] = None
    repo: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


class BackupRunsResponse(BaseModel):
    """Paginated backup runs."""

    runs: list[BackupRunOut]
    total: int
    limit: int
    offset: int


class SiteBackupStatus(BaseModel):
    """Backup status for a single site."""

    site: str
    last_db_run: Optional[BackupRunOut] = None
    last_uploads_run: Optional[BackupRunOut] = None
    last_verify_run: Optional[BackupRunOut] = None
    last_snapshot_run: Optional[BackupRunOut] = None
    rpo_seconds_db: Optional[int] = Field(None, description="Seconds since last successful DB backup")
    rpo_seconds_uploads: Optional[int] = Field(None, description="Seconds since last successful uploads backup")
    overall_status: BackupStatus


class BackupSummaryResponse(BaseModel):
    """Summary of backup status for all sites."""

    sites: list[SiteBackupStatus]
    thresholds: BackupThresholds


class BackupThresholds(BaseModel):
    """Configurable thresholds for backup freshness."""

    db_fresh_hours: int = 26
    uploads_fresh_hours: int = 30
    verify_fresh_days: int = 7
    snapshot_fresh_days: int = 8


class RestorePointOut(BaseModel):
    """A restorable backup point."""

    site: str
    job_type: JobType
    timestamp: datetime
    backup_id: str
    repo: Optional[str] = None


class RestorePointsResponse(BaseModel):
    """List of restore points for a site."""

    site: str
    restore_points: list[RestorePointOut]


class BackupConfigResponse(BaseModel):
    """Backup configuration and thresholds."""

    thresholds: BackupThresholds
    restic_repo: str = "/mnt/nas_backups/restic/webserver"


# === New schemas for backup/restore actions ===


class BackupRequest(BaseModel):
    """Request to trigger a backup."""

    snapshot_tag: Optional[str] = Field(None, description="Optional tag for the snapshot")


class RestoreRequest(BaseModel):
    """Request to restore from backup."""

    snapshot_id: str = Field(..., description="Restic snapshot ID to restore from")
    confirm: bool = Field(False, description="Must be True to proceed with restore")


class BackupActionResponse(BaseModel):
    """Response from backup/restore action."""

    status: str = Field(..., description="'success' or 'error'")
    output: str = Field(..., description="Command output for console display")
    snapshot_id: Optional[str] = Field(None, description="New snapshot ID if backup succeeded")
    duration_seconds: float = Field(..., description="How long the operation took")


class SnapshotInfo(BaseModel):
    """Restic snapshot information."""

    id: str
    short_id: str
    time: datetime
    hostname: str
    tags: list[str]
    paths: list[str]


class SnapshotsResponse(BaseModel):
    """List of available snapshots."""

    snapshots: list[SnapshotInfo]
    site: Optional[str] = None


class SystemBackupStatus(BaseModel):
    """Status of system-level backups."""

    last_system_backup: Optional[BackupRunOut] = None
    last_all_sites_backup: Optional[BackupRunOut] = None
    rpo_seconds_system: Optional[int] = None
    overall_status: BackupStatus
