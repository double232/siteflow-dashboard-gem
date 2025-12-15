from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import socketio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])

# Uptime Kuma config
KUMA_URL = os.getenv("KUMA_URL", "http://uptime-kuma:3001")
KUMA_USERNAME = os.getenv("KUMA_USERNAME", "admin")
KUMA_PASSWORD = os.getenv("KUMA_PASSWORD", "")


class HeartbeatEntry(BaseModel):
    status: int  # 0=down, 1=up, 2=pending
    time: str
    ping: int | None = None


class MonitorStatus(BaseModel):
    up: bool
    ping: int | None = None
    uptime: float = 0.0  # Percentage 0-100
    heartbeats: list[HeartbeatEntry] = []  # Last N heartbeats for visualization


class HealthResponse(BaseModel):
    monitors: dict[str, MonitorStatus]


class CreateMonitorRequest(BaseModel):
    site_name: str
    domain: str


class CreateMonitorResponse(BaseModel):
    success: bool
    message: str
    monitor_id: int | None = None


class DeleteMonitorResponse(BaseModel):
    success: bool
    message: str


async def get_kuma_status() -> dict[str, MonitorStatus]:
    """Fetch monitor status from Uptime Kuma via socket.io."""
    sio = socketio.AsyncClient()
    monitors: dict[str, MonitorStatus] = {}
    heartbeats: dict[str, list] = {}  # Store full heartbeat history
    monitor_list: list[dict] = []

    data_received = asyncio.Event()

    @sio.on("heartbeatList")
    async def on_heartbeat_list(monitor_id, data: list, *args):
        if data:
            # Store all heartbeats (Kuma sends last ~50)
            heartbeats[str(monitor_id)] = data

    @sio.on("monitorList")
    async def on_monitor_list(data: dict):
        nonlocal monitor_list
        monitor_list = list(data.values())
        logger.info(f"Received {len(monitor_list)} monitors from Kuma")
        data_received.set()

    try:
        logger.info(f"Connecting to Kuma at {KUMA_URL}")
        await asyncio.wait_for(sio.connect(KUMA_URL), timeout=5)

        # Login
        logger.info(f"Logging in as {KUMA_USERNAME}")
        result = await sio.call(
            "login",
            {"username": KUMA_USERNAME, "password": KUMA_PASSWORD, "token": ""},
            timeout=10,
        )

        if not result.get("ok"):
            logger.error(f"Login failed: {result.get('msg', 'Unknown error')}")
            return monitors

        logger.info("Login successful, waiting for monitor list...")

        # Wait for monitor list (sent automatically after login)
        try:
            await asyncio.wait_for(data_received.wait(), timeout=5)
        except asyncio.TimeoutError:
            # Give it a bit more time
            await asyncio.sleep(1)

        # Wait for heartbeat data to arrive
        await asyncio.sleep(2)

        logger.info(f"Building response from {len(monitor_list)} monitors, {len(heartbeats)} heartbeats")

        # Build response
        for monitor in monitor_list:
            name = monitor.get("name", "")
            monitor_id = str(monitor.get("id"))
            hb_list = heartbeats.get(monitor_id, [])

            # Get latest heartbeat for current status
            latest_hb = hb_list[-1] if hb_list else {}
            status = latest_hb.get("status", 0) if latest_hb else 0
            ping = latest_hb.get("ping") if latest_hb else None

            # Calculate uptime percentage from heartbeat history
            if hb_list:
                up_count = sum(1 for hb in hb_list if hb.get("status") == 1)
                uptime = (up_count / len(hb_list)) * 100
            else:
                uptime = 0.0

            # Convert heartbeats to our format (last 30 for display)
            heartbeat_entries = [
                HeartbeatEntry(
                    status=hb.get("status", 0),
                    time=hb.get("time", ""),
                    ping=hb.get("ping"),
                )
                for hb in hb_list[-30:]  # Last 30 heartbeats
            ]

            monitors[name] = MonitorStatus(
                up=status == 1,
                ping=ping,
                uptime=round(uptime, 1),
                heartbeats=heartbeat_entries,
            )

    except Exception as e:
        logger.error(f"Error fetching Kuma status: {type(e).__name__}: {e}")
    finally:
        if sio.connected:
            await sio.disconnect()

    return monitors


