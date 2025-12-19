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
    DetectRequest,
    DetectResponse,
    ProvisionRequest,
    ProvisionResponse,
    SITE_TEMPLATES,
    SiteTemplate,
    TemplateType,
)
from app.services.audit import AuditService
from app.services.cloudflare import CloudflareService
from app.services.ssh_client import SSHClientManager
from app.validators import (
    ValidationError,
    validate_site_name,
    validate_domain,
    validate_git_url,
    quote_shell_arg,
)


logger = logging.getLogger(__name__)


COMPOSE_TEMPLATES: dict[TemplateType, str] = {
    TemplateType.STATIC: """services:
  nginx:
    image: nginx:alpine
    container_name: {name}
    restart: unless-stopped
    volumes:
      - ./public:/usr/share/nginx/html
    networks:
      - web_proxy
    labels:
      caddy: http://${{DOMAIN}}
      caddy.reverse_proxy: "{{{{upstreams 80}}}}"

networks:
  web_proxy:
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
      - web_proxy
    labels:
      caddy: http://${{DOMAIN}}
      caddy.reverse_proxy: "{{{{upstreams 3000}}}}"

  mongodb:
    image: mongo:7
    container_name: {name}-mongo
    restart: unless-stopped
    volumes:
      - mongo_data:/data/db
    networks:
      - web_proxy

volumes:
  node_modules:
  mongo_data:

networks:
  web_proxy:
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
      - web_proxy
    labels:
      caddy: http://${{DOMAIN}}
      caddy.reverse_proxy: "{{{{upstreams 8000}}}}"

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
      - web_proxy

volumes:
  pip_cache:
  postgres_data:

networks:
  web_proxy:
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
      - web_proxy
    labels:
      caddy: http://${{DOMAIN}}
      caddy.reverse_proxy: "{{{{upstreams 80}}}}"

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
      - web_proxy

volumes:
  wp_content:
  mariadb_data:

networks:
  web_proxy:
    external: true
""",
}


CADDY_ROUTE_TEMPLATE = """
{domain} {{
    reverse_proxy {name}:{port}
}}
"""

