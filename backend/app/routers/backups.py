from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.dependencies import get_audit_service, get_backup_service
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.schemas.backups import (
    BackupConfigResponse,
    BackupRunIn,
    BackupRunOut,
    BackupRunsResponse,
    BackupSummaryResponse,
    BackupThresholds,
    JobType,
    RestorePointsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backups", tags=["backups"])

# Default thresholds - can be made configurable via env vars later
DEFAULT_THRESHOLDS = BackupThresholds(
    db_fresh_hours=26,
    uploads_fresh_hours=30,
    verify_fresh_days=7,
    snapshot_fresh_days=8,
)


@router.post("/runs", response_model=BackupRunOut)
async def ingest_backup_run(run: BackupRunIn):
    """
    Ingest a backup run result from backup scripts.

    This endpoint is called by the backup scripts after each run completes.
    """
    service = get_backup_service()
    audit = get_audit_service()

    try:
        stored_run = service.store_run(run)

        # Log to audit
        audit.log_action(
            action_type=ActionType.BACKUP_RUN,
            target_type=TargetType.SITE,
            target_name=run.site,
            status=ActionStatus.SUCCESS if run.status.value == "ok" else ActionStatus.FAILURE,
            output=f"Backup {run.job_type.value}: {run.status.value}",
            metadata={
                "job_type": run.job_type.value,
                "backup_id": run.backup_id,
                "bytes_written": run.bytes_written,
            },
            duration_ms=int((run.ended_at - run.started_at).total_seconds() * 1000),
        )

        logger.info(f"Ingested backup run: {run.site}/{run.job_type.value} = {run.status.value}")
        return stored_run

    except Exception as e:
        logger.error(f"Failed to ingest backup run: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/runs", response_model=BackupRunsResponse)
async def get_backup_runs(
    site: Optional[str] = None,
    job_type: Optional[JobType] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    Get backup run history with optional filters.
    """
    service = get_backup_service()

    if limit > 200:
        limit = 200

    runs, total = service.get_runs(site=site, job_type=job_type, limit=limit, offset=offset)

    return BackupRunsResponse(runs=runs, total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=BackupSummaryResponse)
async def get_backup_summary():
    """
    Get backup status summary for all sites.

    Returns per-site status including last run times, RPO, and overall health.
    """
    service = get_backup_service()

    sites = service.get_all_sites()
    site_statuses = [
        service.compute_site_status(site, DEFAULT_THRESHOLDS) for site in sites
    ]

    return BackupSummaryResponse(sites=site_statuses, thresholds=DEFAULT_THRESHOLDS)


@router.get("/restore-points", response_model=RestorePointsResponse)
async def get_restore_points(site: str, limit: int = 20):
    """
    Get available restore points for a site.

    Returns timestamps and backup IDs that can be used with the restore script.
    """
    service = get_backup_service()

    if limit > 100:
        limit = 100

    restore_points = service.get_restore_points(site, limit)

    return RestorePointsResponse(site=site, restore_points=restore_points)


@router.get("/config", response_model=BackupConfigResponse)
async def get_backup_config():
    """
    Get backup configuration and thresholds.
    """
    return BackupConfigResponse(
        thresholds=DEFAULT_THRESHOLDS,
        restic_repo="/mnt/nas_backups/restic/webserver",
    )
