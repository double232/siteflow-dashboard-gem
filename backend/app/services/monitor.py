from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from app.config import Settings
from app.dependencies import (
    get_cloudflare_service,
    get_graph_builder,
    get_hetzner_service,
    get_metrics_service,
    get_nas_service,
)
from app.services.event_bus import EventType, get_connection_manager


logger = logging.getLogger(__name__)


class SiteMonitor:
    """Background task that monitors site changes and broadcasts updates."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.interval = settings.ws_monitor_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_sites_hash: str | None = None
        self._last_graph_hash: str | None = None

    async def start(self) -> None:
        """Start the monitoring background task."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Site monitor started with interval: %.1fs", self.interval)

    async def stop(self) -> None:
        """Stop the monitoring background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Site monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_for_changes()
            except Exception as e:
                logger.error("Monitor check failed: %s", e)

            await asyncio.sleep(self.interval)

    async def _check_for_changes(self) -> None:
        """Check for changes in sites and graph data."""
        connection_manager = get_connection_manager()

        # Skip if no connections
        if not connection_manager.active_connections:
            return

        try:
            # Get current data
            hetzner = get_hetzner_service()
            cloudflare = get_cloudflare_service()
            metrics_service = get_metrics_service()
            nas_service = get_nas_service()
            builder = get_graph_builder()

            # Fetch data in parallel
            sites, cf_status, container_metrics = await asyncio.gather(
                asyncio.to_thread(hetzner.get_sites, False),
                asyncio.to_thread(cloudflare.get_status, False),
                asyncio.to_thread(metrics_service.get_container_metrics, False),
            )

            site_names = [site.name for site in sites.sites]
            nas_status = None
            try:
                nas_status = await asyncio.to_thread(
                    nas_service.get_backup_status, site_names, False
                )
            except Exception:
                pass

            # Check for sites changes
            sites_data = sites.model_dump()
            sites_hash = self._compute_hash(sites_data)

            if sites_hash != self._last_sites_hash:
                self._last_sites_hash = sites_hash
                await connection_manager.broadcast({
                    "type": EventType.SITES_UPDATE.value,
                    "data": sites_data,
                })
                logger.debug("Broadcasted sites update")

            # Check for graph changes
            graph = builder.build(sites, cf_status, container_metrics, nas_status)
            graph_data = graph.model_dump()
            graph_hash = self._compute_hash(graph_data)

            if graph_hash != self._last_graph_hash:
                self._last_graph_hash = graph_hash
                await connection_manager.broadcast({
                    "type": EventType.GRAPH_UPDATE.value,
                    "data": graph_data,
                })
                logger.debug("Broadcasted graph update")

        except Exception as e:
            logger.error("Failed to check for changes: %s", e)

    @staticmethod
    def _compute_hash(data: Any) -> str:
        """Compute a hash of the data for change detection."""
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(json_str.encode()).hexdigest()

    async def force_broadcast(self) -> None:
        """Force a broadcast of current state (e.g., after an action)."""
        self._last_sites_hash = None
        self._last_graph_hash = None
        await self._check_for_changes()


# Global monitor instance
_monitor: SiteMonitor | None = None


def get_monitor(settings: Settings) -> SiteMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SiteMonitor(settings)
    return _monitor
