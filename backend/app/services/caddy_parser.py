from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class CaddyRoute:
    hosts: list[str]
    reverse_proxies: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)


def parse_caddyfile(raw: str) -> list[CaddyRoute]:
    routes: List[CaddyRoute] = []
    brace_depth = 0
    current_route: CaddyRoute | None = None

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        opening = raw_line.count("{")
        closing = raw_line.count("}")

        if line.endswith("{") and brace_depth == 0:
            hosts_line = line[:-1].strip()
            hosts = [h.strip().strip(",") for h in hosts_line.split(",") if h.strip()]
            current_route = CaddyRoute(hosts=hosts)
            brace_depth = 1
            continue

        if current_route:
            if line.startswith("reverse_proxy"):
                target = line[len("reverse_proxy"):].strip()
                if target:
                    current_route.reverse_proxies.append(target)
            elif line.startswith("redir"):
                target = line[len("redir"):].strip()
                if target:
                    current_route.redirects.append(target)

        if brace_depth > 0:
            brace_depth += opening - closing
            if brace_depth <= 0 and current_route:
                routes.append(current_route)
                current_route = None
        else:
            brace_depth = max(brace_depth + opening - closing, 0)

    if current_route:
        routes.append(current_route)
    return routes
