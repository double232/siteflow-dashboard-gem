from __future__ import annotations

from pydantic import BaseModel


class RouteRequest(BaseModel):
    """Request to add or modify a Caddy route."""

    domain: str
    container: str
    port: int = 80


class RouteResponse(BaseModel):
    """Response after route operation."""

    success: bool
    message: str
    domain: str | None = None
    container: str | None = None


class RouteInfo(BaseModel):
    """Information about an existing route."""

    domain: str
    target: str
    container: str | None = None
    port: int | None = None


class RoutesListResponse(BaseModel):
    """List of all routes from Caddyfile."""

    routes: list[RouteInfo]
