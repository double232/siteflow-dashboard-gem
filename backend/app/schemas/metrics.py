from __future__ import annotations

from pydantic import BaseModel, Field


class ContainerMetrics(BaseModel):
    container_name: str
    cpu_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_limit_mb: float = 0.0
    memory_percent: float = 0.0
    network_rx_mb: float = 0.0
    network_tx_mb: float = 0.0
    block_read_mb: float = 0.0
    block_write_mb: float = 0.0


class SiteMetrics(BaseModel):
    site_name: str
    containers: list[ContainerMetrics] = Field(default_factory=list)
    total_cpu_percent: float = 0.0
    total_memory_mb: float = 0.0


class MetricsResponse(BaseModel):
    sites: list[SiteMetrics]
    timestamp: float
