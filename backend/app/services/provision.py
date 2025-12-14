from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.config import Settings
from app.schemas.audit import ActionStatus, ActionType, TargetType
from app.schemas.provision import (
    DeprovisionRequest,
    DeprovisionResponse,
    ProvisionRequest,
    ProvisionResponse,
    SITE_TEMPLATES,
    SiteTemplate,
    TemplateType,
)
from app.services.audit import AuditService
from app.services.ssh_client import SSHClientManager


logger = logging.getLogger(__name__)


COMPOSE_TEMPLATES: dict[TemplateType, str] = {
    TemplateType.STATIC: """services:
  nginx:
    image: nginx:alpine
    container_name: {name}
    restart: unless-stopped
    volumes:
      - ./public:/usr/share/nginx/html:ro
      - ./admin:/usr/share/nginx/html/admin:ro
    networks:
      - siteflow

networks:
  siteflow:
    external: true
""",
    TemplateType.NODE: """services:
  payload:
    image: node:20-alpine
    container_name: {name}
    restart: unless-stopped
    working_dir: /app
    command: sh -c "npm install && npm run dev"
    environment:
      - MONGODB_URI=mongodb://mongodb:27017/{name}
      - PAYLOAD_SECRET={secret}
      - NODE_ENV=development
    volumes:
      - ./app:/app
      - node_modules:/app/node_modules
    depends_on:
      - mongodb
    networks:
      - siteflow

  mongodb:
    image: mongo:7
    container_name: {name}-mongo
    restart: unless-stopped
    volumes:
      - mongo_data:/data/db
    networks:
      - siteflow

volumes:
  node_modules:
  mongo_data:

networks:
  siteflow:
    external: true
""",
    TemplateType.PYTHON: """services:
  wagtail:
    image: python:3.12-slim
    container_name: {name}
    restart: unless-stopped
    working_dir: /app
    command: sh -c "pip install -r requirements.txt && python manage.py migrate && python manage.py runserver 0.0.0.0:8000"
    environment:
      - DATABASE_URL=postgres://postgres:postgres@postgres:5432/{name}
      - DJANGO_SECRET_KEY={secret}
      - DEBUG=True
    volumes:
      - ./app:/app
      - pip_cache:/root/.cache/pip
    depends_on:
      - postgres
    networks:
      - siteflow

  postgres:
    image: postgres:16-alpine
    container_name: {name}-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB={name}
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - siteflow

volumes:
  pip_cache:
  postgres_data:

networks:
  siteflow:
    external: true
""",
    TemplateType.WORDPRESS: """services:
  wordpress:
    image: wordpress:latest
    container_name: {name}
    restart: unless-stopped
    environment:
      - WORDPRESS_DB_HOST={name}-mariadb
      - WORDPRESS_DB_USER=wordpress
      - WORDPRESS_DB_PASSWORD={secret}
      - WORDPRESS_DB_NAME=wordpress
    volumes:
      - wp_content:/var/www/html/wp-content
    depends_on:
      - mariadb
    networks:
      - siteflow

  mariadb:
    image: mariadb:11
    container_name: {name}-mariadb
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD={secret}
      - MYSQL_DATABASE=wordpress
      - MYSQL_USER=wordpress
      - MYSQL_PASSWORD={secret}
    volumes:
      - mariadb_data:/var/lib/mysql
    networks:
      - siteflow

volumes:
  wp_content:
  mariadb_data:

networks:
  siteflow:
    external: true
""",
}


CADDY_ROUTE_TEMPLATE = """
{domain} {{
    reverse_proxy {name}:{port}
}}
"""


