"""Tests for Caddy configuration parser."""

import pytest

from app.services.caddy_parser import (
    detect_unexpanded_vars,
    validate_route,
    CaddyParseResult,
    CaddyRoute,
    parse_caddyfile_with_warnings,
)


class TestDetectUnexpandedVars:
    """Test detection of unexpanded environment variables."""

    def test_detects_dollar_sign_vars(self):
        """Detects $VAR style variables."""
        warnings = detect_unexpanded_vars("reverse_proxy $BACKEND_HOST:8080", "test route")
        assert len(warnings) == 1
        assert "$BACKEND_HOST" in warnings[0]

    def test_detects_braced_vars(self):
        """Detects ${VAR} style variables."""
        warnings = detect_unexpanded_vars("reverse_proxy ${BACKEND_HOST}:8080", "test route")
        assert len(warnings) == 1
        assert "${BACKEND_HOST}" in warnings[0]

    def test_detects_multiple_vars(self):
        """Detects multiple variables in same string."""
        warnings = detect_unexpanded_vars(
            "reverse_proxy $HOST:$PORT",
            "test route"
        )
        assert len(warnings) == 2

    def test_no_warnings_for_expanded_values(self):
        """No warnings for normal values without variables."""
        warnings = detect_unexpanded_vars("reverse_proxy localhost:8080", "test route")
        assert len(warnings) == 0

    def test_no_warnings_for_empty_string(self):
        """No warnings for empty string."""
        warnings = detect_unexpanded_vars("", "test route")
        assert len(warnings) == 0

    def test_context_included_in_warning(self):
        """Warning includes context information."""
        warnings = detect_unexpanded_vars("$UNDEFINED_VAR", "Caddyfile line 42")
        assert len(warnings) == 1
        assert "Caddyfile line 42" in warnings[0]

    def test_detects_vars_in_middle_of_string(self):
        """Detects variables embedded in longer strings."""
        warnings = detect_unexpanded_vars(
            "https://$DOMAIN.example.com/path",
            "domain config"
        )
        assert len(warnings) == 1
        assert "$DOMAIN" in warnings[0]

    def test_handles_underscores_in_var_names(self):
        """Handles variable names with underscores."""
        warnings = detect_unexpanded_vars(
            "$MY_LONG_VARIABLE_NAME",
            "test"
        )
        assert len(warnings) == 1
        assert "$MY_LONG_VARIABLE_NAME" in warnings[0]

    def test_handles_numbers_in_var_names(self):
        """Handles variable names with numbers."""
        warnings = detect_unexpanded_vars(
            "$VAR123",
            "test"
        )
        assert len(warnings) == 1
        assert "$VAR123" in warnings[0]


class TestValidateRoute:
    """Test route validation."""

    def test_valid_reverse_proxy_route(self):
        """Valid reverse_proxy route passes."""
        route = CaddyRoute(
            hosts=["example.com"],
            reverse_proxies=["localhost:8080"]
        )
        warnings = validate_route(route)
        assert len(warnings) == 0

    def test_route_with_no_hosts(self):
        """Route with no hosts produces warning."""
        route = CaddyRoute(
            hosts=[],
            reverse_proxies=["localhost:8080"]
        )
        warnings = validate_route(route)
        assert len(warnings) >= 1
        assert any("no hosts" in w.lower() for w in warnings)

    def test_route_with_unexpanded_var_in_host(self):
        """Route with unexpanded var in host produces warning."""
        route = CaddyRoute(
            hosts=["$DOMAIN.example.com"],
            reverse_proxies=["localhost:8080"]
        )
        warnings = validate_route(route)
        assert len(warnings) >= 1
        assert any("$DOMAIN" in w for w in warnings)

    def test_route_with_unexpanded_var_in_proxy(self):
        """Route with unexpanded var in reverse_proxy produces warning."""
        route = CaddyRoute(
            hosts=["example.com"],
            reverse_proxies=["$BACKEND:8080"]
        )
        warnings = validate_route(route)
        assert len(warnings) >= 1
        assert any("$BACKEND" in w for w in warnings)

    def test_valid_route_with_redirect(self):
        """Valid route with redirect passes."""
        route = CaddyRoute(
            hosts=["example.com"],
            redirects=["https://www.example.com{uri}"]
        )
        warnings = validate_route(route)
        assert len(warnings) == 0


