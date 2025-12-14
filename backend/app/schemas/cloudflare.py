from __future__ import annotations

from pydantic import BaseModel, Field


class CloudflareConnector(BaseModel):
    id: str
    version: str | None = None
    location: str | None = None
    status: str | None = None


class CloudflareHostname(BaseModel):
    hostname: str
    service: str


class CloudflareTunnel(BaseModel):
    id: str
    name: str
    status: str | None = None
    connections: list[CloudflareConnector] = Field(default_factory=list)
    hostnames: list[CloudflareHostname] = Field(default_factory=list)


class CloudflareStatus(BaseModel):
    tunnel: CloudflareTunnel | None = None
