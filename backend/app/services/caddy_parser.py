from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple


logger = logging.getLogger(__name__)

# Pattern to detect unexpanded environment variables like $VAR, ${VAR}, $DOMAIN, etc.
ENV_VAR_PATTERN = re.compile(r'\$\{?[A-Za-z_][A-Za-z0-9_]*\}?')


@dataclass
class CaddyRoute:
    hosts: list[str]
    reverse_proxies: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CaddyParseResult:
    routes: list[CaddyRoute]
    warnings: list[str]  # Global parsing warnings


def detect_unexpanded_vars(value: str, context: str) -> list[str]:
    """Detect unexpanded environment variables in a string."""
    warnings = []
    matches = ENV_VAR_PATTERN.findall(value)
    for match in matches:
        warning = f"Unexpanded env var '{match}' in {context}"
        warnings.append(warning)
        logger.warning(warning)
    return warnings


def validate_route(route: CaddyRoute) -> list[str]:
    """Validate a Caddy route and return warnings for issues."""
    warnings = []

    # Check for empty hosts
    if not route.hosts:
        warnings.append("Route has no hosts defined")
        logger.warning("Caddy route has no hosts defined")

    # Check for hosts with unexpanded vars
    for host in route.hosts:
        var_warnings = detect_unexpanded_vars(host, f"host '{host}'")
        warnings.extend(var_warnings)

        # Check for obviously malformed hosts
        if host and not host.replace("*", "").replace(".", "").replace("-", "").replace("_", "").replace(":", "").isalnum():
            if not host.startswith("http://") and not host.startswith("https://"):
                # Allow wildcards and normal domain patterns
                pass

    # Check reverse proxy targets
    for target in route.reverse_proxies:
        var_warnings = detect_unexpanded_vars(target, f"reverse_proxy target '{target}'")
        warnings.extend(var_warnings)

        # Check for malformed targets (should be host:port or just host)
        if target and not re.match(r'^[\w\.\-]+:\d+(/.*)?$', target) and not re.match(r'^[\w\.\-]+$', target):
            # Allow special Caddy directives
            if not target.startswith("{") and not target.startswith("@"):
                warning = f"Potentially malformed reverse_proxy target: '{target}'"
                warnings.append(warning)
                logger.warning(warning)

    # Check redirects
    for redirect in route.redirects:
        var_warnings = detect_unexpanded_vars(redirect, f"redirect '{redirect}'")
        warnings.extend(var_warnings)

    return warnings


def parse_caddyfile(raw: str) -> list[CaddyRoute]:
    """Parse Caddyfile and return routes. Use parse_caddyfile_with_warnings for detailed results."""
    result = parse_caddyfile_with_warnings(raw)
    return result.routes


def parse_caddyfile_with_warnings(raw: str) -> CaddyParseResult:
    """Parse Caddyfile and return routes with any warnings detected."""
    routes: List[CaddyRoute] = []
    global_warnings: List[str] = []
    brace_depth = 0
    current_route: CaddyRoute | None = None
    line_num = 0

    for raw_line in raw.splitlines():
        line_num += 1
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        opening = raw_line.count("{")
        closing = raw_line.count("}")

        if line.endswith("{") and brace_depth == 0:
            hosts_line = line[:-1].strip()
            hosts = [h.strip().strip(",") for h in hosts_line.split(",") if h.strip()]

            # Check for unexpanded vars in hosts
            for host in hosts:
                var_warnings = detect_unexpanded_vars(host, f"host on line {line_num}")
                global_warnings.extend(var_warnings)

            current_route = CaddyRoute(hosts=hosts)
            brace_depth = 1
            continue

        if current_route:
            if line.startswith("reverse_proxy"):
                target = line[len("reverse_proxy"):].strip()
                if target:
                    current_route.reverse_proxies.append(target)
                    # Check for unexpanded vars
                    var_warnings = detect_unexpanded_vars(target, f"reverse_proxy on line {line_num}")
                    current_route.warnings.extend(var_warnings)
            elif line.startswith("redir"):
                target = line[len("redir"):].strip()
                if target:
                    current_route.redirects.append(target)
                    # Check for unexpanded vars
                    var_warnings = detect_unexpanded_vars(target, f"redirect on line {line_num}")
                    current_route.warnings.extend(var_warnings)

        if brace_depth > 0:
            brace_depth += opening - closing
            if brace_depth <= 0 and current_route:
                # Validate the complete route
                route_warnings = validate_route(current_route)
                current_route.warnings.extend(route_warnings)
                routes.append(current_route)
                current_route = None
        else:
            brace_depth = max(brace_depth + opening - closing, 0)

    if current_route:
        # Handle unclosed block
        global_warnings.append(f"Unclosed block detected, route may be malformed")
        logger.warning("Caddyfile has unclosed block")
        route_warnings = validate_route(current_route)
        current_route.warnings.extend(route_warnings)
        routes.append(current_route)

    if global_warnings:
        logger.info(f"Caddyfile parsed with {len(global_warnings)} warnings")

    return CaddyParseResult(routes=routes, warnings=global_warnings)
