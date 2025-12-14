from __future__ import annotations

import httpx

from app.config import Settings
from app.schemas.cloudflare import (
    CloudflareConnector,
    CloudflareHostname,
    CloudflareStatus,
    CloudflareTunnel,
)
from app.services.cache import TimedCache


class CloudflareService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = TimedCache[CloudflareStatus](ttl_seconds=max(settings.cache_ttl_seconds, 30))

    def get_status(self, force_refresh: bool = False) -> CloudflareStatus:
        if not (self.settings.cf_account_id and self.settings.cf_api_token and self.settings.cf_tunnel_id):
            return CloudflareStatus(tunnel=None)

        def builder() -> CloudflareStatus:
            tunnel = self._fetch_tunnel()
            connections = self._fetch_connections()
            hostnames = self._fetch_hostnames()
            if tunnel:
                tunnel.connections = connections
                tunnel.hostnames = hostnames
            return CloudflareStatus(tunnel=tunnel)

        return self.cache.get(builder, force_refresh=force_refresh)

    # Internal HTTP helpers -------------------------------------------

    def _client(self) -> httpx.Client:
        headers = {
            "Authorization": f"Bearer {self.settings.cf_api_token}",
            "Content-Type": "application/json",
        }
        return httpx.Client(base_url="https://api.cloudflare.com/client/v4", headers=headers, timeout=15.0)

    def _fetch_tunnel(self) -> CloudflareTunnel | None:
        url = f"/accounts/{self.settings.cf_account_id}/cfd_tunnel/{self.settings.cf_tunnel_id}"
        with self._client() as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json().get("result")
            if not data:
                return None
            return CloudflareTunnel(
                id=data.get("id"),
                name=data.get("name"),
                status=data.get("status"),
            )

    def _fetch_connections(self) -> list[CloudflareConnector]:
        url = f"/accounts/{self.settings.cf_account_id}/cfd_tunnel/{self.settings.cf_tunnel_id}/connections"
        with self._client() as client:
            response = client.get(url)
            response.raise_for_status()
            results = response.json().get("result", [])
            connectors: list[CloudflareConnector] = []
            for item in results:
                connectors.append(
                    CloudflareConnector(
                        id=item.get("id"),
                        version=item.get("client_version"),
                        location=item.get("data_center"),
                        status=item.get("status"),
                    )
                )
            return connectors

    def _fetch_hostnames(self) -> list[CloudflareHostname]:
        url = f"/accounts/{self.settings.cf_account_id}/cfd_tunnel/{self.settings.cf_tunnel_id}/hostnames"
        with self._client() as client:
            response = client.get(url)
            response.raise_for_status()
            results = response.json().get("result", [])
            hostnames: list[CloudflareHostname] = []
            for item in results:
                hostnames.append(
                    CloudflareHostname(
                        hostname=item.get("hostname"),
                        service=item.get("service"),
                    )
                )
            return hostnames
