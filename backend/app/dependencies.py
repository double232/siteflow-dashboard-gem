from functools import lru_cache

from app.config import get_settings
from app.services.audit import AuditService
from app.services.cloudflare import CloudflareService
from app.services.graph_builder import GraphBuilder
from app.services.hetzner import HetznerService
from app.services.metrics_service import MetricsService
from app.services.nas_service import NASService
from app.services.provision import ProvisionService


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
