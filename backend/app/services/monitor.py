from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
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


class CircuitBreaker:
    """Circuit breaker to handle repeated failures gracefully."""

    # Circuit states
    CLOSED = "closed"       # Normal operation, requests flow through
    OPEN = "open"           # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open" # Testing if service recovered

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == self.CLOSED

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        if self._state == self.CLOSED:
            return True

        if self._state == self.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time and (time.time() - self._last_failure_time) >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"Circuit breaker '{self.name}' entering half-open state")
                return True
            return False

        if self._state == self.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record a successful request."""
        if self._state == self.HALF_OPEN:
            logger.info(f"Circuit breaker '{self.name}' recovered, closing circuit")
            self._state = self.CLOSED

        self._failure_count = 0
        self._last_failure_time = None

    def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == self.HALF_OPEN:
            logger.warning(f"Circuit breaker '{self.name}' failed in half-open state, re-opening circuit")
            self._state = self.OPEN
            return

        if self._failure_count >= self.failure_threshold:
            if self._state != self.OPEN:
                logger.error(
                    f"Circuit breaker '{self.name}' OPENED after {self._failure_count} consecutive failures. "
                    f"Will retry in {self.recovery_timeout}s. Last error: {error}"
                )
                self._state = self.OPEN

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for monitoring."""
        return {
            "name": self.name,
            "state": self._state,
            "failure_count": self._failure_count,
            "last_failure_time": self._last_failure_time,
            "threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class SiteMonitor:
    """Background task that monitors site changes and broadcasts updates."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.interval = settings.ws_monitor_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_sites_hash: str | None = None
        self._last_graph_hash: str | None = None
        self._data_stale = False

        # Circuit breakers for each dependency
        self._circuit_breakers = {
            "hetzner": CircuitBreaker("hetzner", failure_threshold=5, recovery_timeout=60.0),
            "cloudflare": CircuitBreaker("cloudflare", failure_threshold=3, recovery_timeout=30.0),
            "metrics": CircuitBreaker("metrics", failure_threshold=3, recovery_timeout=30.0),
            "nas": CircuitBreaker("nas", failure_threshold=3, recovery_timeout=30.0),
        }

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
        """Check for changes in sites and graph data with circuit breaker protection."""
        connection_manager = get_connection_manager()

        # Skip if no connections
        if not connection_manager.active_connections:
            return

        hetzner_cb = self._circuit_breakers["hetzner"]
        cloudflare_cb = self._circuit_breakers["cloudflare"]
        metrics_cb = self._circuit_breakers["metrics"]
        nas_cb = self._circuit_breakers["nas"]

        # Check if critical circuit (hetzner) is open
        if not hetzner_cb.allow_request():
            if not self._data_stale:
                self._data_stale = True
                # Broadcast stale data notification
                await connection_manager.broadcast({
                    "type": "data_stale",
                    "data": {
                        "stale": True,
                        "reason": "Primary data source unavailable",
                        "circuit_breakers": self.get_circuit_status(),
                    },
                })
                logger.warning("Monitor pausing broadcasts - hetzner circuit is open")
            return

        try:
            # Get services
            hetzner = get_hetzner_service()
            cloudflare = get_cloudflare_service()
            metrics_service = get_metrics_service()
            nas_service = get_nas_service()
            builder = get_graph_builder()

            # Fetch sites data (critical)
            sites = None
            try:
                sites = await asyncio.to_thread(hetzner.get_sites, False)
                hetzner_cb.record_success()
            except Exception as e:
                hetzner_cb.record_failure(e)
                logger.error(f"Hetzner fetch failed: {e}")
                raise  # Re-raise to skip the rest

            # Fetch optional data with circuit breakers
            cf_status = None
            if cloudflare_cb.allow_request():
                try:
                    cf_status = await asyncio.to_thread(cloudflare.get_status, False)
                    cloudflare_cb.record_success()
                except Exception as e:
                    cloudflare_cb.record_failure(e)
                    logger.warning(f"Cloudflare fetch failed: {e}")

            container_metrics = None
            if metrics_cb.allow_request():
                try:
                    container_metrics = await asyncio.to_thread(metrics_service.get_container_metrics, False)
                    metrics_cb.record_success()
                except Exception as e:
                    metrics_cb.record_failure(e)
                    logger.warning(f"Metrics fetch failed: {e}")

            nas_status = None
            if nas_cb.allow_request():
                try:
                    site_names = [site.name for site in sites.sites]
                    nas_status = await asyncio.to_thread(nas_service.get_backup_status, site_names, False)
                    nas_cb.record_success()
                except Exception as e:
                    nas_cb.record_failure(e)
                    logger.warning(f"NAS fetch failed: {e}")

            # Mark data as fresh if it was stale
            if self._data_stale:
                self._data_stale = False
                await connection_manager.broadcast({
                    "type": "data_stale",
                    "data": {"stale": False},
                })
                logger.info("Monitor resumed - data is now fresh")

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

    def get_circuit_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: cb.get_status() for name, cb in self._circuit_breakers.items()}

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
