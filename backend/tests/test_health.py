"""Tests for health endpoint models and helpers."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from app.routers.health import (
    ComponentStatus,
    SystemHealthResponse,
    HeartbeatEntry,
    MonitorStatus,
    HealthResponse,
    check_ssh_health,
    check_docker_health,
    check_caddy_health,
    check_database_health,
    check_uptime_kuma_health,
)


class TestComponentStatus:
    """Test ComponentStatus model."""

    def test_create_ok_status(self):
        """Create OK component status."""
        status = ComponentStatus(
            status="ok",
            message="All good",
            latency_ms=50.0
        )
        assert status.status == "ok"
        assert status.message == "All good"
        assert status.latency_ms == 50.0

    def test_create_error_status(self):
        """Create error component status."""
        status = ComponentStatus(
            status="error",
            message="Connection failed",
            latency_ms=None
        )
        assert status.status == "error"
        assert status.latency_ms is None

    def test_create_degraded_status(self):
        """Create degraded component status."""
        status = ComponentStatus(
            status="degraded",
            message="Slow response",
            latency_ms=5000.0
        )
        assert status.status == "degraded"

    def test_latency_defaults_to_none(self):
        """Latency defaults to None when not provided."""
        status = ComponentStatus(status="ok", message="OK")
        assert status.latency_ms is None


class TestSystemHealthResponse:
    """Test SystemHealthResponse model."""

    def test_create_healthy_response(self):
        """Create healthy system response."""
        response = SystemHealthResponse(
            status="healthy",
            ssh=ComponentStatus(status="ok", message="SSH OK"),
            docker=ComponentStatus(status="ok", message="Docker OK"),
            caddy=ComponentStatus(status="ok", message="Caddy OK"),
            database=ComponentStatus(status="ok", message="DB OK"),
            uptime_kuma=ComponentStatus(status="ok", message="Kuma OK"),
        )
        assert response.status == "healthy"
        assert response.ssh.status == "ok"

    def test_create_degraded_response(self):
        """Create degraded system response."""
        response = SystemHealthResponse(
            status="degraded",
            ssh=ComponentStatus(status="ok", message="SSH OK"),
            docker=ComponentStatus(status="ok", message="Docker OK"),
            caddy=ComponentStatus(status="degraded", message="Caddy slow"),
            database=ComponentStatus(status="ok", message="DB OK"),
            uptime_kuma=ComponentStatus(status="error", message="Kuma down"),
        )
        assert response.status == "degraded"

    def test_create_unhealthy_response(self):
        """Create unhealthy system response."""
        response = SystemHealthResponse(
            status="unhealthy",
            ssh=ComponentStatus(status="error", message="SSH failed"),
            docker=ComponentStatus(status="error", message="Docker failed"),
            caddy=ComponentStatus(status="error", message="Caddy failed"),
            database=ComponentStatus(status="error", message="DB failed"),
            uptime_kuma=ComponentStatus(status="error", message="Kuma failed"),
        )
        assert response.status == "unhealthy"


class TestHeartbeatEntry:
    """Test HeartbeatEntry model."""

    def test_create_heartbeat_up(self):
        """Create heartbeat entry for up status."""
        entry = HeartbeatEntry(status=1, time="2024-01-01T00:00:00Z", ping=50)
        assert entry.status == 1
        assert entry.ping == 50

    def test_create_heartbeat_down(self):
        """Create heartbeat entry for down status."""
        entry = HeartbeatEntry(status=0, time="2024-01-01T00:00:00Z", ping=None)
        assert entry.status == 0
        assert entry.ping is None

    def test_ping_is_optional(self):
        """Ping field is optional."""
        entry = HeartbeatEntry(status=1, time="2024-01-01T00:00:00Z")
        assert entry.ping is None


class TestMonitorStatus:
    """Test MonitorStatus model."""

    def test_create_up_monitor(self):
        """Create monitor with up status."""
        monitor = MonitorStatus(up=True, ping=50, uptime=99.5)
        assert monitor.up is True
        assert monitor.ping == 50
        assert monitor.uptime == 99.5

    def test_create_down_monitor(self):
        """Create monitor with down status."""
        monitor = MonitorStatus(up=False, uptime=50.0)
        assert monitor.up is False
        assert monitor.ping is None

    def test_heartbeats_default_empty(self):
        """Heartbeats default to empty list."""
        monitor = MonitorStatus(up=True)
        assert monitor.heartbeats == []

    def test_monitor_with_heartbeats(self):
        """Monitor with heartbeat history."""
        heartbeats = [
            HeartbeatEntry(status=1, time="2024-01-01T00:00:00Z", ping=50),
            HeartbeatEntry(status=1, time="2024-01-01T00:01:00Z", ping=55),
        ]
        monitor = MonitorStatus(up=True, heartbeats=heartbeats)
        assert len(monitor.heartbeats) == 2


class TestHealthResponse:
    """Test HealthResponse model."""

    def test_create_empty_monitors(self):
        """Create response with no monitors."""
        response = HealthResponse(monitors={})
        assert len(response.monitors) == 0

    def test_create_with_monitors(self):
        """Create response with monitors."""
        monitors = {
            "site1": MonitorStatus(up=True, ping=50),
            "site2": MonitorStatus(up=False),
        }
        response = HealthResponse(monitors=monitors)
        assert len(response.monitors) == 2
        assert response.monitors["site1"].up is True
        assert response.monitors["site2"].up is False


class TestCheckSshHealth:
    """Test SSH health check function."""

    @pytest.mark.asyncio
    async def test_ssh_healthy_returns_ok_status(self):
        """SSH health check returns ok when connection succeeds."""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.stdout = "ok"

        mock_ssh = MagicMock()
        mock_ssh.execute.return_value = mock_result

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            status = await check_ssh_health()

            assert status.status == "ok"
            assert "successful" in status.message.lower() or "ssh" in status.message.lower()
            assert status.latency_ms is not None

    @pytest.mark.asyncio
    async def test_ssh_unhealthy_returns_error_status(self):
        """SSH health check returns error when connection fails."""
        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_get_hetzner.side_effect = Exception("Connection refused")

            status = await check_ssh_health()

            assert status.status == "error"
            assert "Connection refused" in status.message or "failed" in status.message.lower()

    @pytest.mark.asyncio
    async def test_ssh_nonzero_exit_returns_error(self):
        """SSH health check returns error on non-zero exit code."""
        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.stdout = ""
        mock_result.stderr = "permission denied"

        mock_ssh = MagicMock()
        mock_ssh.execute.return_value = mock_result

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            status = await check_ssh_health()

            assert status.status == "error"


class TestCheckDockerHealth:
    """Test Docker health check function."""

    @pytest.mark.asyncio
    async def test_docker_healthy_returns_ok_status(self):
        """Docker health check returns ok when docker responds."""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.stdout = "24.0.0"

        mock_ssh = MagicMock()
        mock_ssh.execute.return_value = mock_result

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            status = await check_docker_health()

            assert status.status == "ok"
            assert "24.0.0" in status.message or "docker" in status.message.lower()

    @pytest.mark.asyncio
    async def test_docker_unhealthy_on_nonzero_exit(self):
        """Docker health check returns error on non-zero exit code."""
        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.stdout = ""
        mock_result.stderr = "docker: command not found"

        mock_ssh = MagicMock()
        mock_ssh.execute.return_value = mock_result

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            status = await check_docker_health()

            assert status.status == "error"

    @pytest.mark.asyncio
    async def test_docker_unhealthy_on_exception(self):
        """Docker health check returns error on exception."""
        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_get_hetzner.side_effect = Exception("SSH connection failed")

            status = await check_docker_health()

            assert status.status == "error"


class TestCheckCaddyHealth:
    """Test Caddy health check function."""

    @pytest.mark.asyncio
    async def test_caddy_healthy_returns_ok_status(self):
        """Caddy health check returns ok when Caddyfile is readable."""
        mock_ssh = MagicMock()
        mock_ssh.read_file.return_value = "example.com {\n    reverse_proxy localhost:8080\n}"

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            with patch('app.routers.health.get_settings') as mock_settings:
                mock_settings.return_value.remote_caddyfile = "/etc/caddy/Caddyfile"

                status = await check_caddy_health()

                assert status.status == "ok"
                assert "readable" in status.message.lower() or "caddy" in status.message.lower()

    @pytest.mark.asyncio
    async def test_caddy_degraded_on_empty_file(self):
        """Caddy health check returns degraded when Caddyfile is empty."""
        mock_ssh = MagicMock()
        mock_ssh.read_file.return_value = ""

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            with patch('app.routers.health.get_settings') as mock_settings:
                mock_settings.return_value.remote_caddyfile = "/etc/caddy/Caddyfile"

                status = await check_caddy_health()

                assert status.status == "degraded"
                assert "empty" in status.message.lower()

    @pytest.mark.asyncio
    async def test_caddy_error_on_file_not_found(self):
        """Caddy health check returns error when Caddyfile not found."""
        mock_ssh = MagicMock()
        mock_ssh.read_file.side_effect = FileNotFoundError("File not found")

        with patch('app.routers.health.get_hetzner_service') as mock_get_hetzner:
            mock_hetzner = MagicMock()
            mock_hetzner.ssh = mock_ssh
            mock_get_hetzner.return_value = mock_hetzner

            with patch('app.routers.health.get_settings') as mock_settings:
                mock_settings.return_value.remote_caddyfile = "/etc/caddy/Caddyfile"

                status = await check_caddy_health()

                assert status.status == "error"
                assert "not found" in status.message.lower()


class TestCheckDatabaseHealth:
    """Test database health check function."""

    @pytest.mark.asyncio
    async def test_database_healthy_returns_ok_status(self):
        """Database health check returns ok when DB is accessible."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch('app.routers.health.get_settings') as mock_settings:
            mock_settings.return_value.sqlite_db_path = "/tmp/test.db"

            with patch('sqlite3.connect', return_value=mock_conn):
                status = await check_database_health()

                assert status.status == "ok"
                assert "42" in status.message or "accessible" in status.message.lower()

    @pytest.mark.asyncio
    async def test_database_error_on_connection_failure(self):
        """Database health check returns error on connection failure."""
        import sqlite3

        with patch('app.routers.health.get_settings') as mock_settings:
            mock_settings.return_value.sqlite_db_path = "/tmp/test.db"

            with patch('sqlite3.connect', side_effect=sqlite3.Error("Cannot connect")):
                status = await check_database_health()

                assert status.status == "error"


