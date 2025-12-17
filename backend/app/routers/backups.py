from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.dependencies import get_audit_service, get_backup_executor, get_backup_service
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.schemas.backups import (
    BackupActionResponse,
    BackupConfigResponse,
    BackupRequest,
    BackupRunIn,
    BackupRunOut,
    BackupRunsResponse,
    BackupStatus,
    BackupSummaryResponse,
    BackupThresholds,
    JobType,
    RestorePointsResponse,
    RestoreRequest,
    SnapshotsResponse,
    SystemBackupStatus,
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


# === Backup/Restore Action Endpoints ===


@router.post("/site/{site}/backup", response_model=BackupActionResponse)
async def backup_site(site: str, request: Optional[BackupRequest] = None):
    """
    Trigger a backup for a single site.

    Backs up the site's files to the restic repository.
    """
    executor = get_backup_executor()
    audit = get_audit_service()

    logger.info(f"Starting backup for site: {site}")

    try:
        result = await executor.backup_site(site)

        audit.log_action(
            action_type=ActionType.BACKUP_RUN,
            target_type=TargetType.SITE,
            target_name=site,
            status=ActionStatus.SUCCESS if result.status == "success" else ActionStatus.FAILURE,
            output=result.output[:500],
            metadata={"snapshot_id": result.snapshot_id},
            duration_ms=int(result.duration_seconds * 1000),
        )

        return result

    except Exception as e:
        logger.error(f"Backup failed for site {site}: {e}")
        audit.log_action(
            action_type=ActionType.BACKUP_RUN,
            target_type=TargetType.SITE,
            target_name=site,
            status=ActionStatus.FAILURE,
            output=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/site/{site}/restore", response_model=BackupActionResponse)
async def restore_site(site: str, request: RestoreRequest):
    """
    Restore a site from a restic snapshot.

    Requires confirm=true in the request body to proceed.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Restore requires confirm=true. This is a destructive operation.",
        )

    executor = get_backup_executor()
    audit = get_audit_service()

    logger.info(f"Starting restore for site: {site} from snapshot: {request.snapshot_id}")

    try:
        result = await executor.restore_site(site, request.snapshot_id)

        audit.log_action(
            action_type=ActionType.SITE_RESTORE,
            target_type=TargetType.SITE,
            target_name=site,
            status=ActionStatus.SUCCESS if result.status == "success" else ActionStatus.FAILURE,
            output=result.output[:500],
            metadata={"snapshot_id": request.snapshot_id},
            duration_ms=int(result.duration_seconds * 1000),
        )

        return result

    except Exception as e:
        logger.error(f"Restore failed for site {site}: {e}")
        audit.log_action(
            action_type=ActionType.SITE_RESTORE,
            target_type=TargetType.SITE,
            target_name=site,
            status=ActionStatus.FAILURE,
            output=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/all/backup", response_model=BackupActionResponse)
async def backup_all_sites():
    """
    Backup all sites sequentially.

    This may take several minutes depending on the number of sites.
    """
    executor = get_backup_executor()
    audit = get_audit_service()

    logger.info("Starting backup for all sites")

    try:
        result = await executor.backup_all_sites()

        audit.log_action(
            action_type=ActionType.BACKUP_RUN,
            target_type=TargetType.SITE,
            target_name="all-sites",
            status=ActionStatus.SUCCESS if result.status == "success" else ActionStatus.FAILURE,
            output=result.output[:500],
            duration_ms=int(result.duration_seconds * 1000),
        )

        return result

    except Exception as e:
        logger.error(f"Backup all sites failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/system/backup", response_model=BackupActionResponse)
async def backup_system():
    """
    Full system backup for catastrophic recovery.

    Backs up /opt (all sites, gateway, and data) to the restic repository.
    This operation may take 10-30 minutes.
    """
    executor = get_backup_executor()
    audit = get_audit_service()

    logger.info("Starting full system backup")

    try:
        result = await executor.backup_system()

        audit.log_action(
            action_type=ActionType.BACKUP_RUN,
            target_type=TargetType.SITE,
            target_name="system",
            status=ActionStatus.SUCCESS if result.status == "success" else ActionStatus.FAILURE,
            output=result.output[:500],
            metadata={"snapshot_id": result.snapshot_id, "scope": "full-system"},
            duration_ms=int(result.duration_seconds * 1000),
        )

        return result

    except Exception as e:
        logger.error(f"System backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/system/restore", response_model=BackupActionResponse)
async def restore_system(request: RestoreRequest):
    """
    Restore entire system from a snapshot.

    WARNING: This is an extremely destructive operation.
    Requires confirm=true in the request body.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="System restore requires confirm=true. This will overwrite ALL files in /opt.",
        )

    executor = get_backup_executor()
    audit = get_audit_service()

    logger.info(f"Starting SYSTEM RESTORE from snapshot: {request.snapshot_id}")

    try:
        result = await executor.restore_system(request.snapshot_id)

        audit.log_action(
            action_type=ActionType.SITE_RESTORE,
            target_type=TargetType.SITE,
            target_name="system",
            status=ActionStatus.SUCCESS if result.status == "success" else ActionStatus.FAILURE,
            output=result.output[:500],
            metadata={"snapshot_id": request.snapshot_id, "scope": "full-system"},
            duration_ms=int(result.duration_seconds * 1000),
        )

        return result

    except Exception as e:
        logger.error(f"System restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/snapshots", response_model=SnapshotsResponse)
async def list_snapshots():
    """
    List all available restic snapshots.
    """
    executor = get_backup_executor()

    try:
        snapshots = await executor.list_snapshots()
        return SnapshotsResponse(snapshots=snapshots)

    except Exception as e:
        logger.error(f"Failed to list snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/snapshots/{site}", response_model=SnapshotsResponse)
async def list_site_snapshots(site: str):
    """
    List available restic snapshots for a specific site.
    """
    executor = get_backup_executor()

    try:
        snapshots = await executor.list_snapshots(site=site)
        return SnapshotsResponse(snapshots=snapshots, site=site)

    except Exception as e:
        logger.error(f"Failed to list snapshots for site {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/system/status", response_model=SystemBackupStatus)
async def get_system_backup_status():
    """
    Get the status of system-level backups.
    """
    service = get_backup_service()

    # Get last system backup
    last_system = service.get_last_run("system", JobType.SYSTEM)

    # Compute RPO
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rpo_system = None
    if last_system and last_system.status == BackupStatus.OK:
        rpo_system = int((now - last_system.ended_at.replace(tzinfo=timezone.utc)).total_seconds())

    # Determine overall status
    if not last_system:
        overall = BackupStatus.FAIL
    elif last_system.status == BackupStatus.FAIL:
        overall = BackupStatus.FAIL
    elif rpo_system and rpo_system > 86400 * 7:  # Warn if older than 7 days
        overall = BackupStatus.WARN
    else:
        overall = BackupStatus.OK

    return SystemBackupStatus(
        last_system_backup=last_system,
        rpo_seconds_system=rpo_system,
        overall_status=overall,
    )
