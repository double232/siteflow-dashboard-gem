"""Tests for configuration validation."""

import os
import pytest
from unittest.mock import patch

from app.config import Settings, ConfigurationError, validate_config_on_startup


class TestSettingsValidation:
    """Test Settings.validate_required() method."""

    def test_default_settings_pass_in_development(self):
        """Default settings are valid in development when required fields are set."""
        # Create a temporary SSH key file for testing
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(os, 'access', return_value=True):
                settings = Settings(
                    hetzner_host="test-host",
                    hetzner_user="test-user",
                    hetzner_key_path="/path/to/key",
                    remote_sites_root="/opt/sites",
                    environment="development",
                )
                errors = settings.validate_required()
                assert len(errors) == 0

    def test_missing_hetzner_host_fails(self):
        """Missing HETZNER_HOST produces error."""
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(os, 'access', return_value=True):
                settings = Settings(
                    hetzner_host="",  # Empty
                    hetzner_user="test-user",
                    hetzner_key_path="/path/to/key",
                    environment="development",
                )
                errors = settings.validate_required()
                assert any("HETZNER_HOST" in e for e in errors)

    def test_missing_ssh_key_path_fails(self):
        """Missing SSH key path produces error."""
        settings = Settings(
            hetzner_host="test-host",
            hetzner_user="test-user",
            hetzner_key_path="",  # Empty
            environment="development",
        )
        errors = settings.validate_required()
        assert any("HETZNER_KEY_PATH" in e for e in errors)

    def test_nonexistent_ssh_key_fails(self):
        """Non-existent SSH key file produces error."""
        with patch.object(os.path, 'exists', return_value=False):
            settings = Settings(
                hetzner_host="test-host",
                hetzner_user="test-user",
                hetzner_key_path="/nonexistent/key",
                environment="development",
            )
            errors = settings.validate_required()
            assert any("not found" in e for e in errors)

    def test_default_cors_fails_in_production(self):
        """Default CORS settings fail in production."""
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(os, 'access', return_value=True):
                settings = Settings(
                    hetzner_host="test-host",
                    hetzner_user="test-user",
                    hetzner_key_path="/path/to/key",
                    environment="production",
                    cors_allowed_origins="http://localhost:5173,http://localhost:3000",  # Default
                )
                errors = settings.validate_required()
                assert any("CORS_ALLOWED_ORIGINS" in e for e in errors)

    def test_wildcard_cors_fails_in_production(self):
        """Wildcard CORS fails in production."""
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(os, 'access', return_value=True):
                settings = Settings(
                    hetzner_host="test-host",
                    hetzner_user="test-user",
                    hetzner_key_path="/path/to/key",
                    environment="production",
                    cors_allowed_origins="*",
                )
                errors = settings.validate_required()
                assert any("*" in e or "all" in e.lower() for e in errors)

    def test_custom_cors_passes_in_production(self):
        """Custom CORS settings pass in production."""
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(os, 'access', return_value=True):
                settings = Settings(
                    hetzner_host="test-host",
                    hetzner_user="test-user",
                    hetzner_key_path="/path/to/key",
                    environment="production",
                    cors_allowed_origins="https://dashboard.example.com",
                )
                errors = settings.validate_required()
                # Should only have CORS warnings if any, not localhost errors
                cors_errors = [e for e in errors if "localhost" in e.lower() or "*" in e]
                assert len(cors_errors) == 0


class TestConfigurationError:
    """Test ConfigurationError exception."""

    def test_configuration_error_is_runtime_error(self):
        """ConfigurationError inherits from RuntimeError."""
        exc = ConfigurationError("test error")
        assert isinstance(exc, RuntimeError)

    def test_configuration_error_stores_message(self):
        """ConfigurationError stores message."""
        exc = ConfigurationError("my error message")
        assert "my error message" in str(exc)


class TestValidateConfigOnStartup:
    """Test validate_config_on_startup function."""

    def test_valid_config_does_not_raise(self):
        """Valid configuration does not raise."""
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(os, 'access', return_value=True):
                settings = Settings(
                    hetzner_host="test-host",
                    hetzner_user="test-user",
                    hetzner_key_path="/path/to/key",
                    environment="development",
                )
                # Should not raise
                validate_config_on_startup(settings)

    def test_invalid_config_raises_configuration_error(self):
        """Invalid configuration raises ConfigurationError."""
        settings = Settings(
            hetzner_host="",  # Missing
            hetzner_user="test-user",
            hetzner_key_path="",  # Missing
            environment="development",
        )
        with pytest.raises(ConfigurationError):
            validate_config_on_startup(settings)


class TestRequireAuth:
    """Test authentication requirement settings."""

    def test_require_auth_default_is_false(self):
        """require_auth defaults to False."""
        settings = Settings(
            hetzner_host="test-host",
            hetzner_user="test-user",
            hetzner_key_path="/path/to/key",
        )
        assert settings.require_auth is False

    def test_require_auth_can_be_enabled(self):
        """require_auth can be enabled."""
        settings = Settings(
            hetzner_host="test-host",
            hetzner_user="test-user",
            hetzner_key_path="/path/to/key",
            require_auth=True,
        )
        assert settings.require_auth is True
