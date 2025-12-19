from __future__ import annotations

import asyncio
import re
import time

from fastapi import APIRouter, HTTPException

from app.dependencies import get_audit_service, get_hetzner_service
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.schemas.routes import RouteInfo, RouteRequest, RouteResponse, RoutesListResponse
from app.services.caddy_parser import parse_caddyfile


router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.get("/", response_model=RoutesListResponse)
async def list_routes():
    """List all routes from Caddyfile."""
    service = get_hetzner_service()

    try:
        caddyfile = await asyncio.to_thread(
            service.ssh.read_file, service.settings.remote_caddyfile
        )
    except FileNotFoundError:
        return RoutesListResponse(routes=[])

    parsed = parse_caddyfile(caddyfile)
    routes: list[RouteInfo] = []

    for route in parsed:
        for host in route.hosts:
            for target in route.reverse_proxies:
                container = None
                port = None
                if ":" in target:
                    parts = target.split(":")
                    container = parts[0]
                    port_str = parts[1].split("/")[0]
                    try:
                        port = int(port_str)
                    except ValueError:
                        pass
                else:
                    container = target.split("/")[0]

                routes.append(
                    RouteInfo(
                        domain=host,
                        target=target,
                        container=container,
                        port=port,
                    )
                )

    return RoutesListResponse(routes=routes)


@router.post("/", response_model=RouteResponse)
async def add_route(request: RouteRequest):
    """Add a new Caddy route (edge from domain to container)."""
    service = get_hetzner_service()
    audit = get_audit_service()

    start_time = time.time()

    try:
        # Read current Caddyfile
        try:
            current = await asyncio.to_thread(
                service.ssh.read_file, service.settings.remote_caddyfile
            )
        except FileNotFoundError:
            current = ""

        # Check if route already exists
        parsed = parse_caddyfile(current)
        for route in parsed:
            if request.domain in route.hosts:
                raise ValueError(f"Route for domain '{request.domain}' already exists")

        # Add new route block
        new_route = f"""
{request.domain} {{
    reverse_proxy {request.container}:{request.port}
}}
"""
        new_content = current.rstrip() + "\n" + new_route

        # Write updated Caddyfile
        await asyncio.to_thread(
            service.ssh.execute,
            f"cat > {service.settings.remote_caddyfile} << 'SITEFLOW_EOF'\n{new_content}\nSITEFLOW_EOF",
        )

        # Reload Caddy
        reload_result = await asyncio.to_thread(
            service.ssh.execute,
            "docker exec caddy caddy reload --config /etc/caddy/Caddyfile",
        )

        # Invalidate cache
        service.cache.invalidate()

        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.ROUTE_ADD,
            target_type=TargetType.ROUTE,
            target_name=request.domain,
            status=ActionStatus.SUCCESS,
            output=f"Added route: {request.domain} -> {request.container}:{request.port}",
            duration_ms=duration_ms,
        )

        return RouteResponse(
            success=True,
            message=f"Route added: {request.domain} -> {request.container}:{request.port}",
            domain=request.domain,
            container=request.container,
        )

    except ValueError as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.ROUTE_ADD,
            target_type=TargetType.ROUTE,
            target_name=request.domain,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.ROUTE_ADD,
            target_type=TargetType.ROUTE,
            target_name=request.domain,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/", response_model=RouteResponse)
async def remove_route(domain: str):
    """Remove a Caddy route by domain."""
    service = get_hetzner_service()
    audit = get_audit_service()

    start_time = time.time()

    try:
        # Read current Caddyfile
        try:
            current = await asyncio.to_thread(
                service.ssh.read_file, service.settings.remote_caddyfile
            )
        except FileNotFoundError:
            raise ValueError("Caddyfile not found")

        # Find and remove the route block
        # Match: domain { ... } (including multiline)
        pattern = rf'\n?{re.escape(domain)}\s*\{{[^}}]*\}}\s*'
        new_content, count = re.subn(pattern, '', current, flags=re.MULTILINE | re.DOTALL)

        if count == 0:
            raise ValueError(f"Route for domain '{domain}' not found")

        # Write updated Caddyfile
        await asyncio.to_thread(
            service.ssh.execute,
            f"cat > {service.settings.remote_caddyfile} << 'SITEFLOW_EOF'\n{new_content.strip()}\nSITEFLOW_EOF",
        )

        # Reload Caddy
        await asyncio.to_thread(
            service.ssh.execute,
            "docker exec caddy caddy reload --config /etc/caddy/Caddyfile",
        )

        # Invalidate cache
        service.cache.invalidate()

        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.ROUTE_REMOVE,
            target_type=TargetType.ROUTE,
            target_name=domain,
            status=ActionStatus.SUCCESS,
            output=f"Removed route: {domain}",
            duration_ms=duration_ms,
        )

        return RouteResponse(
            success=True,
            message=f"Route removed: {domain}",
            domain=domain,
        )

    except ValueError as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.ROUTE_REMOVE,
            target_type=TargetType.ROUTE,
            target_name=domain,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.ROUTE_REMOVE,
            target_type=TargetType.ROUTE,
            target_name=domain,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