class TestCaddyParseResult:
    """Test CaddyParseResult dataclass."""

    def test_create_with_warnings(self):
        """CaddyParseResult can be created with warnings."""
        route = CaddyRoute(hosts=["test.com"])
        result = CaddyParseResult(
            routes=[route],
            warnings=["Warning 1", "Warning 2"]
        )
        assert len(result.routes) == 1
        assert len(result.warnings) == 2

    def test_create_with_empty_routes(self):
        """CaddyParseResult can be created with empty routes."""
        result = CaddyParseResult(routes=[], warnings=[])
        assert len(result.routes) == 0
        assert len(result.warnings) == 0

    def test_warnings_list_is_accessible(self):
        """Warnings list is accessible."""
        result_with = CaddyParseResult(routes=[], warnings=["warning"])
        result_without = CaddyParseResult(routes=[], warnings=[])

        assert len(result_with.warnings) == 1
        assert len(result_without.warnings) == 0


class TestParseCaddyfileWithWarnings:
    """Test full Caddyfile parsing."""

    def test_parse_simple_caddyfile(self):
        """Parse simple Caddyfile with single host."""
        caddyfile = """
example.com {
    reverse_proxy localhost:8080
}
"""
        result = parse_caddyfile_with_warnings(caddyfile)
        assert len(result.routes) == 1
        assert "example.com" in result.routes[0].hosts
        assert "localhost:8080" in result.routes[0].reverse_proxies

    def test_parse_caddyfile_with_unexpanded_var(self):
        """Parse Caddyfile with unexpanded environment variable."""
        caddyfile = """
$DOMAIN {
    reverse_proxy $BACKEND:8080
}
"""
        result = parse_caddyfile_with_warnings(caddyfile)
        assert len(result.routes) == 1
        # Should have warnings for unexpanded vars
        all_warnings = result.warnings + result.routes[0].warnings
        assert len(all_warnings) >= 1

    def test_parse_caddyfile_multiple_hosts(self):
        """Parse Caddyfile with multiple hosts."""
        caddyfile = """
site1.com {
    reverse_proxy app1:8080
}

site2.com {
    reverse_proxy app2:8080
}
"""
        result = parse_caddyfile_with_warnings(caddyfile)
        assert len(result.routes) == 2

    def test_parse_empty_caddyfile(self):
        """Parse empty Caddyfile."""
        result = parse_caddyfile_with_warnings("")
        assert len(result.routes) == 0
        assert len(result.warnings) == 0

    def test_parse_caddyfile_with_comments(self):
        """Parse Caddyfile with comments."""
        caddyfile = """
# This is a comment
example.com {
    # Another comment
    reverse_proxy localhost:8080
}
"""
        result = parse_caddyfile_with_warnings(caddyfile)
        assert len(result.routes) == 1


class TestUnexpandedVarsInRealConfigs:
    """Test detection with realistic Caddy config snippets."""

    def test_common_env_var_patterns(self):
        """Detects common environment variable patterns."""
        test_cases = [
            ("$DOMAIN", True),
            ("${DOMAIN}", True),
            ("$HTTP_PORT", True),
            ("${HTTPS_PORT}", True),
            ("$DB_HOST", True),
            ("example.com", False),
            ("localhost", False),
            ("127.0.0.1", False),
            ("site-name.double232.com", False),
        ]

        for value, should_warn in test_cases:
            warnings = detect_unexpanded_vars(value, "test")
            has_warning = len(warnings) > 0
            assert has_warning == should_warn, f"Expected {should_warn} for '{value}', got {has_warning}"

    def test_typical_caddyfile_lines(self):
        """Tests typical Caddyfile configuration lines."""
        # Should warn
        assert len(detect_unexpanded_vars("reverse_proxy $BACKEND", "line 1")) > 0
        assert len(detect_unexpanded_vars("{$SITE_DOMAIN}", "line 2")) > 0

        # Should not warn
        assert len(detect_unexpanded_vars("reverse_proxy myapp:8080", "line 3")) == 0
        assert len(detect_unexpanded_vars("site.example.com {", "line 4")) == 0
        assert len(detect_unexpanded_vars("tls internal", "line 5")) == 0

    def test_json_config_with_placeholders(self):
        """Tests JSON config values that might contain unexpanded vars."""
        config_values = [
            # Expanded values - no warnings
            ("localhost:8080", False),
            ("https://api.example.com", False),

            # Unexpanded - should warn
            ("$API_URL", True),
            ("${BACKEND_SERVICE}:8080", True),
            ("http://$HOST:$PORT/api", True),
        ]

        for value, should_warn in config_values:
            warnings = detect_unexpanded_vars(value, "json config")
            assert (len(warnings) > 0) == should_warn, f"Failed for '{value}'"