class TestCheckUptimeKumaHealth:
    """Test Uptime Kuma health check function."""

    @pytest.mark.asyncio
    async def test_uptime_kuma_healthy_returns_ok_status(self):
        """Uptime Kuma health check returns ok when connected."""
        mock_sio = MagicMock()
        mock_sio.connected = True
        mock_sio.connect = AsyncMock()
        mock_sio.disconnect = AsyncMock()

        with patch('app.routers.health.socketio.AsyncClient', return_value=mock_sio):
            status = await check_uptime_kuma_health()

            assert status.status == "ok"
            assert "connected" in status.message.lower()

    @pytest.mark.asyncio
    async def test_uptime_kuma_degraded_on_error(self):
        """Uptime Kuma health check returns degraded on error (optional service)."""
        mock_sio = MagicMock()
        mock_sio.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with patch('app.routers.health.socketio.AsyncClient', return_value=mock_sio):
            status = await check_uptime_kuma_health()

            # Kuma is optional, so errors result in degraded, not error
            assert status.status == "degraded"
            assert "unavailable" in status.message.lower()

    @pytest.mark.asyncio
    async def test_uptime_kuma_error_on_timeout(self):
        """Uptime Kuma health check returns error on timeout."""
        mock_sio = MagicMock()

        async def slow_connect(*args, **kwargs):
            await asyncio.sleep(10)

        mock_sio.connect = slow_connect

        with patch('app.routers.health.socketio.AsyncClient', return_value=mock_sio):
            status = await check_uptime_kuma_health()

            assert status.status == "error"
            assert "timeout" in status.message.lower()
