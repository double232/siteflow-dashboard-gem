from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.dependencies import get_audit_service, get_hetzner_service, get_current_user_email
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.schemas.site import SitesResponse
from app.validators import (
    ValidationError,
    validate_site_name,
    validate_domain,
    validate_container_name,
    quote_shell_arg,
)


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
    user_email: str | None = Depends(get_current_user_email),
):
    # Validate container name
    try:
        validated_container = validate_container_name(container)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Validate action
    if action not in ("start", "stop", "restart", "logs"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

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
        output = await asyncio.to_thread(service.run_container_action, validated_container, action)
        duration_ms = (time.time() - start_time) * 1000

        await audit.log_action_async(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.CONTAINER,
            target_name=validated_container,
            status=ActionStatus.SUCCESS,
            user_email=user_email,
            output=output,
            duration_ms=duration_ms,
        )
    except ValueError as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.CONTAINER,
            target_name=validated_container,
            status=ActionStatus.FAILURE,
            user_email=user_email,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.CONTAINER,
            target_name=validated_container,
            status=ActionStatus.FAILURE,
            user_email=user_email,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"container": validated_container, "action": action, "output": output}


@router.post("/{site_name}/{action}")
async def site_action(
    site_name: str = Path(..., description="Site directory name"),
    action: str = Path(..., description="start|stop|restart"),
    user_email: str | None = Depends(get_current_user_email),
):
    """Start/stop/restart a site using docker-compose."""
    # Validate site name
    try:
        validated_site = validate_site_name(site_name)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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
        output = await asyncio.to_thread(service.run_site_action, validated_site, action)
        duration_ms = (time.time() - start_time) * 1000

        await audit.log_action_async(
            action_type=action_type_map[action],
            target_type=TargetType.SITE,
            target_name=validated_site,
            status=ActionStatus.SUCCESS,
            user_email=user_email,
            output=output,
            duration_ms=duration_ms,
        )
    except ValueError as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.SITE,
            target_name=validated_site,
            status=ActionStatus.FAILURE,
            user_email=user_email,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=action_type_map.get(action, action),
            target_type=TargetType.SITE,
            target_name=validated_site,
            status=ActionStatus.FAILURE,
            user_email=user_email,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"site": validated_site, "action": action, "output": output}


@router.post("/caddy/reload")
async def reload_caddy(user_email: str | None = Depends(get_current_user_email)):
    service = get_hetzner_service()
    audit = get_audit_service()

    start_time = time.time()
    try:
        output = await asyncio.to_thread(service.reload_caddy)
        duration_ms = (time.time() - start_time) * 1000

        status = ActionStatus.SUCCESS if "Failed" not in output else ActionStatus.FAILURE
        await audit.log_action_async(
            action_type=ActionType.CADDY_RELOAD,
            target_type=TargetType.CADDY,
            target_name="caddy",
            status=status,
            user_email=user_email,
            output=output,
            duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.CADDY_RELOAD,
            target_type=TargetType.CADDY,
            target_name="caddy",
            status=ActionStatus.FAILURE,
            user_email=user_email,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"message": output}


@router.put("/{site}/domain")
async def set_site_env(
    site: str = Path(..., description="Site name"),
    domain: str = Query(..., description="Domain for the site"),
    user_email: str | None = Depends(get_current_user_email),
):
    """Set the DOMAIN environment variable for a site."""
    # Validate inputs
    try:
        validated_site = validate_site_name(site)
        validated_domain = validate_domain(domain)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    service = get_hetzner_service()
    audit = get_audit_service()

    start_time = time.time()
    env_path = f"{service.settings.remote_sites_root}/{validated_site}/.env"
    quoted_env_path = quote_shell_arg(env_path)

    try:
        # Read existing .env if it exists
        try:
            existing = await asyncio.to_thread(service.ssh.read_file, env_path)
        except FileNotFoundError:
            existing = ""

        # Update or add DOMAIN line
        lines = existing.strip().split('\n') if existing.strip() else []
        new_lines = [l for l in lines if not l.startswith('DOMAIN=')]
        new_lines.append(f'DOMAIN={validated_domain}')
        new_content = '\n'.join(new_lines) + '\n'

        # Write the .env file using heredoc (content is validated)
        cmd = f"cat > {quoted_env_path} << 'EOF'\n{new_content}EOF"
        await asyncio.to_thread(service.ssh.execute, cmd)

        # Invalidate cache
        service.cache.invalidate()

        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.SITE_CONFIG,
            target_type=TargetType.SITE,
            target_name=validated_site,
            status=ActionStatus.SUCCESS,
            user_email=user_email,
            output=f"Set DOMAIN={validated_domain}",
            duration_ms=duration_ms,
        )

        return {"message": f"Set DOMAIN={validated_domain} for {validated_site}", "site": validated_site, "domain": validated_domain}
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        await audit.log_action_async(
            action_type=ActionType.SITE_CONFIG,
            target_type=TargetType.SITE,
            target_name=validated_site,
            status=ActionStatus.FAILURE,
            user_email=user_email,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
