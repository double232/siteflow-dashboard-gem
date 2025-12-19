from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Any

import socketio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.dependencies import get_hetzner_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])


class HeartbeatEntry(BaseModel):
    status: int  # 0=down, 1=up, 2=pending
    time: str
    ping: int | None = None


class MonitorStatus(BaseModel):
    up: bool
    ping: int | None = None
    uptime: float = 0.0  # Percentage 0-100
    heartbeats: list[HeartbeatEntry] = Field(default_factory=list)  # Last N heartbeats for visualization


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
    settings = get_settings()
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
        logger.info(f"Connecting to Kuma at {settings.kuma_url}")
        await asyncio.wait_for(sio.connect(settings.kuma_url), timeout=5)

        # Login
        logger.info(f"Logging in as {settings.kuma_username}")
        result = await sio.call(
            "login",
            {"username": settings.kuma_username, "password": settings.kuma_password, "token": ""},
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
    settings = get_settings()
    sio = socketio.AsyncClient()
    connected = asyncio.Event()

    @sio.on("connect")
    async def on_connect():
        connected.set()

    try:
        await asyncio.wait_for(sio.connect(settings.kuma_url), timeout=5)
        await asyncio.wait_for(connected.wait(), timeout=5)

        # Login
        result = await sio.call(
            "login",
            {"username": settings.kuma_username, "password": settings.kuma_password, "token": ""},
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
    settings = get_settings()
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
        await asyncio.wait_for(sio.connect(settings.kuma_url), timeout=5)
        await asyncio.wait_for(connected.wait(), timeout=5)

        # Login
        result = await sio.call(
            "login",
            {"username": settings.kuma_username, "password": settings.kuma_password, "token": ""},
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


# System Health Check Models
class ComponentStatus(BaseModel):
    status: str  # "ok", "degraded", "error"
    message: str
    latency_ms: float | None = None


class SystemHealthResponse(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy"
    ssh: ComponentStatus
    docker: ComponentStatus
    caddy: ComponentStatus
    database: ComponentStatus
    uptime_kuma: ComponentStatus


async def check_ssh_health() -> ComponentStatus:
    """Check SSH connectivity to Hetzner server."""
    import time
    try:
        service = get_hetzner_service()
        start = time.time()
        result = service.ssh.execute("echo ok", timeout=10)
        latency = (time.time() - start) * 1000

        if result.exit_code == 0 and "ok" in result.stdout:
            return ComponentStatus(status="ok", message="SSH connection successful", latency_ms=round(latency, 2))
        else:
            return ComponentStatus(status="error", message=f"SSH check failed: {result.stderr or 'unknown error'}", latency_ms=round(latency, 2))
    except Exception as e:
        logger.error(f"SSH health check failed: {e}")
        return ComponentStatus(status="error", message=f"SSH connection failed: {str(e)}")


async def check_docker_health() -> ComponentStatus:
    """Check Docker availability on remote server."""
    import time
    try:
        service = get_hetzner_service()
        start = time.time()
        result = service.ssh.execute("docker info --format '{{.ServerVersion}}'", timeout=15)
        latency = (time.time() - start) * 1000

        if result.exit_code == 0 and result.stdout:
            return ComponentStatus(
                status="ok",
                message=f"Docker {result.stdout.strip()} available",
                latency_ms=round(latency, 2)
            )
        else:
            return ComponentStatus(
                status="error",
                message=f"Docker not available: {result.stderr or 'unknown error'}",
                latency_ms=round(latency, 2)
            )
    except Exception as e:
        logger.error(f"Docker health check failed: {e}")
        return ComponentStatus(status="error", message=f"Docker check failed: {str(e)}")


async def check_caddy_health() -> ComponentStatus:
    """Check Caddy configuration file accessibility."""
    import time
    try:
        service = get_hetzner_service()
        settings = get_settings()
        start = time.time()

        # Check if Caddyfile exists and is readable
        try:
            content = service.ssh.read_file(settings.remote_caddyfile)
            latency = (time.time() - start) * 1000

            if content:
                line_count = len(content.splitlines())
                return ComponentStatus(
                    status="ok",
                    message=f"Caddyfile readable ({line_count} lines)",
                    latency_ms=round(latency, 2)
                )
            else:
                return ComponentStatus(status="degraded", message="Caddyfile is empty", latency_ms=round(latency, 2))
        except FileNotFoundError:
            latency = (time.time() - start) * 1000
            return ComponentStatus(
                status="error",
                message=f"Caddyfile not found: {settings.remote_caddyfile}",
                latency_ms=round(latency, 2)
            )
    except Exception as e:
        logger.error(f"Caddy health check failed: {e}")
        return ComponentStatus(status="error", message=f"Caddy check failed: {str(e)}")


async def check_database_health() -> ComponentStatus:
    """Check SQLite database accessibility."""
    import time
    try:
        settings = get_settings()
        start = time.time()

        conn = sqlite3.connect(settings.sqlite_db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        count = cursor.fetchone()[0]
        conn.close()

        latency = (time.time() - start) * 1000
        return ComponentStatus(
            status="ok",
            message=f"Database accessible ({count} audit entries)",
            latency_ms=round(latency, 2)
        )
    except sqlite3.Error as e:
        logger.error(f"Database health check failed: {e}")
        return ComponentStatus(status="error", message=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return ComponentStatus(status="error", message=f"Database check failed: {str(e)}")


async def check_uptime_kuma_health() -> ComponentStatus:
    """Check Uptime Kuma connectivity."""
    import time
    settings = get_settings()
    try:
        sio = socketio.AsyncClient()
        start = time.time()

        await asyncio.wait_for(sio.connect(settings.kuma_url), timeout=5)
        latency = (time.time() - start) * 1000

        if sio.connected:
            await sio.disconnect()
            return ComponentStatus(
                status="ok",
                message="Uptime Kuma connected",
                latency_ms=round(latency, 2)
            )
        else:
            return ComponentStatus(status="error", message="Connection failed")
    except asyncio.TimeoutError:
        return ComponentStatus(status="error", message="Connection timeout")
    except Exception as e:
        # Don't fail if Kuma is optional/not configured
        logger.warning(f"Uptime Kuma health check failed: {e}")
        return ComponentStatus(status="degraded", message=f"Uptime Kuma unavailable: {str(e)}")


@router.get("/system", response_model=SystemHealthResponse)
async def get_system_health():
    """Get system health status for all dependent services."""
    # Run all checks concurrently using asyncio.gather
    ssh_status, docker_status, caddy_status, db_status, kuma_status = await asyncio.gather(
        check_ssh_health(),
        check_docker_health(),
        check_caddy_health(),
        check_database_health(),
        check_uptime_kuma_health(),
    )

    # Determine overall status
    statuses = [ssh_status.status, docker_status.status, caddy_status.status, db_status.status]
    # Kuma is optional, so only count it if it's in error (not degraded)
    if kuma_status.status == "error":
        statuses.append("degraded")  # Downgrade Kuma errors to degraded since it's optional

    if all(s == "ok" for s in statuses):
        overall = "healthy"
    elif any(s == "error" for s in statuses[:4]):  # Only SSH, Docker, Caddy, DB are critical
        overall = "unhealthy"
    else:
        overall = "degraded"

    return SystemHealthResponse(
        status=overall,
        ssh=ssh_status,
        docker=docker_status,
        caddy=caddy_status,
        database=db_status,
        uptime_kuma=kuma_status,
    )