class ProvisionService:
    """Service for provisioning and deprovisioning sites."""

    def __init__(self, settings: Settings, audit_service: AuditService):
        self.settings = settings
        self.ssh = SSHClientManager(settings)
        self.audit = audit_service

    def get_templates(self) -> list[SiteTemplate]:
        return SITE_TEMPLATES

    def _generate_secret(self) -> str:
        import secrets
        return secrets.token_urlsafe(32)

    def _get_port_for_template(self, template: TemplateType) -> int:
        port_map = {
            TemplateType.STATIC: 80,
            TemplateType.NODE: 3000,
            TemplateType.PYTHON: 8000,
            TemplateType.WORDPRESS: 80,
        }
        return port_map.get(template, 80)

    def _ensure_siteflow_network(self) -> None:
        """Ensure the siteflow Docker network exists."""
        result = self.ssh.execute(
            "docker network ls --filter name=siteflow --format '{{.Name}}'",
            check=False,
        )
        if "siteflow" not in result.stdout:
            logger.info("Creating siteflow Docker network")
            self.ssh.execute("docker network create siteflow", check=True)

    def provision_site(self, request: ProvisionRequest) -> ProvisionResponse:
        """Provision a new site with the specified template."""
        start_time = time.time()
        site_path = f"{self.settings.remote_sites_root}/{request.name}"

        try:
            # Ensure siteflow network exists
            self._ensure_siteflow_network()

            # Check if site already exists
            result = self.ssh.execute(f"test -d {site_path} && echo exists || echo missing")
            if "exists" in result.stdout:
                raise ValueError(f"Site '{request.name}' already exists")

            # Create site directory
            self.ssh.execute(f"mkdir -p {site_path}", check=True)

            # Generate docker-compose.yml
            secret = self._generate_secret()
            compose_content = COMPOSE_TEMPLATES[request.template].format(
                name=request.name,
                secret=secret,
            )
            self._write_remote_file(f"{site_path}/docker-compose.yml", compose_content)

            # Create template-specific directories
            self._create_template_dirs(request.name, request.template, site_path)

            # Add Caddy route if domain specified
            if request.domain:
                self._add_caddy_route(request.name, request.domain, request.template)

            # Start containers
            self.ssh.execute(f"cd {site_path} && docker compose up -d", check=True)

            # Wait for containers to start
            time.sleep(3)

            # Reload Caddy if domain was added
            if request.domain:
                self.ssh.execute("docker exec caddy caddy reload --config /etc/caddy/Caddyfile", check=False)

            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_PROVISION,
                target_type=TargetType.SITE,
                target_name=request.name,
                status=ActionStatus.SUCCESS,
                output=f"Site provisioned with template {request.template.value}",
                metadata={"template": request.template.value, "domain": request.domain},
                duration_ms=duration_ms,
            )

            return ProvisionResponse(
                name=request.name,
                template=request.template,
                status="success",
                message=f"Site '{request.name}' provisioned successfully",
                path=site_path,
                domain=request.domain,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_PROVISION,
                target_type=TargetType.SITE,
                target_name=request.name,
                status=ActionStatus.FAILURE,
                error_message=str(e),
                metadata={"template": request.template.value},
                duration_ms=duration_ms,
            )
            raise

    def deprovision_site(self, request: DeprovisionRequest) -> DeprovisionResponse:
        """Deprovision an existing site."""
        start_time = time.time()
        site_path = f"{self.settings.remote_sites_root}/{request.name}"

        try:
            # Check if site exists
            result = self.ssh.execute(f"test -d {site_path} && echo exists || echo missing")
            if "missing" in result.stdout:
                raise ValueError(f"Site '{request.name}' does not exist")

            # Stop and remove containers
            volume_flag = "-v" if request.remove_volumes else ""
            self.ssh.execute(f"cd {site_path} && docker compose down {volume_flag}", check=False)

            # Remove Caddy route
            self._remove_caddy_route(request.name)

            # Remove files if requested
            files_removed = False
            if request.remove_files:
                self.ssh.execute(f"rm -rf {site_path}", check=True)
                files_removed = True

            # Reload Caddy
            self.ssh.execute("docker exec caddy caddy reload --config /etc/caddy/Caddyfile", check=False)

            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_DEPROVISION,
                target_type=TargetType.SITE,
                target_name=request.name,
                status=ActionStatus.SUCCESS,
                output=f"Site deprovisioned (volumes: {request.remove_volumes}, files: {request.remove_files})",
                metadata={
                    "remove_volumes": request.remove_volumes,
                    "remove_files": request.remove_files,
                },
                duration_ms=duration_ms,
            )

            return DeprovisionResponse(
                name=request.name,
                status="success",
                message=f"Site '{request.name}' deprovisioned successfully",
                volumes_removed=request.remove_volumes,
                files_removed=files_removed,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_DEPROVISION,
                target_type=TargetType.SITE,
                target_name=request.name,
                status=ActionStatus.FAILURE,
                error_message=str(e),
                duration_ms=duration_ms,
            )
            raise

    def _write_remote_file(self, path: str, content: str) -> None:
        """Write content to a remote file via SSH."""
        escaped_content = content.replace("'", "'\\''")
        self.ssh.execute(f"cat > {path} << 'SITEFLOW_EOF'\n{content}\nSITEFLOW_EOF", check=True)

    def _create_template_dirs(self, name: str, template: TemplateType, site_path: str) -> None:
        """Create template-specific directories and files."""
        if template == TemplateType.STATIC:
            self.ssh.execute(f"mkdir -p {site_path}/public {site_path}/admin", check=True)
            index_html = f"<html><body><h1>Welcome to {name}</h1></body></html>"
            self._write_remote_file(f"{site_path}/public/index.html", index_html)

        elif template == TemplateType.NODE:
            self.ssh.execute(f"mkdir -p {site_path}/app", check=True)

        elif template == TemplateType.PYTHON:
            self.ssh.execute(f"mkdir -p {site_path}/app", check=True)

        elif template == TemplateType.WORDPRESS:
            pass  # WordPress handles its own directories

    def _add_caddy_route(self, name: str, domain: str, template: TemplateType) -> None:
        """Add a route to the Caddyfile."""
        port = self._get_port_for_template(template)
        route = CADDY_ROUTE_TEMPLATE.format(domain=domain, name=name, port=port)

        # Read current Caddyfile
        try:
            current = self.ssh.read_file(self.settings.remote_caddyfile)
        except FileNotFoundError:
            current = ""

        # Append new route
        new_content = current.rstrip() + "\n" + route
        self._write_remote_file(self.settings.remote_caddyfile, new_content)

    def _remove_caddy_route(self, name: str) -> None:
        """Remove a site's route from the Caddyfile."""
        try:
            current = self.ssh.read_file(self.settings.remote_caddyfile)
        except FileNotFoundError:
            return

        # Simple regex to remove the site's block
        # This matches domain { ... reverse_proxy name:port ... }
        pattern = rf'\n[^\n]*\{{\s*\n\s*reverse_proxy\s+{re.escape(name)}:\d+\s*\n\}}'
        new_content = re.sub(pattern, '', current, flags=re.MULTILINE)

        if new_content != current:
            self._write_remote_file(self.settings.remote_caddyfile, new_content)
