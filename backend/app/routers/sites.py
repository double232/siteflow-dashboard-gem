from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Path, Query

from app.dependencies import get_audit_service, get_hetzner_service
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.schemas.site import SitesResponse


router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("/", response_model=SitesResponse)
async def list_sites(refresh: bool = Query(False, description="Force refresh from Hetzner")):
    service = get_hetzner_service()
    response = await asyncio.to_thread(service.get_sites, refresh)
    return response


@router.post("/containers/{container}/{action}")
async def container_action(
    container: str = Path(..., description="Docker container name"),
    action: str = Path(..., description="start|stop|restart|logs"),
):
    service = get_hetzner_service()
    audit = get_audit_service()

    action_type_map = {
        "start": ActionType.CONTAINER_START,
        "stop": ActionType.CONTAINER_STOP,
        "restart": ActionType.CONTAINER_RESTART,
        "logs": ActionType.CONTAINER_LOGS,
    }

    start_time = time.time()
    try:
        output = await asyncio.to_thread(service.run_container_action, container, action)
        duration_ms = (time.time() - start_time) * 1000

        audit.log_action(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.CONTAINER,
            target_name=container,
            status=ActionStatus.SUCCESS,
            output=output,
            duration_ms=duration_ms,
        )
    except ValueError as exc:
        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.CONTAINER,
            target_name=container,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.CONTAINER,
            target_name=container,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"container": container, "action": action, "output": output}


@router.post("/{site_name}/{action}")
async def site_action(
    site_name: str = Path(..., description="Site directory name"),
    action: str = Path(..., description="start|stop|restart"),
):
    """Start/stop/restart a site using docker-compose."""
    service = get_hetzner_service()
    audit = get_audit_service()

    action_type_map = {
        "start": ActionType.SITE_START,
        "stop": ActionType.SITE_STOP,
        "restart": ActionType.SITE_RESTART,
    }

    if action not in action_type_map:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    start_time = time.time()
    try:
        output = await asyncio.to_thread(service.run_site_action, site_name, action)
        duration_ms = (time.time() - start_time) * 1000

        audit.log_action(
            action_type=action_type_map[action],
            target_type=TargetType.SITE,
            target_name=site_name,
            status=ActionStatus.SUCCESS,
            output=output,
            duration_ms=duration_ms,
        )
    except ValueError as exc:
        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.SITE,
            target_name=site_name,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.SITE,
            target_name=site_name,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"site": site_name, "action": action, "output": output}


@router.post("/caddy/reload")
async def reload_caddy():
    service = get_hetzner_service()
    audit = get_audit_service()

    start_time = time.time()
    try:
        output = await asyncio.to_thread(service.reload_caddy)
        duration_ms = (time.time() - start_time) * 1000

        status = ActionStatus.SUCCESS if "Failed" not in output else ActionStatus.FAILURE
        audit.log_action(
            action_type=ActionType.CADDY_RELOAD,
            target_type=TargetType.CADDY,
            target_name="caddy",
            status=status,
            output=output,
            duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=ActionType.CADDY_RELOAD,
            target_type=TargetType.CADDY,
            target_name="caddy",
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"message": output}


@router.put("/{site}/domain")
async def set_site_env(
    site: str = Path(..., description="Site name"),
    domain: str = Query(..., description="Domain for the site"),
):
    """Set the DOMAIN environment variable for a site."""
    service = get_hetzner_service()
    audit = get_audit_service()

    start_time = time.time()
    env_path = f"{service.settings.remote_sites_root}/{site}/.env"

    try:
        # Read existing .env if it exists
        try:
            existing = await asyncio.to_thread(service.ssh.read_file, env_path)
        except FileNotFoundError:
            existing = ""

        # Update or add DOMAIN line
        lines = existing.strip().split('\n') if existing.strip() else []
        new_lines = [l for l in lines if not l.startswith('DOMAIN=')]
        new_lines.append(f'DOMAIN={domain}')
        new_content = '\n'.join(new_lines) + '\n'

        # Write the .env file
        cmd = f"cat > {env_path} << 'EOF'\n{new_content}EOF"
        await asyncio.to_thread(service.ssh.execute, cmd)

        # Invalidate cache
        service.cache.invalidate()

        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=ActionType.SITE_START,  # Using SITE_START as placeholder
            target_type=TargetType.SITE,
            target_name=site,
            status=ActionStatus.SUCCESS,
            output=f"Set DOMAIN={domain}",
            duration_ms=duration_ms,
        )

        return {"message": f"Set DOMAIN={domain} for {site}", "site": site, "domain": domain}
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        audit.log_action(
            action_type=ActionType.SITE_START,
            target_type=TargetType.SITE,
            target_name=site,
            status=ActionStatus.FAILURE,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
