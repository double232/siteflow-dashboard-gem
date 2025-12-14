from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from app.dependencies import get_audit_service
from app.schemas.audit import AuditLogFilter, AuditLogResponse


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs", response_model=AuditLogResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    action_type: str | None = Query(None, description="Filter by action type"),
    target_type: str | None = Query(None, description="Filter by target type"),
    target_name: str | None = Query(None, description="Filter by target name (partial match)"),
    status: str | None = Query(None, description="Filter by status"),
    start_date: datetime | None = Query(None, description="Filter logs after this date"),
    end_date: datetime | None = Query(None, description="Filter logs before this date"),
):
    """Get paginated audit logs with optional filters."""
    service = get_audit_service()
    filters = AuditLogFilter(
        action_type=action_type,
        target_type=target_type,
        target_name=target_name,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return service.get_logs(filters=filters, page=page, page_size=page_size)


@router.post("/cleanup")
async def cleanup_old_logs():
    """Manually trigger cleanup of old audit logs."""
    service = get_audit_service()
    deleted = service.cleanup_old_logs()
    return {"deleted": deleted, "message": f"Deleted {deleted} old audit log entries"}
