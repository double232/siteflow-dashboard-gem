from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TemplateType(str, Enum):
    STATIC = "static"
    NODE = "node"
    PYTHON = "python"
    WORDPRESS = "wordpress"


class SiteTemplate(BaseModel):
    id: TemplateType
    name: str
    description: str
    cms: str
    stack: str
    best_for: list[str] = Field(default_factory=list)
    required_services: list[str] = Field(default_factory=list)


class ProvisionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    template: TemplateType
    domain: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)


class DeprovisionRequest(BaseModel):
    name: str
    remove_volumes: bool = False
    remove_files: bool = False


class ProvisionResponse(BaseModel):
    name: str
    template: TemplateType
    status: str
    message: str
    path: str | None = None
    domain: str | None = None


class DeprovisionResponse(BaseModel):
    name: str
    status: str
    message: str
    volumes_removed: bool = False
    files_removed: bool = False


class TemplateListResponse(BaseModel):
    templates: list[SiteTemplate]


# Pre-defined templates
SITE_TEMPLATES: list[SiteTemplate] = [
    SiteTemplate(
        id=TemplateType.STATIC,
        name="Static Site (Decap CMS)",
        description="Nginx serving static files with Decap CMS for git-based content management",
        cms="Decap (formerly Netlify CMS)",
        stack="Nginx + Decap CMS",
        best_for=["blogs", "documentation", "landing pages"],
        required_services=["nginx"],
    ),
    SiteTemplate(
        id=TemplateType.NODE,
        name="Node (Payload CMS)",
        description="Payload CMS - a TypeScript headless CMS with REST and GraphQL APIs",
        cms="Payload CMS",
        stack="Node.js + Payload + MongoDB",
        best_for=["headless apps", "APIs", "custom content types"],
        required_services=["payload", "mongodb"],
    ),
    SiteTemplate(
        id=TemplateType.PYTHON,
        name="Python (Wagtail)",
        description="Django-based CMS with StreamField page builder",
        cms="Wagtail",
        stack="Django + Wagtail + PostgreSQL",
        best_for=["complex sites", "multi-page content"],
        required_services=["wagtail", "postgres"],
    ),
    SiteTemplate(
        id=TemplateType.WORDPRESS,
        name="WordPress",
        description="Full WordPress installation with MariaDB database",
        cms="WordPress",
        stack="WordPress + MariaDB",
        best_for=["traditional blogs", "WooCommerce", "client sites"],
        required_services=["wordpress", "mariadb"],
    ),
]
