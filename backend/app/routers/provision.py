from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.dependencies import get_audit_service, get_provision_service
from app.routers.health import create_kuma_monitor, delete_kuma_monitor
from app.schemas.provision import (
    DeprovisionRequest,
    DeprovisionResponse,
    DetectRequest,
    DetectResponse,
    ProvisionRequest,
    ProvisionResponse,
    TemplateListResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/provision", tags=["provision"])


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates():
    """List available site templates."""
    service = get_provision_service()
    return TemplateListResponse(templates=service.get_templates())


@router.post("/detect", response_model=DetectResponse)
async def detect_project_type(request: DetectRequest):
    """Detect project type from git URL or path."""
    service = get_provision_service()
    try:
        result = await asyncio.to_thread(service.detect_project_type, request)
        return result
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/", response_model=ProvisionResponse)
async def provision_site(request: ProvisionRequest):
    """Provision a new site with the specified template."""
    service = get_provision_service()
    try:
        result = await asyncio.to_thread(service.provision_site, request)

        # Create Uptime Kuma monitor for the new site
        domain = request.domain or f"{request.name}.double232.com"
        try:
            success, msg, monitor_id = await create_kuma_monitor(request.name, domain)
            if success:
                logger.info(f"Created Kuma monitor for {request.name}: {monitor_id}")
            else:
                logger.warning(f"Failed to create Kuma monitor for {request.name}: {msg}")
        except Exception as e:
            logger.warning(f"Kuma monitor creation failed for {request.name}: {e}")

        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/", response_model=DeprovisionResponse)
async def deprovision_site(request: DeprovisionRequest):
    """Deprovision an existing site."""
    service = get_provision_service()
    try:
        # Delete Uptime Kuma monitor first
        try:
            success, msg = await delete_kuma_monitor(request.name)
            if success:
                logger.info(f"Deleted Kuma monitor for {request.name}")
            else:
                logger.warning(f"Failed to delete Kuma monitor for {request.name}: {msg}")
        except Exception as e:
            logger.warning(f"Kuma monitor deletion failed for {request.name}: {e}")

        result = await asyncio.to_thread(service.deprovision_site, request)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