LANDING_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{site_name} - Coming Soon</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e4e4e4;
        }}
        .container {{
            text-align: center;
            padding: 2rem;
            max-width: 600px;
        }}
        .logo {{
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #e94560 0%, #533483 100%);
            border-radius: 20px;
            margin: 0 auto 2rem;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            font-weight: bold;
            color: white;
        }}
        h1 {{
            font-size: 2.5rem;
            margin-bottom: 1rem;
            background: linear-gradient(90deg, #e94560, #533483);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        p {{
            font-size: 1.1rem;
            color: #a0a0a0;
            line-height: 1.6;
            margin-bottom: 2rem;
        }}
        .status {{
            display: inline-block;
            padding: 0.5rem 1.5rem;
            background: rgba(233, 69, 96, 0.1);
            border: 1px solid rgba(233, 69, 96, 0.3);
            border-radius: 50px;
            color: #e94560;
            font-size: 0.9rem;
        }}
        .pulse {{
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">{site_initial}</div>
        <h1>{site_name}</h1>
        <p>This site is being set up. Check back soon for something great.</p>
        <span class="status pulse">Coming Soon</span>
    </div>
</body>
</html>
"""

MAINTENANCE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{site_name} - Maintenance</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e4e4e4;
        }}
        .container {{
            text-align: center;
            padding: 2rem;
            max-width: 600px;
        }}
        .icon {{
            font-size: 4rem;
            margin-bottom: 1.5rem;
        }}
        h1 {{
            font-size: 2rem;
            margin-bottom: 1rem;
            color: #f0f0f0;
        }}
        p {{
            font-size: 1.1rem;
            color: #a0a0a0;
            line-height: 1.6;
            margin-bottom: 2rem;
        }}
        .status {{
            display: inline-block;
            padding: 0.5rem 1.5rem;
            background: rgba(250, 204, 21, 0.1);
            border: 1px solid rgba(250, 204, 21, 0.3);
            border-radius: 50px;
            color: #facc15;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">&#9881;</div>
        <h1>Under Maintenance</h1>
        <p>We're making some improvements. This site will be back online shortly.</p>
        <span class="status">Scheduled Maintenance</span>
    </div>
</body>
</html>
"""


class ProvisionService:
    """Service for provisioning and deprovisioning sites."""

    def __init__(self, settings: Settings, audit_service: AuditService, cloudflare_service: CloudflareService):
        self.settings = settings
        self.ssh = SSHClientManager(settings)
        self.audit = audit_service
        self.cloudflare = cloudflare_service

    def get_templates(self) -> list[SiteTemplate]:
        return SITE_TEMPLATES

    def detect_project_type(self, request: DetectRequest) -> DetectResponse:
        """Detect the project type from a git URL or existing path."""
        import tempfile
        import shutil

        temp_dir = None
        scan_path = None
        files_checked: list[str] = []

        try:
            if request.git_url:
                # Validate git URL
                try:
                    validated_url = validate_git_url(request.git_url)
                except ValidationError as e:
                    return DetectResponse(
                        detected_type=TemplateType.STATIC,
                        confidence="low",
                        reason=f"Invalid git URL: {e}",
                        files_checked=[],
                    )

                # Clone to temp directory for scanning
                temp_dir = tempfile.mkdtemp(prefix="siteflow_detect_")
                quoted_url = quote_shell_arg(validated_url)
                quoted_dir = quote_shell_arg(f"{temp_dir}/repo")
                result = self.ssh.execute(
                    f"git clone --depth 1 {quoted_url} {quoted_dir} 2>&1",
                    check=False,
                    timeout=60,
                )
                if result.exit_code != 0:
                    return DetectResponse(
                        detected_type=TemplateType.STATIC,
                        confidence="low",
                        reason=f"Failed to clone repo: {result.stderr or result.stdout}",
                        files_checked=[],
                    )
                scan_path = f"{temp_dir}/repo"
            elif request.path:
                scan_path = request.path
            else:
                return DetectResponse(
                    detected_type=TemplateType.STATIC,
                    confidence="low",
                    reason="No git_url or path provided",
                    files_checked=[],
                )

            # Check for indicator files
            indicators = {
                "package.json": TemplateType.NODE,
                "requirements.txt": TemplateType.PYTHON,
                "pyproject.toml": TemplateType.PYTHON,
                "setup.py": TemplateType.PYTHON,
                "Pipfile": TemplateType.PYTHON,
                "manage.py": TemplateType.PYTHON,
                "wp-config.php": TemplateType.WORDPRESS,
                "wp-content": TemplateType.WORDPRESS,
            }

            # List files in root
            result = self.ssh.execute(f"ls -la {scan_path} 2>/dev/null || echo 'DIR_NOT_FOUND'", check=False)
            if "DIR_NOT_FOUND" in result.stdout:
                return DetectResponse(
                    detected_type=TemplateType.STATIC,
                    confidence="low",
                    reason="Directory not found",
                    files_checked=[],
                )

            root_files = result.stdout.strip().split("\n")
            files_checked = [f.split()[-1] for f in root_files if len(f.split()) > 0]

            # Check each indicator
            for indicator, template_type in indicators.items():
                check_result = self.ssh.execute(
                    f"test -e {scan_path}/{indicator} && echo 'FOUND' || echo 'NOT_FOUND'",
                    check=False,
                )
                if "FOUND" in check_result.stdout:
                    # Determine confidence based on what we found
                    confidence = "high"
                    if indicator in ["package.json"]:
                        # Check if it's a Node project with specific frameworks
                        pkg_result = self.ssh.execute(f"cat {scan_path}/package.json 2>/dev/null", check=False)
                        if "payload" in pkg_result.stdout.lower() or "express" in pkg_result.stdout.lower():
                            confidence = "high"
                            reason = f"Found {indicator} with Node.js framework"
                        else:
                            reason = f"Found {indicator}"
                    elif indicator in ["wp-config.php", "wp-content"]:
                        confidence = "high"
                        reason = f"Found WordPress indicator: {indicator}"
                    elif indicator == "manage.py":
                        confidence = "high"
                        reason = "Found Django manage.py"
                    else:
                        reason = f"Found {indicator}"

                    return DetectResponse(
                        detected_type=template_type,
                        confidence=confidence,
                        reason=reason,
                        files_checked=files_checked[:10],
                    )

            # Default to static
            return DetectResponse(
                detected_type=TemplateType.STATIC,
                confidence="medium",
                reason="No framework indicators found, defaulting to static site",
                files_checked=files_checked[:10],
            )

        finally:
            # Cleanup temp directory
            if temp_dir:
                self.ssh.execute(f"rm -rf {temp_dir}", check=False)

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

    def _ensure_web_proxy_network(self) -> None:
        """Ensure the web_proxy Docker network exists."""
        result = self.ssh.execute(
            "docker network ls --filter name=web_proxy --format '{{.Name}}'",
            check=False,
        )
        if "web_proxy" not in result.stdout:
            logger.info("Creating web_proxy Docker network")
            self.ssh.execute("docker network create web_proxy", check=True)

    def provision_site(self, request: ProvisionRequest) -> ProvisionResponse:
        """Provision a new site with the specified template."""
        start_time = time.time()

        # Validate inputs
        try:
            validated_name = validate_site_name(request.name)
        except ValidationError as e:
            raise ValueError(f"Invalid site name: {e}") from e

        site_path = f"{self.settings.remote_sites_root}/{validated_name}"
        quoted_site_path = quote_shell_arg(site_path)

        # Use provided domain or default to {name}.double232.com
        raw_domain = request.domain or f"{validated_name}.double232.com"
        try:
            domain = validate_domain(raw_domain)
        except ValidationError as e:
            raise ValueError(f"Invalid domain: {e}") from e

        try:
            # Ensure web_proxy network exists
            self._ensure_web_proxy_network()

            # Check if site already exists
            result = self.ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
            if "exists" in result.stdout:
                raise ValueError(f"Site '{validated_name}' already exists")

            # Create site directory
            self.ssh.execute(f"mkdir -p {quoted_site_path}", check=True)

            # Generate docker-compose.yml
            secret = self._generate_secret()
            compose_content = COMPOSE_TEMPLATES[request.template].format(
                name=validated_name,
                secret=secret,
            )
            self._write_remote_file(f"{site_path}/docker-compose.yml", compose_content)

            # Create .env file with DOMAIN
            self._write_remote_file(f"{site_path}/.env", f"DOMAIN={domain}\n")

            # Create template-specific directories
            self._create_template_dirs(validated_name, request.template, site_path)

            # Start containers (caddy-docker-proxy auto-discovers labels)
            self.ssh.execute(f"cd {quoted_site_path} && docker compose up -d", check=True)

            # Reload Caddy to pick up the new container's labels immediately
            # This prevents HTTP/HTTPS redirect loops from stale config
            self.ssh.execute("docker restart caddy", check=False)
            logger.info(f"Reloaded Caddy to pick up labels for {validated_name}")

            # Add public hostname to Cloudflare tunnel and create DNS record
            # Route through HTTP - Cloudflare handles TLS at the edge, tunnel is already encrypted
            service_url = "http://localhost:80"
            cf_success = self.cloudflare.add_public_hostname(domain, service_url)
            if not cf_success:
                logger.warning(f"Failed to add Cloudflare tunnel hostname for {domain}")

            dns_success = self.cloudflare.add_dns_record(domain)
            if not dns_success:
                logger.warning(f"Failed to create Cloudflare DNS record for {domain}")

            # Handle immediate deployment if requested
            deploy_output = ""
            if request.deploy_source:
                logger.info(f"Triggering immediate deployment for {validated_name} from {request.deploy_source.type}")
                try:
                    deploy_output = self._handle_deploy(validated_name, request.deploy_source)
                except Exception as e:
                    logger.error(f"Immediate deployment failed: {e}")
                    deploy_output = f"\nStats: Provisioned OK, but Deployment Failed: {e}"

            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_PROVISION,
                target_type=TargetType.SITE,
                target_name=validated_name,
                status=ActionStatus.SUCCESS,
                output=f"Site provisioned with template {request.template.value}{deploy_output}",
                metadata={"template": request.template.value, "domain": domain},
                duration_ms=duration_ms,
            )

            return ProvisionResponse(
                name=validated_name,
                template=request.template,
                status="success",
                message=f"Site '{validated_name}' provisioned successfully at {domain}. {deploy_output}",
                path=site_path,
                domain=domain,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_PROVISION,
                target_type=TargetType.SITE,
                target_name=validated_name,
                status=ActionStatus.FAILURE,
                error_message=str(e),
                metadata={"template": request.template.value},
                duration_ms=duration_ms,
            )
            raise

    def _handle_deploy(self, site_name: str, source: Any) -> str:
        """Helper to trigger deployment logic from provision service.
        Note: This re-implements some logic from deploy router to keep services decoupled,
        or ideally we should move deploy logic to a service. For now, we inline a simple git deploy.
        """
        # Only supporting Git for background provision-deploy for now as per reliability recommendation
        if source.type != 'git' or not source.url:
             return " Skipped deployment: Only Git source supported for immediate provision-deploy."

        site_path = f"{self.settings.remote_sites_root}/{site_name}"
        # Simplified version of deploy logic
        # 1. Determine app path (assume default structure since we just created it)
        # Static/WordPress -> public/wp-content is mounted, but git usually goes to app or root.
        # For simplicity in this unified flow, we assume standard 'app' unless template is static.
        
        # Actually, let's use the same logic as deploy.py: check docker-compose
        # But we just wrote it, so we know.
        # STATIC -> ./public
        # NODE -> ./app
        # PYTHON -> ./app
        
        deploy_dir = "public" if "public" in COMPOSE_TEMPLATES.get(TemplateType.STATIC, "") else "app" 
        # Wait, we need to check the ACTUAL template used. But we don't have it in this method args strictly.
        # Let's inspect the site on disk or just try standard locations.
        # Better: use the 'app' dir for git clones generally, unless it's pure static HTML.
        
        target_path = f"{site_path}/app" # Default for most
        result = self.ssh.execute(f"grep 'volumes:' {site_path}/docker-compose.yml -A 5 | grep './public'", check=False)
        if result.exit_code == 0:
            target_path = f"{site_path}/public"

        quoted_target = quote_shell_arg(target_path)
        quoted_url = quote_shell_arg(source.url)
        quoted_branch = quote_shell_arg(source.branch)

        # Clone
        logger.info(f"Cloning {source.url} to {target_path}")
        self.ssh.execute(
            f"rm -rf {quoted_target} && git clone --branch {quoted_branch} --depth 1 {quoted_url} {quoted_target}",
            check=True
        )

        # Save config
        import json
        config = {"repo_url": source.url, "branch": source.branch}
        quoted_config = quote_shell_arg(json.dumps(config))
        self.ssh.execute(f"echo {quoted_config} > {site_path}/.siteflow.json", check=False)
        
        # Rebuild
        self.ssh.execute(
            f"cd {site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
            check=True
        )
        
        return " Deployment successful."

    def deprovision_site(self, request: DeprovisionRequest) -> DeprovisionResponse:
        """Deprovision an existing site."""
        start_time = time.time()

        # Validate site name
        try:
            validated_name = validate_site_name(request.name)
        except ValidationError as e:
            raise ValueError(f"Invalid site name: {e}") from e

        site_path = f"{self.settings.remote_sites_root}/{validated_name}"
        quoted_site_path = quote_shell_arg(site_path)

        try:
            # Check if site exists
            result = self.ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
            if "missing" in result.stdout:
                raise ValueError(f"Site '{validated_name}' does not exist")

            # Read domain from .env file to remove from Cloudflare
            domain = None
            try:
                env_result = self.ssh.execute(f"cat {quoted_site_path}/.env 2>/dev/null || true", check=False)
                for line in env_result.stdout.split("\n"):
                    if line.startswith("DOMAIN="):
                        domain = line.split("=", 1)[1].strip()
                        break
            except Exception as e:
                logger.warning(f"Could not read domain from .env: {e}")

            # Remove hostname from Cloudflare tunnel and DNS record
            if domain:
                cf_success = self.cloudflare.remove_public_hostname(domain)
                if not cf_success:
                    logger.warning(f"Failed to remove Cloudflare tunnel hostname for {domain}")

                dns_success = self.cloudflare.remove_dns_record(domain)
                if not dns_success:
                    logger.warning(f"Failed to remove Cloudflare DNS record for {domain}")

            # Stop and remove containers (caddy-docker-proxy auto-removes routes)
            volume_flag = "-v" if request.remove_volumes else ""
            self.ssh.execute(f"cd {quoted_site_path} && docker compose down {volume_flag}", check=False)

            # Remove files if requested
            files_removed = False
            if request.remove_files:
                self.ssh.execute(f"rm -rf {quoted_site_path}", check=True)
                files_removed = True

            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_DEPROVISION,
                target_type=TargetType.SITE,
                target_name=validated_name,
                status=ActionStatus.SUCCESS,
                output=f"Site deprovisioned (volumes: {request.remove_volumes}, files: {request.remove_files})",
                metadata={
                    "remove_volumes": request.remove_volumes,
                    "remove_files": request.remove_files,
                },
                duration_ms=duration_ms,
            )

            return DeprovisionResponse(
                name=validated_name,
                status="success",
                message=f"Site '{validated_name}' deprovisioned successfully",
                volumes_removed=request.remove_volumes,
                files_removed=files_removed,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_action(
                action_type=ActionType.SITE_DEPROVISION,
                target_type=TargetType.SITE,
                target_name=validated_name,
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
        # Generate landing page for all templates
        site_initial = name[0].upper() if name else "S"
        display_name = name.replace("-", " ").title()
        landing_page = LANDING_PAGE_TEMPLATE.format(
            site_name=display_name,
            site_initial=site_initial,
        )
        maintenance_page = MAINTENANCE_PAGE_TEMPLATE.format(site_name=display_name)

        if template == TemplateType.STATIC:
            self.ssh.execute(f"mkdir -p {site_path}/public {site_path}/admin", check=True)
            self._write_remote_file(f"{site_path}/public/index.html", landing_page)
            self._write_remote_file(f"{site_path}/public/maintenance.html", maintenance_page)

        elif template == TemplateType.NODE:
            self.ssh.execute(f"mkdir -p {site_path}/app {site_path}/public", check=True)
            self._write_remote_file(f"{site_path}/public/index.html", landing_page)
            self._write_remote_file(f"{site_path}/public/maintenance.html", maintenance_page)

        elif template == TemplateType.PYTHON:
            self.ssh.execute(f"mkdir -p {site_path}/app {site_path}/static", check=True)
            self._write_remote_file(f"{site_path}/static/index.html", landing_page)
            self._write_remote_file(f"{site_path}/static/maintenance.html", maintenance_page)

        elif template == TemplateType.WORDPRESS:
            # WordPress has its own structure, but we can add maintenance page
            self.ssh.execute(f"mkdir -p {site_path}/maintenance", check=True)
            self._write_remote_file(f"{site_path}/maintenance/index.html", maintenance_page)

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
