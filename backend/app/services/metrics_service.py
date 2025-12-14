from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.config import Settings
from app.schemas.metrics import ContainerMetrics, MetricsResponse, SiteMetrics
from app.services.cache import TimedCache
from app.services.ssh_client import SSHClientManager


logger = logging.getLogger(__name__)


class MetricsService:
    """Service for collecting Docker container metrics."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.ssh = SSHClientManager(settings)
        self.cache = TimedCache[dict[str, ContainerMetrics]](ttl_seconds=10)

    def get_container_metrics(self, force_refresh: bool = False) -> dict[str, ContainerMetrics]:
        """Get metrics for all running containers."""
        def builder() -> dict[str, ContainerMetrics]:
            return self._collect_metrics()

        return self.cache.get(builder, force_refresh=force_refresh)

    def get_site_metrics(self, sites: list[str], containers_by_site: dict[str, list[str]]) -> list[SiteMetrics]:
        """Get aggregated metrics for sites."""
        all_metrics = self.get_container_metrics()
        site_metrics: list[SiteMetrics] = []

        for site_name in sites:
            container_names = containers_by_site.get(site_name, [])
            containers: list[ContainerMetrics] = []
            total_cpu = 0.0
            total_memory = 0.0

            for container_name in container_names:
                if container_name in all_metrics:
                    metrics = all_metrics[container_name]
                    containers.append(metrics)
                    total_cpu += metrics.cpu_percent
                    total_memory += metrics.memory_usage_mb

            site_metrics.append(
                SiteMetrics(
                    site_name=site_name,
                    containers=containers,
                    total_cpu_percent=total_cpu,
                    total_memory_mb=total_memory,
                )
            )

        return site_metrics

    def _collect_metrics(self) -> dict[str, ContainerMetrics]:
        """Collect metrics from docker stats."""
        result = self.ssh.execute(
            "docker stats --no-stream --format '{{json .}}'",
            timeout=30,
        )

        metrics: dict[str, ContainerMetrics] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                container_metrics = self._parse_stats(data)
                if container_metrics:
                    metrics[container_metrics.container_name] = container_metrics
            except json.JSONDecodeError:
                logger.warning("Failed to parse docker stats line: %s", line)
                continue

        return metrics

    def _parse_stats(self, data: dict[str, Any]) -> ContainerMetrics | None:
        """Parse docker stats JSON output."""
        name = data.get("Name", "").strip()
        if not name:
            return None

        cpu_percent = self._parse_percent(data.get("CPUPerc", "0%"))
        mem_percent = self._parse_percent(data.get("MemPerc", "0%"))

        mem_usage, mem_limit = self._parse_memory(data.get("MemUsage", "0B / 0B"))
        net_rx, net_tx = self._parse_network(data.get("NetIO", "0B / 0B"))
        block_read, block_write = self._parse_network(data.get("BlockIO", "0B / 0B"))

        return ContainerMetrics(
            container_name=name,
            cpu_percent=cpu_percent,
            memory_usage_mb=mem_usage,
            memory_limit_mb=mem_limit,
            memory_percent=mem_percent,
            network_rx_mb=net_rx,
            network_tx_mb=net_tx,
            block_read_mb=block_read,
            block_write_mb=block_write,
        )

    @staticmethod
    def _parse_percent(value: str) -> float:
        """Parse percentage string like '0.12%' to float."""
        try:
            return float(value.rstrip("%"))
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _parse_size(value: str) -> float:
        """Parse size string like '1.5GiB' or '100MiB' to MB."""
        value = value.strip()
        if not value:
            return 0.0

        multipliers = {
            "B": 1 / (1024 * 1024),
            "KB": 1 / 1024,
            "KiB": 1 / 1024,
            "MB": 1,
            "MiB": 1,
            "GB": 1024,
            "GiB": 1024,
            "TB": 1024 * 1024,
            "TiB": 1024 * 1024,
        }

        match = re.match(r"([\d.]+)\s*([A-Za-z]+)", value)
        if not match:
            return 0.0

        try:
            number = float(match.group(1))
            unit = match.group(2)
            multiplier = multipliers.get(unit, 1)
            return number * multiplier
        except (ValueError, AttributeError):
            return 0.0

    def _parse_memory(self, value: str) -> tuple[float, float]:
        """Parse memory usage string like '100MiB / 1GiB'."""
        parts = value.split("/")
        if len(parts) != 2:
            return 0.0, 0.0
        return self._parse_size(parts[0]), self._parse_size(parts[1])

    def _parse_network(self, value: str) -> tuple[float, float]:
        """Parse network IO string like '100MB / 50MB'."""
        parts = value.split("/")
        if len(parts) != 2:
            return 0.0, 0.0
        return self._parse_size(parts[0]), self._parse_size(parts[1])
