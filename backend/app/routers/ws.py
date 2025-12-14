from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.dependencies import get_audit_service, get_hetzner_service
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.services.event_bus import EventType, get_connection_manager
from app.services.monitor import get_monitor


logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    manager = get_connection_manager()
    await manager.connect(websocket)

    try:
        while True:
            try:
                data = await websocket.receive_json()
                await handle_message(websocket, data)
            except json.JSONDecodeError:
                await manager.send_personal(websocket, {
                    "type": EventType.ERROR.value,
                    "data": {"message": "Invalid JSON"},
                })
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        await manager.disconnect(websocket)


async def handle_message(websocket: WebSocket, data: dict) -> None:
    """Handle incoming WebSocket messages."""
    manager = get_connection_manager()
    message_type = data.get("type", "")

    if message_type == "ping":
        await manager.send_personal(websocket, {"type": "pong"})

    elif message_type == "subscribe":
        topic = data.get("topic")
        if topic:
            logger.debug("Client subscribed to: %s", topic)
            await manager.send_personal(websocket, {
                "type": "subscribed",
                "data": {"topic": topic},
            })

    elif message_type == "unsubscribe":
        topic = data.get("topic")
        if topic:
            logger.debug("Client unsubscribed from: %s", topic)
            await manager.send_personal(websocket, {
                "type": "unsubscribed",
                "data": {"topic": topic},
            })

    elif message_type == "action.start":
        await handle_action(websocket, data)

    else:
        await manager.send_personal(websocket, {
            "type": EventType.ERROR.value,
            "data": {"message": f"Unknown message type: {message_type}"},
        })


async def handle_action(websocket: WebSocket, data: dict) -> None:
    """Handle container action requests with streaming output."""
    manager = get_connection_manager()
    hetzner = get_hetzner_service()
    audit = get_audit_service()
    settings = get_settings()

    container = data.get("container")
    action = data.get("action")

    if not container or not action:
        await manager.send_personal(websocket, {
            "type": EventType.ERROR.value,
            "data": {"message": "Missing container or action"},
        })
        return

    action_type_map = {
        "start": ActionType.CONTAINER_START,
        "stop": ActionType.CONTAINER_STOP,
        "restart": ActionType.CONTAINER_RESTART,
        "logs": ActionType.CONTAINER_LOGS,
    }

    if action not in action_type_map:
        await manager.send_personal(websocket, {
            "type": EventType.ERROR.value,
            "data": {"message": f"Invalid action: {action}"},
        })
        return

    import time
    start_time = time.time()

    try:
        # Send action started notification
        await manager.send_personal(websocket, {
            "type": EventType.ACTION_OUTPUT.value,
            "data": {
                "container": container,
                "action": action,
                "status": "started",
                "output": f"Starting {action} on {container}...\n",
            },
        })

        # Execute the action
        output = await asyncio.to_thread(
            hetzner.run_container_action, container, action
        )

        duration_ms = (time.time() - start_time) * 1000

        # Log successful action
        audit.log_action(
            action_type=action_type_map[action],
            target_type=TargetType.CONTAINER,
            target_name=container,
            status=ActionStatus.SUCCESS,
            output=output,
            duration_ms=duration_ms,
        )

        # Send completion with output
        await manager.send_personal(websocket, {
            "type": EventType.ACTION_OUTPUT.value,
            "data": {
                "container": container,
                "action": action,
                "status": "completed",
                "output": output,
                "duration_ms": duration_ms,
            },
        })

        # Force a state update broadcast
        monitor = get_monitor(settings)
        await monitor.force_broadcast()

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        # Log failed action
        audit.log_action(
            action_type=action_type_map[action],
            target_type=TargetType.CONTAINER,
            target_name=container,
            status=ActionStatus.FAILURE,
            error_message=str(e),
            duration_ms=duration_ms,
        )

        # Send error
        await manager.send_personal(websocket, {
            "type": EventType.ACTION_OUTPUT.value,
            "data": {
                "container": container,
                "action": action,
                "status": "failed",
                "error": str(e),
                "duration_ms": duration_ms,
            },
        })
