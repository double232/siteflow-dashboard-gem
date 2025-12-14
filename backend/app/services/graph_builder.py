from __future__ import annotations

from typing import Dict, Set, Tuple

from app.schemas.backup import BackupInfo, NASStatus
from app.schemas.cloudflare import CloudflareStatus
from app.schemas.graph import GraphEdge, GraphNode, GraphResponse, NodeBackupStatus, NodeMetrics
from app.schemas.metrics import ContainerMetrics
from app.schemas.site import ContainerStatus, Site, SitesResponse


class GraphBuilder:
    def __init__(self):
        self.internet_node_id = "internet"
        self.cloudflare_node_id = "cloudflare"
        self.gateway_node_id = "caddy-gateway"
        self.nas_node_id = "nas-backup"

    def build(
        self,
        sites: SitesResponse,
        cloudflare: CloudflareStatus,
        container_metrics: dict[str, ContainerMetrics] | None = None,
        nas_status: NASStatus | None = None,
    ) -> GraphResponse:
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        edge_keys: Set[Tuple[str, str, str | None]] = set()

        # Build lookup for backup info by site name
        backup_by_site: dict[str, BackupInfo] = {}
        if nas_status and nas_status.backups:
            for backup in nas_status.backups:
                backup_by_site[backup.site_name] = backup

        def add_edge(source: str, target: str, label: str | None):
            key = (source, target, label)
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append(
                GraphEdge(
                    id=f"edge-{len(edge_keys)}",
                    source=source,
                    target=target,
                    label=label,
                )
            )

        # Internet node (entry point)
        nodes[self.internet_node_id] = GraphNode(
            id=self.internet_node_id,
            label="Internet",
            type="internet",
            status="running",
            meta={},
        )

        # Cloudflare node
        cf_status = "running" if cloudflare.tunnel else "active"
        cf_meta: dict = {}
        if cloudflare.tunnel:
            cf_meta = {
                "tunnel": cloudflare.tunnel.name,
                "connections": len(cloudflare.tunnel.connections),
            }
        nodes[self.cloudflare_node_id] = GraphNode(
            id=self.cloudflare_node_id,
            label="Cloudflare",
            type="cloudflare",
            status=cf_status,
            meta=cf_meta,
        )
        add_edge(self.internet_node_id, self.cloudflare_node_id, "DNS")

        # Gateway node
        nodes[self.gateway_node_id] = GraphNode(
            id=self.gateway_node_id,
            label="Caddy Gateway",
            type="gateway",
            status="running",
            meta={"remote_path": "/opt/gateway"},
        )

        # NAS backup node (if configured)
        if nas_status:
            nas_node_status = "running" if nas_status.connected else "degraded"
            nodes[self.nas_node_id] = GraphNode(
                id=self.nas_node_id,
                label=f"NAS: {nas_status.host or 'Backup Server'}",
                type="nas",
                status=nas_node_status,
                meta={
                    "total_size_mb": nas_status.total_backup_size_mb,
                    "backup_count": len(nas_status.backups),
                },
            )

        domain_nodes: Dict[str, str] = {}

        for site in sites.sites:
            site_node_id = f"site-{site.name}"

            # Get backup status for site
            site_backup = None
            if site.name in backup_by_site:
                backup_info = backup_by_site[site.name]
                site_backup = NodeBackupStatus(
                    status=backup_info.status.value,
                    last_backup=backup_info.last_backup,
                    hours_since_backup=backup_info.hours_since_backup,
                    backup_size_mb=backup_info.backup_size_mb,
                )

            nodes[site_node_id] = GraphNode(
                id=site_node_id,
                label=f"Site: {site.name}",
                type="site",
                status=site.status,
                meta={"path": site.path, "services": len(site.services)},
                backup=site_backup,
            )

            # Connect site to NAS if backup exists
            if nas_status and site.name in backup_by_site:
                add_edge(site_node_id, self.nas_node_id, "backup")

            container_nodes = self._build_container_nodes(site, nodes, container_metrics)
            for container_id in container_nodes:
                add_edge(container_id, site_node_id, "deployed as")
                add_edge(self.gateway_node_id, container_id, "reverse proxy")

            for domain in site.caddy_domains or []:
                domain_node_id = domain_nodes.get(domain)
                if not domain_node_id:
                    domain_node_id = f"domain-{domain}"
                    domain_nodes[domain] = domain_node_id
                    nodes[domain_node_id] = GraphNode(
                        id=domain_node_id,
                        label=domain,
                        type="domain",
                        status=site.status,
                        meta={"targets": site.caddy_targets},
                    )
                # Connect: Cloudflare -> Domain -> Gateway
                add_edge(self.cloudflare_node_id, domain_node_id, "proxy")
                add_edge(domain_node_id, self.gateway_node_id, "reverse proxy")

        return GraphResponse(
            nodes=list(nodes.values()),
            edges=edges,
            nas_connected=nas_status.connected if nas_status else False,
            nas_error=nas_status.error if nas_status else None,
        )

    def _build_container_nodes(
        self,
        site: Site,
        nodes: dict[str, GraphNode],
        container_metrics: dict[str, ContainerMetrics] | None = None,
    ) -> list[str]:
        container_ids: list[str] = []
        for container in site.containers:
            container_id = f"container-{container.name}"

            # Get metrics for this container
            node_metrics = None
            if container_metrics and container.name in container_metrics:
                metrics = container_metrics[container.name]
                node_metrics = NodeMetrics(
                    cpu_percent=metrics.cpu_percent,
                    memory_percent=metrics.memory_percent,
                    memory_usage_mb=metrics.memory_usage_mb,
                    memory_limit_mb=metrics.memory_limit_mb,
                )

            nodes[container_id] = GraphNode(
                id=container_id,
                label=f"Container: {container.name}",
                type="container",
                status=self._container_status(container),
                meta={
                    "image": container.image,
                    "ports": ", ".join(
                        f"{p.public or 'int'}->{p.private}" for p in container.ports
                    ),
                },
                metrics=node_metrics,
            )
            container_ids.append(container_id)
        return container_ids

    @staticmethod
    def _container_status(container: ContainerStatus) -> str:
        if not container.status:
            return "unknown"
        if "Up" in container.status:
            return "running"
        if "Exited" in container.status:
            return "stopped"
        return "degraded"
