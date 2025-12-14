from __future__ import annotations

from pydantic import BaseModel, Field


class PortMapping(BaseModel):
    private: str
    public: str | None = None
    protocol: str = "tcp"


class ContainerStatus(BaseModel):
    name: str
    status: str
    state: str | None = None
    image: str | None = None
    ports: list[PortMapping] = Field(default_factory=list)


class SiteService(BaseModel):
    name: str
    container_name: str | None = None
    image: str | None = None
    ports: list[PortMapping] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)


class Site(BaseModel):
    name: str
    path: str
    compose_file: str
    services: list[SiteService] = Field(default_factory=list)
    containers: list[ContainerStatus] = Field(default_factory=list)
    caddy_domains: list[str] = Field(default_factory=list)
    caddy_targets: list[str] = Field(default_factory=list)
    status: str = "unknown"


class SitesResponse(BaseModel):
    sites: list[Site]
    updated_at: float
