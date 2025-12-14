from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")


@lru_cache
def get_settings() -> Settings:
    return Settings()
