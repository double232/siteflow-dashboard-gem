from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from app.dependencies import (
    get_cloudflare_service,
    get_graph_builder,
    get_hetzner_service,
    get_metrics_service,
    get_nas_service,
)
from app.schemas.graph import GraphResponse


router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/", response_model=GraphResponse)
async def graph(refresh: bool = Query(False, description="Force refresh of upstream data")):
    hetzner = get_hetzner_service()
    cloudflare = get_cloudflare_service()
    metrics_service = get_metrics_service()
    nas_service = get_nas_service()
    builder = get_graph_builder()

    # Fetch all data in parallel
    sites, cf_status, container_metrics = await asyncio.gather(
        asyncio.to_thread(hetzner.get_sites, refresh),
        asyncio.to_thread(cloudflare.get_status, refresh),
        asyncio.to_thread(metrics_service.get_container_metrics, refresh),
    )

    # Get site names for NAS backup check
    site_names = [site.name for site in sites.sites]

    # Fetch NAS status (may be slow, so do it separately)
    nas_status = None
    try:
        nas_status = await asyncio.to_thread(nas_service.get_backup_status, site_names, refresh)
    except Exception:
        pass  # NAS status is optional

    return builder.build(sites, cf_status, container_metrics, nas_status)
