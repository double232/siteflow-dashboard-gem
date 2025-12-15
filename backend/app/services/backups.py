from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.schemas.backups import (
    BackupRunIn,
    BackupRunOut,
    BackupStatus,
    BackupThresholds,
    JobType,
    RestorePointOut,
    SiteBackupStatus,
)

logger = logging.getLogger(__name__)


class BackupService:
    """Service for managing backup run records and computing backup health."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Create backup_runs table if it doesn't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backup_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    bytes_written INTEGER,
                    backup_id TEXT,
                    repo TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_backup_runs_site
                ON backup_runs(site)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_backup_runs_job_type
                ON backup_runs(job_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_backup_runs_started_at
                ON backup_runs(started_at DESC)
            """)
            conn.commit()

    def _row_to_run(self, row: sqlite3.Row) -> BackupRunOut:
        """Convert a database row to BackupRunOut."""
        return BackupRunOut(
            id=row["id"],
            site=row["site"],
            job_type=JobType(row["job_type"]),
            status=BackupStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]),
            bytes_written=row["bytes_written"],
            backup_id=row["backup_id"],
            repo=row["repo"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def store_run(self, run: BackupRunIn) -> BackupRunOut:
        """Store a backup run record."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO backup_runs
                (site, job_type, status, started_at, ended_at, bytes_written, backup_id, repo, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.site,
                    run.job_type.value,
                    run.status.value,
                    run.started_at.isoformat(),
                    run.ended_at.isoformat(),
                    run.bytes_written,
                    run.backup_id,
                    run.repo,
                    run.error,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid

            row = conn.execute(
                "SELECT * FROM backup_runs WHERE id = ?", (row_id,)
            ).fetchone()
            return self._row_to_run(row)

    def get_runs(
        self,
        site: Optional[str] = None,
        job_type: Optional[JobType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BackupRunOut], int]:
        """Get backup runs with optional filters."""
        conditions = []
        params: list = []

        if site:
            conditions.append("site = ?")
            params.append(site)
        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type.value)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._get_conn() as conn:
            # Get total count
            count_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM backup_runs WHERE {where_clause}",
                params,
            ).fetchone()
            total = count_row["cnt"]

            # Get paginated results
            rows = conn.execute(
                f"""
                SELECT * FROM backup_runs
                WHERE {where_clause}
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

            runs = [self._row_to_run(row) for row in rows]
            return runs, total

    def get_last_run(
        self, site: str, job_type: JobType, status: Optional[BackupStatus] = None
    ) -> Optional[BackupRunOut]:
        """Get the most recent run for a site and job type."""
        with self._get_conn() as conn:
            if status:
                row = conn.execute(
                    """
                    SELECT * FROM backup_runs
                    WHERE site = ? AND job_type = ? AND status = ?
                    ORDER BY started_at DESC LIMIT 1
                    """,
                    (site, job_type.value, status.value),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM backup_runs
                    WHERE site = ? AND job_type = ?
                    ORDER BY started_at DESC LIMIT 1
                    """,
                    (site, job_type.value),
                ).fetchone()

            return self._row_to_run(row) if row else None

    def get_all_sites(self) -> list[str]:
        """Get list of all sites that have backup records."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT site FROM backup_runs ORDER BY site"
            ).fetchall()
            return [row["site"] for row in rows]

    def compute_site_status(
        self, site: str, thresholds: BackupThresholds
    ) -> SiteBackupStatus:
        """Compute backup status for a single site."""
        now = datetime.now(timezone.utc)

        last_db = self.get_last_run(site, JobType.DB)
        last_uploads = self.get_last_run(site, JobType.UPLOADS)
        last_verify = self.get_last_run(site, JobType.VERIFY)
        last_snapshot = self.get_last_run(site, JobType.SNAPSHOT)

        # Compute RPO (time since last successful backup)
        last_db_ok = self.get_last_run(site, JobType.DB, BackupStatus.OK)
        last_uploads_ok = self.get_last_run(site, JobType.UPLOADS, BackupStatus.OK)

        rpo_db = None
        rpo_uploads = None

        if last_db_ok:
            rpo_db = int((now - last_db_ok.ended_at.replace(tzinfo=timezone.utc)).total_seconds())
        if last_uploads_ok:
            rpo_uploads = int((now - last_uploads_ok.ended_at.replace(tzinfo=timezone.utc)).total_seconds())

        # Compute overall status
        overall = self._compute_overall_status(
            last_db, last_uploads, last_verify, last_snapshot, thresholds, now
        )

        return SiteBackupStatus(
            site=site,
            last_db_run=last_db,
            last_uploads_run=last_uploads,
            last_verify_run=last_verify,
            last_snapshot_run=last_snapshot,
            rpo_seconds_db=rpo_db,
            rpo_seconds_uploads=rpo_uploads,
            overall_status=overall,
        )

    def _compute_overall_status(
        self,
        last_db: Optional[BackupRunOut],
        last_uploads: Optional[BackupRunOut],
        last_verify: Optional[BackupRunOut],
        last_snapshot: Optional[BackupRunOut],
        thresholds: BackupThresholds,
        now: datetime,
    ) -> BackupStatus:
        """Compute overall backup status based on thresholds."""
        issues = []

        # Check DB backup
        if not last_db:
            issues.append("fail")
        elif last_db.status == BackupStatus.FAIL:
            issues.append("fail")
        elif (now - last_db.ended_at.replace(tzinfo=timezone.utc)) > timedelta(hours=thresholds.db_fresh_hours):
            issues.append("warn")

        # Check uploads backup
        if not last_uploads:
            issues.append("fail")
        elif last_uploads.status == BackupStatus.FAIL:
            issues.append("fail")
        elif (now - last_uploads.ended_at.replace(tzinfo=timezone.utc)) > timedelta(hours=thresholds.uploads_fresh_hours):
            issues.append("warn")

        # Check verify (less critical)
        if last_verify and last_verify.status == BackupStatus.FAIL:
            issues.append("warn")
        elif last_verify and (now - last_verify.ended_at.replace(tzinfo=timezone.utc)) > timedelta(days=thresholds.verify_fresh_days):
            issues.append("warn")

        # Check snapshot (less critical)
        if last_snapshot and last_snapshot.status == BackupStatus.FAIL:
            issues.append("warn")
        elif last_snapshot and (now - last_snapshot.ended_at.replace(tzinfo=timezone.utc)) > timedelta(days=thresholds.snapshot_fresh_days):
            issues.append("warn")

        if "fail" in issues:
            return BackupStatus.FAIL
        if "warn" in issues:
            return BackupStatus.WARN
        return BackupStatus.OK

    def get_restore_points(self, site: str, limit: int = 20) -> list[RestorePointOut]:
        """Get available restore points for a site."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM backup_runs
                WHERE site = ?
                  AND status = 'ok'
                  AND backup_id IS NOT NULL
                  AND job_type IN ('db', 'uploads')
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (site, limit),
            ).fetchall()

            return [
                RestorePointOut(
                    site=row["site"],
                    job_type=JobType(row["job_type"]),
                    timestamp=datetime.fromisoformat(row["started_at"]),
                    backup_id=row["backup_id"],
                    repo=row["repo"],
                )
                for row in rows
            ]

    def cleanup_old_runs(self, retention_days: int = 90) -> int:
        """Delete backup run records older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM backup_runs WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()
            return cursor.rowcount
