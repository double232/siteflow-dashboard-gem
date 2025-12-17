from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    CONTAINER_START = "container_start"
    CONTAINER_STOP = "container_stop"
    CONTAINER_RESTART = "container_restart"
    CONTAINER_LOGS = "container_logs"
    CADDY_RELOAD = "caddy_reload"
    SITE_START = "site_start"
    SITE_STOP = "site_stop"
    SITE_RESTART = "site_restart"
    SITE_PROVISION = "site_provision"
    SITE_DEPROVISION = "site_deprovision"
    SITE_CONFIG = "site_config"
    ROUTE_ADD = "route_add"
    ROUTE_REMOVE = "route_remove"
    BACKUP_RUN = "backup_run"
    SITE_RESTORE = "site_restore"


class TargetType(str, Enum):
    CONTAINER = "container"
    SITE = "site"
    CADDY = "caddy"
    SYSTEM = "system"
    ROUTE = "route"


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


class AuditLogEntry(BaseModel):
    id: int
    timestamp: datetime
    action_type: str
    target_type: str
    target_name: str
    status: str
    user_email: str | None = None
    output: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class AuditLogFilter(BaseModel):
    action_type: str | None = None
    target_type: str | None = None
    target_name: str | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class AuditLogResponse(BaseModel):
    logs: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    total_pages: int


class AuditLogCreate(BaseModel):
    action_type: str
    target_type: str
    target_name: str
    status: str = ActionStatus.PENDING
    output: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
