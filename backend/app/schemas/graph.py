from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NodeMetrics(BaseModel):
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_limit_mb: float = 0.0


class NodeBackupStatus(BaseModel):
    status: str = "unknown"
    last_backup: datetime | None = None
    hours_since_backup: float | None = None
    backup_size_mb: float | None = None


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    status: str = "unknown"
    meta: dict[str, Any] = Field(default_factory=dict)
    metrics: NodeMetrics | None = None
    backup: NodeBackupStatus | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    nas_connected: bool = False
    nas_error: str | None = None
