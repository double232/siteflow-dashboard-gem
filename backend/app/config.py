from functools import lru_cache
import logging
import os
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils.path_utils import resolve_local_path


logger = logging.getLogger(__name__)


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""
    pass


class Settings(BaseSettings):
    """Application configuration pulled from environment variables or .env file."""

    hetzner_host: str = ""
    hetzner_user: str = "root"
    hetzner_port: int = 22
    hetzner_key_path: str = ""
    ssh_known_hosts: str | None = None
    ssh_timeout: int = 30

    remote_sites_root: str = "/opt/sites"
    remote_gateway_root: str = "/opt/gateway"
    remote_caddyfile: str = "/opt/gateway/Caddyfile"
    remote_data_root: str = "/opt/data"

    cache_ttl_seconds: int = 20
    enable_mock_data: bool = False

    cf_account_id: str | None = None
    cf_api_token: str | None = None
    cf_tunnel_id: str | None = None

    desktop_projects_root: str | None = None

    log_ssh_commands: bool = True

    # Database settings
    sqlite_db_path: str = "siteflow.db"
    audit_retention_days: int = 90
    audit_max_output_length: int = 10000

    # NAS settings (SMB/Samba)
    nas_host: str | None = None
    nas_user: str | None = None
    nas_password: str | None = None
    nas_share: str = "backups"
    nas_backup_path: str = ""
    nas_stale_threshold_hours: int = 48
    nas_poll_interval_seconds: int = 300

    # WebSocket settings
    ws_monitor_interval: float = 10.0

    # Uptime Kuma settings
    kuma_url: str = "http://uptime-kuma:3001"
    kuma_username: str = "admin"
    kuma_password: str = ""

    # CORS settings
    # Comma-separated list of allowed origins, or "*" for all (not recommended)
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # Environment (development, staging, production)
    environment: str = "development"

    # Auth settings (OAuth2 proxy headers)
    auth_header_email: str = "X-Forwarded-Email"  # Header containing user email from OAuth2 proxy
    auth_header_user: str = "X-Forwarded-User"    # Header containing username from OAuth2 proxy
    require_auth: bool = False                     # Require authentication in production

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    def validate_required(self) -> list[str]:
        """Validate required configuration settings.

        Returns a list of error messages for invalid settings.
        Raises ConfigurationError if critical settings are missing.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check required SSH settings
        if not self.hetzner_host:
            errors.append("HETZNER_HOST is required but not set")

        if not self.hetzner_user:
            errors.append("HETZNER_USER is required but not set")

        key_path = resolve_local_path(self.hetzner_key_path)
        if not key_path:
            errors.append("HETZNER_KEY_PATH is required but not set")
        else:
            if not os.path.exists(key_path):
                errors.append(f"SSH key file not found: {key_path}")
            elif not os.access(key_path, os.R_OK):
                errors.append(f"SSH key file not readable: {key_path}")

        # Check remote paths are set
        if not self.remote_sites_root:
            errors.append("REMOTE_SITES_ROOT is required but not set")

        if not self.remote_caddyfile:
            warnings.append("REMOTE_CADDYFILE not set, Caddy integration may not work")

        # Check CORS settings in production
        is_production = self.environment.lower() == "production"
        default_cors = "http://localhost:5173,http://localhost:3000"

        if is_production:
            if self.cors_allowed_origins == default_cors:
                errors.append(
                    "CORS_ALLOWED_ORIGINS is using default localhost values in production. "
                    "Set CORS_ALLOWED_ORIGINS to your actual domain(s) or this is a security risk."
                )
            if self.cors_allowed_origins == "*":
                errors.append(
                    "CORS_ALLOWED_ORIGINS is set to '*' (allow all) in production. "
                    "This is a security risk. Set specific allowed origins."
                )
            if not self.require_auth:
                warnings.append(
                    "REQUIRE_AUTH is False in production. "
                    "Consider enabling authentication via OAuth2 proxy."
                )

        # Log warnings
        for warning in warnings:
            logger.warning(f"Config warning: {warning}")

        return errors


def validate_config_on_startup(settings: Settings) -> None:
    """Validate configuration and exit if critical settings are missing."""
    errors = settings.validate_required()

    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        print("\nConfiguration Error:", file=sys.stderr)
        print("The following required settings are missing or invalid:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("\nPlease check your .env file or environment variables.", file=sys.stderr)
        raise ConfigurationError(f"Configuration validation failed: {'; '.join(errors)}")

    logger.info("Configuration validated successfully")


@lru_cache
def get_settings() -> Settings:
    return Settings()
