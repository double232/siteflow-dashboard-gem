from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Generator

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import AuditLog, get_database
from app.schemas.audit import (
    ActionStatus,
    AuditLogCreate,
    AuditLogEntry,
    AuditLogFilter,
    AuditLogResponse,
)


logger = logging.getLogger(__name__)


class AuditService:
    """Service for managing audit logs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = get_database(settings.sqlite_db_path)

    def _get_session(self) -> Session:
        return self.db.get_session()

    def log_action(
        self,
        action_type: str,
        target_type: str,
        target_name: str,
        status: str = ActionStatus.SUCCESS,
        user_email: str | None = None,
        output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        exit_code: int | None = None,
        stderr: str | None = None,
    ) -> AuditLogEntry:
        """Log an action to the audit log with structured logging.

        Args:
            action_type: Type of action (e.g., site_start, container_stop)
            target_type: Type of target (e.g., site, container)
            target_name: Name of the target
            status: Action status (success, failure, pending)
            user_email: Email of user who triggered the action
            output: Command output (stdout)
            error_message: Error message if action failed
            metadata: Additional metadata dict
            duration_ms: Action duration in milliseconds
            exit_code: Exit code from remote command
            stderr: Standard error output from command
        """
        session = self._get_session()
        try:
            # Truncate output if too long
            if output and len(output) > self.settings.audit_max_output_length:
                output = output[: self.settings.audit_max_output_length] + "... [truncated]"

            # Truncate stderr if too long
            if stderr and len(stderr) > self.settings.audit_max_output_length:
                stderr = stderr[: self.settings.audit_max_output_length] + "... [truncated]"

            # Build metadata with exit_code and stderr if provided
            full_metadata = metadata.copy() if metadata else {}
            if exit_code is not None:
                full_metadata["exit_code"] = exit_code
            if stderr:
                full_metadata["stderr"] = stderr

            log_entry = AuditLog(
                timestamp=datetime.utcnow(),
                action_type=action_type,
                target_type=target_type,
                target_name=target_name,
                status=status,
                user_email=user_email,
                output=output,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            if full_metadata:
                log_entry.set_metadata(full_metadata)

            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)

            # Emit structured log for monitoring/alerting
            log_data = {
                "action": action_type,
                "target_type": target_type,
                "target": target_name,
                "status": status,
                "duration_ms": round(duration_ms, 2) if duration_ms else None,
                "user": user_email,
            }
            if exit_code is not None:
                log_data["exit_code"] = exit_code
            if stderr:
                log_data["stderr"] = stderr[:500] if len(stderr) > 500 else stderr  # Truncate for log line
            if error_message:
                log_data["error"] = error_message[:200] if len(error_message) > 200 else error_message

            if status == ActionStatus.SUCCESS:
                logger.info(
                    f"Action completed: {action_type} on {target_type}/{target_name}",
                    extra=log_data,
                )
            else:
                logger.warning(
                    f"Action failed: {action_type} on {target_type}/{target_name}",
                    extra=log_data,
                )

            return AuditLogEntry(
                id=log_entry.id,
                timestamp=log_entry.timestamp,
                action_type=log_entry.action_type,
                target_type=log_entry.target_type,
                target_name=log_entry.target_name,
                status=log_entry.status,
                user_email=log_entry.user_email,
                output=log_entry.output,
                error_message=log_entry.error_message,
                metadata=log_entry.get_metadata(),
                duration_ms=log_entry.duration_ms,
            )
        finally:
            session.close()

    def get_logs(
        self,
        filters: AuditLogFilter | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogResponse:
        """Query audit logs with optional filters and pagination."""
        session = self._get_session()
        try:
            query = session.query(AuditLog)

            if filters:
                if filters.action_type:
                    query = query.filter(AuditLog.action_type == filters.action_type)
                if filters.target_type:
                    query = query.filter(AuditLog.target_type == filters.target_type)
                if filters.target_name:
                    query = query.filter(AuditLog.target_name.ilike(f"%{filters.target_name}%"))
                if filters.status:
                    query = query.filter(AuditLog.status == filters.status)
                if filters.start_date:
                    query = query.filter(AuditLog.timestamp >= filters.start_date)
                if filters.end_date:
                    query = query.filter(AuditLog.timestamp <= filters.end_date)

            total = query.count()
            total_pages = (total + page_size - 1) // page_size

            offset = (page - 1) * page_size
            logs = query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(page_size).all()

            return AuditLogResponse(
                logs=[
                    AuditLogEntry(
                        id=log.id,
                        timestamp=log.timestamp,
                        action_type=log.action_type,
                        target_type=log.target_type,
                        target_name=log.target_name,
                        status=log.status,
                        user_email=log.user_email,
                        output=log.output,
                        error_message=log.error_message,
                        metadata=log.get_metadata(),
                        duration_ms=log.duration_ms,
                    )
                    for log in logs
                ],
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )
        finally:
            session.close()

    def cleanup_old_logs(self) -> int:
        """Delete logs older than the retention period."""
        session = self._get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=self.settings.audit_retention_days)
            deleted = session.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
            session.commit()
            logger.info("Cleaned up %d old audit logs", deleted)
            return deleted
        finally:
            session.close()

    @contextmanager
    def track_action(
        self,
        action_type: str,
        target_type: str,
        target_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Context manager to track an action with timing and status."""
        context: dict[str, Any] = {
            "output": None,
            "error": None,
        }
        start_time = time.time()

        try:
            yield context
            duration_ms = (time.time() - start_time) * 1000
            self.log_action(
                action_type=action_type,
                target_type=target_type,
                target_name=target_name,
                status=ActionStatus.SUCCESS,
                output=context.get("output"),
                metadata=metadata,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.log_action(
                action_type=action_type,
                target_type=target_type,
                target_name=target_name,
                status=ActionStatus.FAILURE,
                output=context.get("output"),
                error_message=str(e),
                metadata=metadata,
                duration_ms=duration_ms,
            )
            raise
