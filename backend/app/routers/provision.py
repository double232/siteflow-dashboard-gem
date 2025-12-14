from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.dependencies import get_audit_service, get_provision_service
from app.schemas.provision import (
    DeprovisionRequest,
    DeprovisionResponse,
    ProvisionRequest,
    ProvisionResponse,
    TemplateListResponse,
)


router = APIRouter(prefix="/api/provision", tags=["provision"])


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates():
    """List available site templates."""
    service = get_provision_service()
    return TemplateListResponse(templates=service.get_templates())


@router.post("/", response_model=ProvisionResponse)
async def provision_site(request: ProvisionRequest):
    """Provision a new site with the specified template."""
    service = get_provision_service()
    try:
        result = await asyncio.to_thread(service.provision_site, request)
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
        result = await asyncio.to_thread(service.deprovision_site, request)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
