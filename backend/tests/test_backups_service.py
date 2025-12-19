from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.backups import BackupRunIn, BackupStatus, BackupThresholds, JobType
from app.services.backups import BackupService


@pytest.fixture
def backup_service(tmp_path) -> BackupService:
    db_path = tmp_path / "backups.db"
    return BackupService(str(db_path))


def _make_run(
    site: str,
    job_type: JobType,
    status: BackupStatus = BackupStatus.OK,
    *,
    started: datetime | None = None,
    ended: datetime | None = None,
    backup_id: str | None = "snap-1",
) -> BackupRunIn:
    started_at = started or datetime.now(timezone.utc) - timedelta(minutes=5)
    ended_at = ended or datetime.now(timezone.utc)
    return BackupRunIn(
        site=site,
        job_type=job_type,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        bytes_written=1024,
        backup_id=backup_id,
        repo="/tmp/repo",
        error=None,
    )


def test_store_and_query_runs(backup_service: BackupService) -> None:
    run = _make_run("alpha", JobType.DB)
    stored = backup_service.store_run(run)
    assert stored.id > 0

    runs, total = backup_service.get_runs(site="alpha")
    assert total == 1
    assert runs[0].site == "alpha"
    assert runs[0].job_type == JobType.DB


def test_compute_site_status_uses_site_fallback(backup_service: BackupService) -> None:
    backup_service.store_run(_make_run("alpha", JobType.SITE))
    status = backup_service.compute_site_status(
        "alpha",
        BackupThresholds(
            db_fresh_hours=48,
            uploads_fresh_hours=48,
            verify_fresh_days=7,
            snapshot_fresh_days=7,
        ),
    )
    assert status.overall_status == BackupStatus.OK
    assert status.last_db_run is not None
    assert status.last_uploads_run is not None


def test_compute_site_status_warns_when_stale(backup_service: BackupService) -> None:
    old_time = datetime.now(timezone.utc) - timedelta(hours=100)
    backup_service.store_run(
        _make_run(
            "beta",
            JobType.DB,
            started=old_time - timedelta(minutes=10),
            ended=old_time,
        )
    )
    # Fresh uploads backup so only DB age should trigger warning
    backup_service.store_run(_make_run("beta", JobType.UPLOADS))
    status = backup_service.compute_site_status(
        "beta",
        BackupThresholds(
            db_fresh_hours=24,
            uploads_fresh_hours=24,
            verify_fresh_days=7,
            snapshot_fresh_days=7,
        ),
    )
    assert status.overall_status == BackupStatus.WARN


def test_restore_points_and_cleanup(backup_service: BackupService) -> None:
    recent = datetime.now(timezone.utc)
    backup_service.store_run(
        _make_run("gamma", JobType.DB, started=recent - timedelta(hours=1), ended=recent, backup_id="snap-db")
    )
    restore_points = backup_service.get_restore_points("gamma")
    assert restore_points
    assert restore_points[0].backup_id == "snap-db"

    deleted = backup_service.cleanup_old_runs(retention_days=0)
    assert deleted >= 1
