from functools import lru_cache

from fastapi import Header

from app.config import get_settings
from app.services.audit import AuditService
from app.services.backups import BackupExecutor, BackupService
from app.services.ssh_client import SSHClientManager
from app.services.cloudflare import CloudflareService
from app.services.graph_builder import GraphBuilder
from app.services.hetzner import HetznerService
from app.services.metrics_service import MetricsService
from app.services.nas_service import NASService
from app.services.provision import ProvisionService


def get_current_user_email(
    x_auth_request_email: str | None = Header(None, alias="X-Auth-Request-Email"),
    x_forwarded_user: str | None = Header(None, alias="X-Forwarded-User"),
) -> str | None:
    """Extract user email from oauth2-proxy headers.

    oauth2-proxy sets X-Auth-Request-Email when using --set-xauthrequest.
    Falls back to X-Forwarded-User if available.
    """
    return x_auth_request_email or x_forwarded_user


@lru_cache
def get_hetzner_service() -> HetznerService:
    return HetznerService(get_settings())


@lru_cache
def get_cloudflare_service() -> CloudflareService:
    return CloudflareService(get_settings())


@lru_cache
def get_graph_builder() -> GraphBuilder:
    return GraphBuilder()


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService(get_settings())


@lru_cache
def get_provision_service() -> ProvisionService:
    return ProvisionService(get_settings(), get_audit_service(), get_cloudflare_service())


@lru_cache
def get_metrics_service() -> MetricsService:
    return MetricsService(get_settings())


@lru_cache
def get_nas_service() -> NASService:
    return NASService(get_settings())


@lru_cache
def get_backup_service() -> BackupService:
    return BackupService(get_settings().sqlite_db_path)


@lru_cache
def get_backup_executor() -> BackupExecutor:
    settings = get_settings()
    ssh = SSHClientManager(settings)
    return BackupExecutor(ssh, get_backup_service())
