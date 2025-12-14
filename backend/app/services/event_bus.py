from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any, Callable, Awaitable
from weakref import WeakSet


logger = logging.getLogger(__name__)


class EventType(str, Enum):
    SITES_UPDATE = "sites.update"
    GRAPH_UPDATE = "graph.update"
    ACTION_OUTPUT = "action.output"
    ERROR = "error"


class EventBus:
    """Pub/sub event bus for WebSocket broadcasts."""

    def __init__(self):
        self._subscribers: dict[str, WeakSet[Callable[[dict[str, Any]], Awaitable[None]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe a callback to a topic."""
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = WeakSet()
            self._subscribers[topic].add(callback)
            logger.debug("Subscriber added to topic: %s", topic)

    async def unsubscribe(
        self,
        topic: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Unsubscribe a callback from a topic."""
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(callback)
                logger.debug("Subscriber removed from topic: %s", topic)

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers of a topic."""
        async with self._lock:
            subscribers = list(self._subscribers.get(topic, []))

        if not subscribers:
            return

        message = {
            "type": topic,
            "data": data,
        }

        for callback in subscribers:
            try:
                await callback(message)
            except Exception as e:
                logger.warning("Failed to deliver message to subscriber: %s", e)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers across all topics."""
        async with self._lock:
            all_callbacks = set()
            for subscribers in self._subscribers.values():
                all_callbacks.update(subscribers)

        for callback in all_callbacks:
            try:
                await callback(data)
            except Exception as e:
                logger.warning("Failed to broadcast message: %s", e)


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.active_connections: WeakSet = WeakSet()
        self._lock = asyncio.Lock()

    async def connect(self, websocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info("WebSocket connected. Total: %d", len(self.active_connections))

    async def disconnect(self, websocket) -> None:
        """Handle WebSocket disconnection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(self.active_connections))

    async def send_personal(self, websocket, message: dict[str, Any]) -> None:
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning("Failed to send personal message: %s", e)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        async with self._lock:
            connections = list(self.active_connections)

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("Failed to broadcast to connection: %s", e)


# Global event bus instance
_event_bus: EventBus | None = None
_connection_manager: ConnectionManager | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def get_connection_manager() -> ConnectionManager:
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager(get_event_bus())
    return _connection_manager
