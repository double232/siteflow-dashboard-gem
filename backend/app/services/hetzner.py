from __future__ import annotations

import json
import time
from typing import Any, Dict, Tuple

import yaml

from app.config import Settings
from app.schemas.site import ContainerStatus, PortMapping, Site, SiteService, SitesResponse
from app.services.cache import TimedCache
from app.services.caddy_parser import parse_caddyfile
from app.services.ssh_client import SSHClientManager


class HetznerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ssh = SSHClientManager(settings)
        self.cache = TimedCache[Tuple[list[Site], float]](ttl_seconds=settings.cache_ttl_seconds)

    def get_sites(self, force_refresh: bool = False) -> SitesResponse:
        def builder() -> tuple[list[Site], float]:
            sites = self._collect_sites()
            return sites, time.time()

        sites, updated_at = self.cache.get(builder, force_refresh=force_refresh)
        return SitesResponse(sites=sites, updated_at=updated_at)

    def run_container_action(self, container: str, action: str) -> str:
        valid_actions = {"start", "stop", "restart", "logs"}
        if action not in valid_actions:
            raise ValueError(f"Unsupported action: {action}")

        if action == "logs":
            result = self.ssh.execute(f"docker logs --tail 200 {container}")
        else:
            result = self.ssh.execute(f"docker {action} {container}", check=True)
            # cache may be stale after action
            self.cache.invalidate()
        return result.stdout or result.stderr

    def reload_caddy(self) -> str:
        result = self.ssh.execute("docker exec caddy caddy reload", check=False)
        if result.exit_code != 0:
            return result.stderr or "Failed to reload Caddy"
        return result.stdout or "Caddy reload triggered"

    def run_site_action(self, site_name: str, action: str) -> str:
        """Run docker-compose action on a site."""
        valid_actions = {"start", "stop", "restart"}
        if action not in valid_actions:
            raise ValueError(f"Unsupported action: {action}")

        site_path = f"{self.settings.remote_sites_root}/{site_name}"

        if action == "start":
            cmd = f"cd {site_path} && docker compose up -d"
        elif action == "stop":
            cmd = f"cd {site_path} && docker compose down"
        elif action == "restart":
            cmd = f"cd {site_path} && docker compose down && docker compose up -d"
        else:
            raise ValueError(f"Unknown action: {action}")

        result = self.ssh.execute(cmd, check=False)
        self.cache.invalidate()

        output = result.stdout or ""
        if result.stderr:
            output += "\n" + result.stderr if output else result.stderr

        return output.strip() or f"Site {action} completed"

    # Internal helpers -------------------------------------------------

    def _collect_sites(self) -> list[Site]:
        directories = self.ssh.list_directories(self.settings.remote_sites_root)
        docker_containers = self._fetch_docker_containers()
        caddy_map = self._map_caddy_targets()

        sites: list[Site] = []
        for directory in directories:
            compose_path = f"{self.settings.remote_sites_root}/{directory}/docker-compose.yml"
            compose_data = self._load_compose_file(compose_path)
            services = self._build_services(directory, compose_data)
            containers = self._match_containers(services, docker_containers)
            caddy_domains: set[str] = set()
            caddy_targets: set[str] = set()
            # Extract caddy info directly from service labels (expanded from .env)
            for service in services:
                caddy_label = service.labels.get("caddy", "")
                if caddy_label:
                    domain = caddy_label.replace("http://", "").replace("https://", "").strip()
                    if domain and not domain.startswith("$"):  # Skip unexpanded vars
                        caddy_domains.add(domain)
                reverse_proxy = service.labels.get("caddy.reverse_proxy", "")
                if reverse_proxy:
                    caddy_targets.add(reverse_proxy)
            # Also check caddy_map for running containers
            for service in services:
                possible_names = [
                    service.container_name,
                    f"{directory}-{service.name}",
                    service.name,
                    directory,
                ]
                for container_name in possible_names:
                    if container_name and container_name in caddy_map:
                        info = caddy_map[container_name]
                        caddy_domains.update(info["domains"])
                        caddy_targets.update(info["targets"])
                        break
            # Also check running containers in case naming differs
            for container in containers:
                if container.name in caddy_map:
                    info = caddy_map[container.name]
                    caddy_domains.update(info["domains"])
                    caddy_targets.update(info["targets"])

            status = self._derive_status(containers)
            site = Site(
                name=directory,
                path=f"{self.settings.remote_sites_root}/{directory}",
                compose_file=compose_path,
                services=services,
                containers=containers,
                caddy_domains=sorted(caddy_domains),
                caddy_targets=sorted(caddy_targets),
                status=status,
            )
            sites.append(site)

        return sites

    def _fetch_docker_containers(self) -> dict[str, ContainerStatus]:
        result = self.ssh.execute("docker ps -a --format '{{json .}}'")
        containers: dict[str, ContainerStatus] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ports = self._parse_docker_ports(payload.get("Ports"))
            container = ContainerStatus(
                name=payload.get("Names", "unknown"),
                status=payload.get("Status", ""),
                state=payload.get("State"),
                image=payload.get("Image"),
                ports=ports,
            )
            containers[container.name] = container
        return containers

    def _map_caddy_targets(self) -> dict[str, dict[str, list[str]]]:
        """Build mapping from container name to caddy domains using Docker labels and Caddyfile."""
        mapping: dict[str, dict[str, list[str]]] = {}

        # Get labels from all containers
        result = self.ssh.execute(
            "docker ps -a --format '{{.Names}}|{{.Label \"caddy\"}}|{{.Label \"caddy.reverse_proxy\"}}'"
        )

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 2:
                continue

            container_name = parts[0]
            caddy_domain = parts[1] if len(parts) > 1 else ""
            reverse_proxy = parts[2] if len(parts) > 2 else ""

            if not caddy_domain:
                continue

            # Clean up domain (remove http:// prefix if present)
            domain = caddy_domain.replace("http://", "").replace("https://", "").strip()

            record = mapping.setdefault(container_name, {"domains": [], "targets": []})
            if domain and domain not in record["domains"]:
                record["domains"].append(domain)
            if reverse_proxy:
                record["targets"].append(reverse_proxy)

        # Also parse Caddyfile for routes not using Docker labels
        self._augment_from_caddyfile(mapping)

        return mapping

    def _augment_from_caddyfile(self, mapping: dict[str, dict[str, list[str]]]) -> None:
        """Parse Caddyfile and add domain mappings for containers."""
        try:
            caddyfile_content = self.ssh.read_file(self.settings.remote_caddyfile)
        except FileNotFoundError:
            return

        routes = parse_caddyfile(caddyfile_content)
        for route in routes:
            for proxy_target in route.reverse_proxies:
                # Extract container name from target like "container:port" or "container:port/path"
                target = proxy_target.split("/")[0]  # Remove path
                if ":" in target:
                    container_name = target.split(":")[0]
                else:
                    container_name = target

                # Skip non-container targets (IPs, external hosts)
                if container_name.replace(".", "").replace("-", "").replace("_", "").isalnum():
                    record = mapping.setdefault(container_name, {"domains": [], "targets": []})
                    for host in route.hosts:
                        domain = host.replace("http://", "").replace("https://", "").strip()
                        if domain and domain not in record["domains"]:
                            record["domains"].append(domain)
                    if proxy_target not in record["targets"]:
                        record["targets"].append(proxy_target)

    def _load_compose_file(self, remote_path: str) -> dict[str, Any]:
        try:
            raw = self.ssh.read_file(remote_path)
        except FileNotFoundError:
            return {}
        data = yaml.safe_load(raw) or {}
        return data

    def _load_env_file(self, site: str) -> dict[str, str]:
        """Load .env file for a site and return as dict."""
        env_path = f"{self.settings.remote_sites_root}/{site}/.env"
        try:
            content = self.ssh.read_file(env_path)
            env_vars: dict[str, str] = {}
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    env_vars[key.strip()] = value.strip()
            return env_vars
        except FileNotFoundError:
            return {}

    def _expand_env_vars(self, value: str, env_vars: dict[str, str]) -> str:
        """Expand ${VAR} references in a string."""
        import re
        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return env_vars.get(var_name, match.group(0))
        return re.sub(r'\$\{([^}]+)\}', replacer, value)

    def _build_services(self, site: str, compose_data: dict[str, Any]) -> list[SiteService]:
        services_section = compose_data.get("services", {}) if isinstance(compose_data, dict) else {}
        env_vars = self._load_env_file(site)
        services: list[SiteService] = []
        for svc_name, svc_data in services_section.items():
            container_name = svc_data.get("container_name") or f"{site}-{svc_name}"
            env_data = self._normalize_env(svc_data.get("environment", {}))
            labels = self._normalize_kv(svc_data.get("labels", {}))
            # Expand environment variables in labels
            labels = {k: self._expand_env_vars(v, env_vars) for k, v in labels.items()}
            ports = self._parse_compose_ports(svc_data.get("ports", []))
            services.append(
                SiteService(
                    name=svc_name,
                    container_name=container_name,
                    image=svc_data.get("image"),
                    ports=ports,
                    labels=labels,
                    environment=env_data,
                )
            )
        return services

    def _match_containers(
        self,
        services: list[SiteService],
        docker_containers: dict[str, ContainerStatus],
    ) -> list[ContainerStatus]:
        matched: list[ContainerStatus] = []
        for service in services:
            key_candidates = {service.container_name, service.name}
            for key in key_candidates:
                if key and key in docker_containers:
                    matched.append(docker_containers[key])
                    break
        return matched

    def _derive_status(self, containers: list[ContainerStatus]) -> str:
        if not containers:
            return "unknown"
        if any("Up" in (c.status or "") for c in containers):
            return "running"
        if all("Exited" in (c.status or "") for c in containers):
            return "stopped"
        return "degraded"

    @staticmethod
    def _parse_docker_ports(raw: str | None) -> list[PortMapping]:
        if not raw:
            return []
        ports: list[PortMapping] = []
        for segment in raw.split(","):
            segment = segment.strip()
            if not segment:
                continue
            if "->" in segment:
                public, private = segment.split("->", 1)
                if ":" in public:
                    public = public.split(":", 1)[1]
                protocol = "tcp"
                if "/" in private:
                    private, protocol = private.split("/", 1)
                ports.append(PortMapping(private=private, public=public, protocol=protocol))
            else:
                ports.append(PortMapping(private=segment, public=None))
        return ports

    @staticmethod
    def _parse_compose_ports(raw: Any) -> list[PortMapping]:
        if not raw:
            return []
        ports: list[PortMapping] = []
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, str):
                    parts = entry.split(":")
                    if len(parts) == 2:
                        ports.append(PortMapping(private=parts[1], public=parts[0]))
                    elif len(parts) == 3:
                        ports.append(PortMapping(private=f"{parts[1]}:{parts[2]}", public=parts[0]))
                elif isinstance(entry, dict):
                    ports.append(
                        PortMapping(
                            private=str(entry.get("target")),
                            public=str(entry.get("published")) if entry.get("published") else None,
                            protocol=entry.get("protocol", "tcp"),
                        )
                    )
        return ports

    @staticmethod
    def _normalize_env(raw: Any) -> dict[str, str]:
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        if isinstance(raw, list):
            env_dict: dict[str, str] = {}
            for item in raw:
                if not isinstance(item, str) or "=" not in item:
                    continue
                key, value = item.split("=", 1)
                env_dict[key] = value
            return env_dict
        return {}

    @staticmethod
    def _normalize_kv(raw: Any) -> dict[str, str]:
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        if isinstance(raw, list):
            pairs = {}
            for item in raw:
                if not isinstance(item, str) or "=" not in item:
                    continue
                key, value = item.split("=", 1)
                pairs[key] = value
            return pairs
        return {}