async def create_kuma_monitor(site_name: str, domain: str) -> tuple[bool, str, int | None]:
    """Create a new HTTP monitor in Uptime Kuma."""
    sio = socketio.AsyncClient()
    connected = asyncio.Event()

    @sio.on("connect")
    async def on_connect():
        connected.set()

    try:
        await asyncio.wait_for(sio.connect(KUMA_URL), timeout=5)
        await asyncio.wait_for(connected.wait(), timeout=5)

        # Login
        result = await sio.call(
            "login",
            {"username": KUMA_USERNAME, "password": KUMA_PASSWORD, "token": ""},
            timeout=10,
        )

        if not result.get("ok"):
            return False, f"Login failed: {result.get('msg', 'Unknown error')}", None

        # Create monitor
        monitor_data = {
            "type": "http",
            "name": site_name,
            "url": f"https://{domain}",
            "method": "GET",
            "interval": 60,
            "retryInterval": 60,
            "resendInterval": 0,
            "maxretries": 3,
            "timeout": 30,
            "active": True,
            "accepted_statuscodes": ["200-299", "301", "302"],
        }

        result = await sio.call("add", monitor_data, timeout=10)

        if result.get("ok"):
            monitor_id = result.get("monitorID")
            return True, f"Monitor created for {site_name}", monitor_id
        else:
            return False, f"Failed to create monitor: {result.get('msg', 'Unknown error')}", None

    except asyncio.TimeoutError:
        return False, "Connection timeout", None
    except Exception as e:
        return False, str(e), None
    finally:
        if sio.connected:
            await sio.disconnect()


async def delete_kuma_monitor(site_name: str) -> tuple[bool, str]:
    """Delete a monitor from Uptime Kuma by name."""
    sio = socketio.AsyncClient()
    connected = asyncio.Event()
    monitor_list: list[dict] = []
    data_received = asyncio.Event()

    @sio.on("connect")
    async def on_connect():
        connected.set()

    @sio.on("monitorList")
    async def on_monitor_list(data: dict):
        nonlocal monitor_list
        monitor_list = list(data.values())
        data_received.set()

    try:
        await asyncio.wait_for(sio.connect(KUMA_URL), timeout=5)
        await asyncio.wait_for(connected.wait(), timeout=5)

        # Login
        result = await sio.call(
            "login",
            {"username": KUMA_USERNAME, "password": KUMA_PASSWORD, "token": ""},
            timeout=10,
        )

        if not result.get("ok"):
            return False, f"Login failed: {result.get('msg', 'Unknown error')}"

        # Wait for monitor list
        await asyncio.wait_for(data_received.wait(), timeout=10)

        # Find monitor by name
        monitor_id = None
        for monitor in monitor_list:
            if monitor.get("name") == site_name:
                monitor_id = monitor.get("id")
                break

        if monitor_id is None:
            return False, f"Monitor '{site_name}' not found"

        # Delete monitor
        result = await sio.call("deleteMonitor", monitor_id, timeout=10)

        if result.get("ok"):
            return True, f"Monitor '{site_name}' deleted"
        else:
            return False, f"Failed to delete: {result.get('msg', 'Unknown error')}"

    except asyncio.TimeoutError:
        return False, "Connection timeout"
    except Exception as e:
        return False, str(e)
    finally:
        if sio.connected:
            await sio.disconnect()


@router.get("/", response_model=HealthResponse)
async def get_health():
    """Get health status of all monitored sites from Uptime Kuma."""
    monitors = await get_kuma_status()
    return HealthResponse(monitors=monitors)


@router.post("/monitors", response_model=CreateMonitorResponse)
async def create_monitor(request: CreateMonitorRequest):
    """Create a new Uptime Kuma monitor for a site."""
    success, message, monitor_id = await create_kuma_monitor(request.site_name, request.domain)

    if not success:
        raise HTTPException(status_code=500, detail=message)

    return CreateMonitorResponse(success=success, message=message, monitor_id=monitor_id)


@router.delete("/monitors/{site_name}", response_model=DeleteMonitorResponse)
async def delete_monitor(site_name: str):
    """Delete an Uptime Kuma monitor by site name."""
    success, message = await delete_kuma_monitor(site_name)

    if not success:
        raise HTTPException(status_code=404 if "not found" in message.lower() else 500, detail=message)

    return DeleteMonitorResponse(success=success, message=message)
