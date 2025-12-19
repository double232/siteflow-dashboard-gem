from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.schemas.backups import (
    BackupActionResponse,
    BackupRunIn,
    BackupRunOut,
    BackupStatus,
    BackupThresholds,
    JobType,
    RestorePointOut,
    SiteBackupStatus,
    SnapshotInfo,
)

if TYPE_CHECKING:
    from app.services.ssh_client import SSHClientManager

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

        # Check for SITE backup (new executor) or legacy DB/UPLOADS backups
        last_site = self.get_last_run(site, JobType.SITE)
        last_db = self.get_last_run(site, JobType.DB)
        last_uploads = self.get_last_run(site, JobType.UPLOADS)
        last_verify = self.get_last_run(site, JobType.VERIFY)
        last_snapshot = self.get_last_run(site, JobType.SNAPSHOT)

        # Use SITE backup as fallback for DB/UPLOADS if they don't exist
        effective_db = last_db or last_site
        effective_uploads = last_uploads or last_site

        # Compute RPO (time since last successful backup)
        last_site_ok = self.get_last_run(site, JobType.SITE, BackupStatus.OK)
        last_db_ok = self.get_last_run(site, JobType.DB, BackupStatus.OK)
        last_uploads_ok = self.get_last_run(site, JobType.UPLOADS, BackupStatus.OK)

        # Use SITE backup time if no specific DB/UPLOADS backup
        effective_db_ok = last_db_ok or last_site_ok
        effective_uploads_ok = last_uploads_ok or last_site_ok

        rpo_db = None
        rpo_uploads = None

        if effective_db_ok:
            rpo_db = int((now - effective_db_ok.ended_at.replace(tzinfo=timezone.utc)).total_seconds())
        if effective_uploads_ok:
            rpo_uploads = int((now - effective_uploads_ok.ended_at.replace(tzinfo=timezone.utc)).total_seconds())

        # Compute overall status using effective backups
        overall = self._compute_overall_status(
            effective_db, effective_uploads, last_verify, last_snapshot, thresholds, now
        )

        return SiteBackupStatus(
            site=site,
            last_db_run=effective_db,
            last_uploads_run=effective_uploads,
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

    async def store_run_async(self, run: BackupRunIn) -> BackupRunOut:
        return await asyncio.to_thread(self.store_run, run)

    async def get_runs_async(
        self,
        site: Optional[str] = None,
        job_type: Optional[JobType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BackupRunOut], int]:
        return await asyncio.to_thread(self.get_runs, site, job_type, limit, offset)

    async def get_last_run_async(
        self, site: str, job_type: JobType, status: Optional[BackupStatus] = None
    ) -> Optional[BackupRunOut]:
        return await asyncio.to_thread(self.get_last_run, site, job_type, status)

    async def get_all_sites_async(self) -> list[str]:
        return await asyncio.to_thread(self.get_all_sites)

    async def compute_site_status_async(
        self, site: str, thresholds: BackupThresholds
    ) -> SiteBackupStatus:
        return await asyncio.to_thread(self.compute_site_status, site, thresholds)

    async def get_restore_points_async(self, site: str, limit: int = 20) -> list[RestorePointOut]:
        return await asyncio.to_thread(self.get_restore_points, site, limit)

    async def cleanup_old_runs_async(self, retention_days: int = 90) -> int:
        return await asyncio.to_thread(self.cleanup_old_runs, retention_days)


class BackupExecutor:
    """Executes backup and restore operations via SSH."""

    # Restic repository configuration (SMB mount)
    RESTIC_REPO = "/mnt/nas-backup/backups/restic"
    RESTIC_PASSWORD_FILE = "/root/.restic-password"
    SITES_ROOT = "/opt/sites"

    def __init__(self, ssh: SSHClientManager, backup_service: BackupService):
        self.ssh = ssh
        self.backup_service = backup_service

    def _restic_env(self) -> str:
        """Return environment variables for restic commands."""
        return f"RESTIC_REPOSITORY={self.RESTIC_REPO} RESTIC_PASSWORD_FILE={self.RESTIC_PASSWORD_FILE}"

    def _parse_backup_stats(self, output: str) -> dict:
        """Parse restic JSON output to extract backup statistics."""
        stats = {
            "files_new": 0,
            "files_changed": 0,
            "files_unmodified": 0,
            "dirs_new": 0,
            "dirs_changed": 0,
            "dirs_unmodified": 0,
            "data_added": 0,
            "total_files": 0,
            "total_bytes": 0,
            "snapshot_id": None,
        }
        try:
            for line in output.strip().split("\n"):
                if not line.strip():
                    continue
                data = json.loads(line)
                msg_type = data.get("message_type", "")
                if msg_type == "summary":
                    stats["files_new"] = data.get("files_new", 0)
                    stats["files_changed"] = data.get("files_changed", 0)
                    stats["files_unmodified"] = data.get("files_unmodified", 0)
                    stats["dirs_new"] = data.get("dirs_new", 0)
                    stats["dirs_changed"] = data.get("dirs_changed", 0)
                    stats["dirs_unmodified"] = data.get("dirs_unmodified", 0)
                    stats["data_added"] = data.get("data_added", 0)
                    stats["total_files"] = data.get("total_files_processed", 0)
                    stats["total_bytes"] = data.get("total_bytes_processed", 0)
                    stats["snapshot_id"] = data.get("snapshot_id")
        except (json.JSONDecodeError, KeyError):
            pass
        return stats

    def _format_bytes(self, bytes_val: int) -> str:
        """Format bytes to human readable format."""
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{bytes_val / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"

    async def _dump_site_database(self, site: str, site_path: str) -> tuple[str | None, list[str]]:
        """Dump database for a site if it has one. Returns (dump_path, log_messages)."""
        outputs = []
        dump_path = None

        # Find database container for this site
        find_db_cmd = f"docker ps --format '{{{{.Names}}}}' | grep -E '^{site}[-_](db|mysql|mariadb)' | head -1"
        result = await asyncio.to_thread(self.ssh.execute, find_db_cmd)
        container = result.stdout.strip()

        if not container:
            outputs.append(f"[{site}] No database container found, skipping DB dump")
            return None, outputs

        outputs.append(f"[{site}] Found database container: {container}")

        # Get database credentials
        get_pass_cmd = f"docker exec {container} printenv MYSQL_PASSWORD 2>/dev/null || docker exec {container} printenv MYSQL_ROOT_PASSWORD 2>/dev/null"
        pass_result = await asyncio.to_thread(self.ssh.execute, get_pass_cmd)
        db_pass = pass_result.stdout.strip()

        if not db_pass:
            outputs.append(f"[{site}] WARNING: Could not find database password, skipping DB dump")
            return None, outputs

        # Create dump
        dump_path = f"{site_path}/.db-backup.sql"
        get_user_cmd = f"docker exec {container} printenv MYSQL_USER 2>/dev/null || echo root"
        user_result = await asyncio.to_thread(self.ssh.execute, get_user_cmd)
        db_user = user_result.stdout.strip() or "root"

        outputs.append(f"[{site}] Dumping database...")
        dump_cmd = f"docker exec {container} mysqldump -u{db_user} -p'{db_pass}' --single-transaction --quick --all-databases > {dump_path} 2>/dev/null"
        dump_result = await asyncio.to_thread(self.ssh.execute, dump_cmd, timeout=300)

        if dump_result.exit_code != 0:
            outputs.append(f"[{site}] WARNING: Database dump failed, continuing without DB")
            # Clean up failed dump
            await asyncio.to_thread(self.ssh.execute, f"rm -f {dump_path}")
            return None, outputs

        # Get dump size
        size_result = await asyncio.to_thread(self.ssh.execute, f"stat -c%s {dump_path} 2>/dev/null")
        if size_result.exit_code == 0:
            dump_size = int(size_result.stdout.strip())
            outputs.append(f"[{site}] Database dump created: {self._format_bytes(dump_size)}")

        return dump_path, outputs

    async def backup_site(self, site: str) -> BackupActionResponse:
        """Backup a single site including database dump if available."""
        start_time = time.time()
        outputs = []
        db_dump_path = None

        site_path = f"{self.SITES_ROOT}/{site}"

        # Check if site exists
        outputs.append(f"[{site}] Checking site directory...")
        check_result = await asyncio.to_thread(
            self.ssh.execute, f"test -d {site_path} && echo exists || echo missing"
        )
        if "missing" in check_result.stdout:
            outputs.append(f"[{site}] ERROR: Site directory not found: {site_path}")
            return BackupActionResponse(
                status="error",
                output="\n".join(outputs),
                snapshot_id=None,
                duration_seconds=time.time() - start_time,
            )

        outputs.append(f"[{site}] Starting backup of {site_path}")
        outputs.append(f"[{site}] Repository: {self.RESTIC_REPO}")

        # Dump database if site has one
        db_dump_path, db_outputs = await self._dump_site_database(site, site_path)
        outputs.extend(db_outputs)

        # Get directory size first
        size_result = await asyncio.to_thread(
            self.ssh.execute, f"du -sh {site_path} 2>/dev/null | cut -f1"
        )
        dir_size = size_result.stdout.strip() if size_result.exit_code == 0 else "unknown"
        outputs.append(f"[{site}] Directory size: {dir_size}")
        outputs.append(f"[{site}] Running restic backup...")

        # Run restic backup
        cmd = f"{self._restic_env()} restic backup {site_path} --tag site:{site} --json"
        result = await asyncio.to_thread(self.ssh.execute, cmd, timeout=600)

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            outputs.append(f"[{site}] FAILED: {error_msg}")

            # Clean up database dump if created
            if db_dump_path:
                await asyncio.to_thread(self.ssh.execute, f"rm -f {db_dump_path}")

            # Record failure
            await self._record_run(site, JobType.SITE, BackupStatus.FAIL, start_time, error=error_msg)

            return BackupActionResponse(
                status="error",
                output="\n".join(outputs),
                snapshot_id=None,
                duration_seconds=time.time() - start_time,
            )

        # Parse backup statistics
        stats = self._parse_backup_stats(result.stdout)
        snapshot_id = stats["snapshot_id"]

        # Clean up database dump after successful backup
        if db_dump_path:
            await asyncio.to_thread(self.ssh.execute, f"rm -f {db_dump_path}")
            outputs.append(f"[{site}] Database dump cleaned up")

        # Build verbose output
        outputs.append(f"[{site}] Backup completed successfully!")
        outputs.append(f"[{site}] Snapshot ID: {snapshot_id or 'unknown'}")
        outputs.append(f"[{site}] Files: {stats['files_new']} new, {stats['files_changed']} changed, {stats['files_unmodified']} unmodified")
        outputs.append(f"[{site}] Directories: {stats['dirs_new']} new, {stats['dirs_changed']} changed")
        outputs.append(f"[{site}] Total processed: {stats['total_files']} files, {self._format_bytes(stats['total_bytes'])}")
        outputs.append(f"[{site}] Data added to repo: {self._format_bytes(stats['data_added'])}")

        duration = time.time() - start_time
        outputs.append(f"[{site}] Duration: {duration:.1f}s")

        # Record success
        await self._record_run(site, JobType.SITE, BackupStatus.OK, start_time, snapshot_id=snapshot_id)

        return BackupActionResponse(
            status="success",
            output="\n".join(outputs),
            snapshot_id=snapshot_id,
            duration_seconds=duration,
        )

    async def backup_all_sites(self) -> BackupActionResponse:
        """Backup all sites sequentially."""
        start_time = time.time()
        outputs = []

        # Get list of sites
        result = await asyncio.to_thread(
            self.ssh.execute, f"ls -1 {self.SITES_ROOT}"
        )
        if result.exit_code != 0:
            return BackupActionResponse(
                status="error",
                output=f"Failed to list sites: {result.stderr}",
                snapshot_id=None,
                duration_seconds=time.time() - start_time,
            )

        sites = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
        outputs.append(f"Found {len(sites)} sites to backup")

        success_count = 0
        fail_count = 0

        for site in sites:
            outputs.append(f"\n--- Backing up {site} ---")
            site_result = await self.backup_site(site)
            outputs.append(site_result.output)
            if site_result.status == "success":
                success_count += 1
            else:
                fail_count += 1

        outputs.append(f"\n=== Summary: {success_count} succeeded, {fail_count} failed ===")

        return BackupActionResponse(
            status="success" if fail_count == 0 else "error",
            output="\n".join(outputs),
            snapshot_id=None,
            duration_seconds=time.time() - start_time,
        )

    async def backup_system(self) -> BackupActionResponse:
        """Full system backup for catastrophic recovery."""
        start_time = time.time()
        outputs = []

        outputs.append("[SYSTEM] Starting full system backup...")
        outputs.append("[SYSTEM] Target: /opt (all sites, gateway, data)")
        outputs.append(f"[SYSTEM] Repository: {self.RESTIC_REPO}")

        # Get directory size
        size_result = await asyncio.to_thread(
            self.ssh.execute, "du -sh /opt 2>/dev/null | cut -f1"
        )
        dir_size = size_result.stdout.strip() if size_result.exit_code == 0 else "unknown"
        outputs.append(f"[SYSTEM] Directory size: {dir_size}")
        outputs.append("[SYSTEM] Running restic backup (this may take several minutes)...")

        # Backup entire /opt directory
        cmd = f"{self._restic_env()} restic backup /opt --tag type:system --tag scope:full --json"
        result = await asyncio.to_thread(self.ssh.execute, cmd, timeout=1800)  # 30 min timeout

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            outputs.append(f"[SYSTEM] FAILED: {error_msg}")

            await self._record_run("system", JobType.SYSTEM, BackupStatus.FAIL, start_time, error=error_msg)

            return BackupActionResponse(
                status="error",
                output="\n".join(outputs),
                snapshot_id=None,
                duration_seconds=time.time() - start_time,
            )

        # Parse backup statistics
        stats = self._parse_backup_stats(result.stdout)
        snapshot_id = stats["snapshot_id"]

        # Build verbose output
        outputs.append("[SYSTEM] Backup completed successfully!")
        outputs.append(f"[SYSTEM] Snapshot ID: {snapshot_id or 'unknown'}")
        outputs.append(f"[SYSTEM] Files: {stats['files_new']} new, {stats['files_changed']} changed, {stats['files_unmodified']} unmodified")
        outputs.append(f"[SYSTEM] Directories: {stats['dirs_new']} new, {stats['dirs_changed']} changed")
        outputs.append(f"[SYSTEM] Total processed: {stats['total_files']} files, {self._format_bytes(stats['total_bytes'])}")
        outputs.append(f"[SYSTEM] Data added to repo: {self._format_bytes(stats['data_added'])}")

        duration = time.time() - start_time
        outputs.append(f"[SYSTEM] Duration: {duration:.1f}s")

        await self._record_run("system", JobType.SYSTEM, BackupStatus.OK, start_time, snapshot_id=snapshot_id)

        return BackupActionResponse(
            status="success",
            output="\n".join(outputs),
            snapshot_id=snapshot_id,
            duration_seconds=duration,
        )

    async def restore_site(self, site: str, snapshot_id: str) -> BackupActionResponse:
        """Restore a site from a restic snapshot."""
        start_time = time.time()
        outputs = []

        site_path = f"{self.SITES_ROOT}/{site}"
        outputs.append(f"Restoring site {site} from snapshot {snapshot_id}")

        # Stop site containers first
        outputs.append("Stopping site containers...")
        stop_result = await asyncio.to_thread(
            self.ssh.execute,
            f"cd {site_path} && docker compose down 2>/dev/null || true"
        )

        # Restore from snapshot
        outputs.append("Restoring files from backup...")
        cmd = f"{self._restic_env()} restic restore {snapshot_id} --target / --include {site_path}"
        result = await asyncio.to_thread(self.ssh.execute, cmd, timeout=600)

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            outputs.append(f"Restore failed: {error_msg}")
            return BackupActionResponse(
                status="error",
                output="\n".join(outputs),
                snapshot_id=None,
                duration_seconds=time.time() - start_time,
            )

        # Start site containers
        outputs.append("Starting site containers...")
        start_result = await asyncio.to_thread(
            self.ssh.execute,
            f"cd {site_path} && docker compose up -d 2>&1"
        )
        outputs.append(start_result.stdout or "Containers started")

        outputs.append(f"Site {site} restored successfully")

        return BackupActionResponse(
            status="success",
            output="\n".join(outputs),
            snapshot_id=snapshot_id,
            duration_seconds=time.time() - start_time,
        )

    async def restore_system(self, snapshot_id: str) -> BackupActionResponse:
        """Restore entire system from a snapshot. USE WITH EXTREME CAUTION."""
        start_time = time.time()
        outputs = []

        outputs.append(f"!!! SYSTEM RESTORE from snapshot {snapshot_id} !!!")
        outputs.append("This will overwrite files in /opt")

        # Stop all containers
        outputs.append("Stopping all site containers...")
        sites_result = await asyncio.to_thread(
            self.ssh.execute, f"ls -1 {self.SITES_ROOT}"
        )
        sites = [s.strip() for s in sites_result.stdout.strip().split("\n") if s.strip()]

        for site in sites:
            await asyncio.to_thread(
                self.ssh.execute,
                f"cd {self.SITES_ROOT}/{site} && docker compose down 2>/dev/null || true"
            )

        # Restore from snapshot
        outputs.append("Restoring system files...")
        cmd = f"{self._restic_env()} restic restore {snapshot_id} --target /"
        result = await asyncio.to_thread(self.ssh.execute, cmd, timeout=3600)  # 1 hour timeout

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            outputs.append(f"System restore failed: {error_msg}")
            return BackupActionResponse(
                status="error",
                output="\n".join(outputs),
                snapshot_id=None,
                duration_seconds=time.time() - start_time,
            )

        # Restart all containers
        outputs.append("Restarting all site containers...")
        for site in sites:
            await asyncio.to_thread(
                self.ssh.execute,
                f"cd {self.SITES_ROOT}/{site} && docker compose up -d 2>/dev/null || true"
            )

        outputs.append("System restore complete")

        return BackupActionResponse(
            status="success",
            output="\n".join(outputs),
            snapshot_id=snapshot_id,
            duration_seconds=time.time() - start_time,
        )

    async def list_snapshots(self, site: str | None = None) -> list[SnapshotInfo]:
        """List available restic snapshots."""
        cmd = f"{self._restic_env()} restic snapshots --json"
        if site:
            cmd += f" --tag site:{site}"

        result = await asyncio.to_thread(self.ssh.execute, cmd, timeout=60)

        if result.exit_code != 0:
            logger.error(f"Failed to list snapshots: {result.stderr}")
            return []

        try:
            snapshots_data = json.loads(result.stdout)
            return [
                SnapshotInfo(
                    id=s["id"],
                    short_id=s["short_id"],
                    time=datetime.fromisoformat(s["time"].replace("Z", "+00:00")),
                    hostname=s.get("hostname", "unknown"),
                    tags=s.get("tags", []),
                    paths=s.get("paths", []),
                )
                for s in snapshots_data
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse snapshots: {e}")
            return []

    def _parse_snapshot_id(self, output: str) -> str | None:
        """Parse snapshot ID from restic JSON output."""
        try:
            # Restic outputs multiple JSON objects, find the summary
            for line in output.strip().split("\n"):
                if line.strip():
                    data = json.loads(line)
                    if data.get("message_type") == "summary":
                        return data.get("snapshot_id")
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: try to find snapshot ID in plain text
        match = re.search(r"snapshot ([a-f0-9]{8,})", output, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    async def _record_run(
        self,
        site: str,
        job_type: JobType,
        status: BackupStatus,
        start_time: float,
        snapshot_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """Record a backup run to the database."""
        now = datetime.now(timezone.utc)
        started_at = datetime.fromtimestamp(start_time, tz=timezone.utc)

        run = BackupRunIn(
            site=site,
            job_type=job_type,
            status=status,
            started_at=started_at,
            ended_at=now,
            backup_id=snapshot_id,
            repo=self.RESTIC_REPO,
            error=error,
        )
        await self.backup_service.store_run_async(run)
