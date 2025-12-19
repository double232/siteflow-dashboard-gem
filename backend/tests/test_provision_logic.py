
import pytest
from unittest.mock import MagicMock, patch, ANY
from app.services.provision import ProvisionService
from app.schemas.provision import ProvisionRequest, TemplateType
from app.config import Settings
from app.schemas.audit import ActionType, ActionStatus

@pytest.fixture
def mock_settings():
    return Settings(
        hetzner_host="1.2.3.4",
        hetzner_user="root",
        hetzner_key_path="/tmp/key",
        remote_sites_root="/opt/sites",
        remote_gateway_root="/opt/gateway",
        remote_caddyfile="/opt/gateway/Caddyfile",
        cf_account_id="fake_acc_id",
        cf_api_token="fake_token",
        cf_tunnel_id="fake_tunnel",
    )

@patch("app.services.provision.SSHClientManager")
@patch("app.services.provision.CloudflareService")
@patch("app.services.provision.AuditService")
def test_provision_static_site_success(mock_audit_cls, mock_cf_cls, mock_ssh_cls, mock_settings):
    # Setup Mocks
    mock_ssh = mock_ssh_cls.return_value
    mock_cf = mock_cf_cls.return_value
    mock_audit = mock_audit_cls.return_value
    
    # Infinite side effect to avoid StopIteration
    mock_ssh.execute.side_effect = [
        MagicMock(exit_code=0, stdout="web_proxy\\n"), # check network
        MagicMock(exit_code=0, stdout="missing"),     # check existence
    ] + [MagicMock(exit_code=0, stdout="") for _ in range(20)]

    # Init Service
    service = ProvisionService(mock_settings, mock_audit, mock_cf)

    # Act
    req = ProvisionRequest(name="test-site", template=TemplateType.STATIC)
    response = service.provision_site(req)

    # Assert
    assert response.status == "success"
    assert response.name == "test-site"
    assert response.domain == "test-site.double232.com"
    
    # Verify SSH calls (Robust check)
    calls = [str(c) for c in mock_ssh.execute.mock_calls]
    
    # Check for mkdir command in any call
    mkdir_found = any("mkdir -p" in str(c) and "test-site" in str(c) for c in calls)
    assert mkdir_found, f"mkdir command not found in calls: {calls}"
    
    # Check for docker compose up
    compose_up_found = any("docker compose up" in str(c) for c in calls)
    assert compose_up_found, f"docker compose up not found in calls: {calls}"
    
    # Verify Cloudflare calls
    mock_cf.add_public_hostname.assert_called_with("test-site.double232.com", "http://localhost:80")
    
    # Verify Audit log
    mock_audit.log_action.assert_called_with(
        action_type=ActionType.SITE_PROVISION,
        target_type="site",
        target_name="test-site",
        status=ActionStatus.SUCCESS,
        output=ANY,
        metadata=ANY,
        duration_ms=ANY
    )

@patch("app.services.provision.SSHClientManager")
@patch("app.services.provision.CloudflareService")
@patch("app.services.provision.AuditService")
def test_provision_site_already_exists(mock_audit_cls, mock_cf_cls, mock_ssh_cls, mock_settings):
    mock_ssh = mock_ssh_cls.return_value
    mock_cf = mock_cf_cls.return_value
    mock_audit = mock_audit_cls.return_value

    mock_ssh.execute.side_effect = [
        MagicMock(exit_code=0, stdout="web_proxy\n"), 
        MagicMock(exit_code=0, stdout="exists")
    ]
    
    service = ProvisionService(mock_settings, mock_audit, mock_cf)
    req = ProvisionRequest(name="existing-site", template=TemplateType.STATIC)

    with pytest.raises(ValueError, match="already exists"):
        service.provision_site(req)

    mock_audit.log_action.assert_called_with(
        action_type=ActionType.SITE_PROVISION,
        target_type="site",
        target_name="existing-site",
        status=ActionStatus.FAILURE,
        error_message=ANY,
        metadata=ANY,
        duration_ms=ANY
    )
