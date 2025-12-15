from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings


logger = logging.getLogger(__name__)
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

    # Public hostname management -------------------------------------------

    def _get_tunnel_config(self) -> dict[str, Any]:
        """Fetch the current tunnel configuration."""
        url = f"/accounts/{self.settings.cf_account_id}/cfd_tunnel/{self.settings.cf_tunnel_id}/configurations"
        with self._client() as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json().get("result", {})

    def _update_tunnel_config(self, config: dict[str, Any]) -> bool:
        """Update the tunnel configuration."""
        url = f"/accounts/{self.settings.cf_account_id}/cfd_tunnel/{self.settings.cf_tunnel_id}/configurations"
        with self._client() as client:
            response = client.put(url, json={"config": config})
            response.raise_for_status()
            return response.json().get("success", False)

    def add_public_hostname(self, hostname: str, service: str) -> bool:
        """Add a public hostname to the tunnel.

        Args:
            hostname: The public hostname (e.g., test.double232.com)
            service: The backend service URL (e.g., http://test:80)

        Returns:
            True if successful, False otherwise
        """
        if not (self.settings.cf_account_id and self.settings.cf_api_token and self.settings.cf_tunnel_id):
            logger.warning("Cloudflare credentials not configured, skipping hostname creation")
            return False

        try:
            config = self._get_tunnel_config()
            ingress = config.get("config", {}).get("ingress", [])

            # Check if hostname already exists
            for entry in ingress:
                if entry.get("hostname") == hostname:
                    logger.info(f"Hostname {hostname} already exists in tunnel config")
                    return True

            # Add new hostname before the catch-all rule (last entry)
            new_entry = {
                "hostname": hostname,
                "service": service,
            }

            # Insert before the last catch-all entry (if it exists)
            if ingress and ingress[-1].get("service") == "http_status:404":
                ingress.insert(-1, new_entry)
            else:
                ingress.append(new_entry)
                # Ensure catch-all exists
                ingress.append({"service": "http_status:404"})

            # Update config
            new_config = config.get("config", {})
            new_config["ingress"] = ingress

            success = self._update_tunnel_config(new_config)
            if success:
                logger.info(f"Added hostname {hostname} -> {service} to tunnel")
                self.cache.invalidate()
            return success

        except Exception as e:
            logger.error(f"Failed to add hostname {hostname}: {e}")
            return False

    def remove_public_hostname(self, hostname: str) -> bool:
        """Remove a public hostname from the tunnel.

        Args:
            hostname: The public hostname to remove

        Returns:
            True if successful, False otherwise
        """
        if not (self.settings.cf_account_id and self.settings.cf_api_token and self.settings.cf_tunnel_id):
            logger.warning("Cloudflare credentials not configured, skipping hostname removal")
            return False

        try:
            config = self._get_tunnel_config()
            ingress = config.get("config", {}).get("ingress", [])

            # Filter out the hostname
            original_len = len(ingress)
            ingress = [entry for entry in ingress if entry.get("hostname") != hostname]

            if len(ingress) == original_len:
                logger.info(f"Hostname {hostname} not found in tunnel config")
                return True

            # Update config
            new_config = config.get("config", {})
            new_config["ingress"] = ingress

            success = self._update_tunnel_config(new_config)
            if success:
                logger.info(f"Removed hostname {hostname} from tunnel")
                self.cache.invalidate()
            return success

        except Exception as e:
            logger.error(f"Failed to remove hostname {hostname}: {e}")
            return False

    # DNS Record management -------------------------------------------

    def _get_zone_id(self, hostname: str) -> str | None:
        """Get the zone ID for a hostname by extracting the root domain."""
        parts = hostname.split(".")
        if len(parts) < 2:
            return None

        # Try progressively shorter domain names to find the zone
        for i in range(len(parts) - 1):
            domain = ".".join(parts[i:])
            with self._client() as client:
                response = client.get("/zones", params={"name": domain})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("result"):
                        return data["result"][0]["id"]
        return None

    def _get_dns_record(self, zone_id: str, hostname: str) -> dict[str, Any] | None:
        """Get an existing DNS record by hostname."""
        with self._client() as client:
            response = client.get(f"/zones/{zone_id}/dns_records", params={"name": hostname, "type": "CNAME"})
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("result"):
                    return data["result"][0]
        return None

    def add_dns_record(self, hostname: str) -> bool:
        """Create a DNS CNAME record pointing to the tunnel.

        Args:
            hostname: The hostname to create a DNS record for

        Returns:
            True if successful, False otherwise
        """
        if not (self.settings.cf_account_id and self.settings.cf_api_token and self.settings.cf_tunnel_id):
            logger.warning("Cloudflare credentials not configured, skipping DNS record creation")
            return False

        try:
            zone_id = self._get_zone_id(hostname)
            if not zone_id:
                logger.error(f"Could not find zone for hostname {hostname}")
                return False

            # Check if record already exists
            existing = self._get_dns_record(zone_id, hostname)
            if existing:
                logger.info(f"DNS record for {hostname} already exists")
                return True

            # Create CNAME record pointing to tunnel
            tunnel_target = f"{self.settings.cf_tunnel_id}.cfargotunnel.com"
            record_data = {
                "type": "CNAME",
                "name": hostname,
                "content": tunnel_target,
                "proxied": True,
                "ttl": 1,  # Auto TTL when proxied
            }

            with self._client() as client:
                response = client.post(f"/zones/{zone_id}/dns_records", json=record_data)
                response.raise_for_status()
                data = response.json()
                if data.get("success"):
                    logger.info(f"Created DNS record {hostname} -> {tunnel_target}")
                    return True
                else:
                    logger.error(f"Failed to create DNS record: {data.get('errors')}")
                    return False

        except Exception as e:
            logger.error(f"Failed to create DNS record for {hostname}: {e}")
            return False

    def remove_dns_record(self, hostname: str) -> bool:
        """Remove a DNS record.

        Args:
            hostname: The hostname to remove the DNS record for

        Returns:
            True if successful, False otherwise
        """
        if not (self.settings.cf_account_id and self.settings.cf_api_token and self.settings.cf_tunnel_id):
            logger.warning("Cloudflare credentials not configured, skipping DNS record removal")
            return False

        try:
            zone_id = self._get_zone_id(hostname)
            if not zone_id:
                logger.error(f"Could not find zone for hostname {hostname}")
                return False

            # Get the record to delete
            existing = self._get_dns_record(zone_id, hostname)
            if not existing:
                logger.info(f"DNS record for {hostname} does not exist")
                return True

            record_id = existing["id"]
            with self._client() as client:
                response = client.delete(f"/zones/{zone_id}/dns_records/{record_id}")
                response.raise_for_status()
                data = response.json()
                if data.get("success"):
                    logger.info(f"Deleted DNS record for {hostname}")
                    return True
                else:
                    logger.error(f"Failed to delete DNS record: {data.get('errors')}")
                    return False

        except Exception as e:
            logger.error(f"Failed to delete DNS record for {hostname}: {e}")
            return False
