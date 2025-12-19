#!/usr/bin/env python3
"""
Test site management script for siteflow-dashboard.

Usage:
    python scripts/test_site.py provision [--name NAME] [--template TEMPLATE]
    python scripts/test_site.py start [--name NAME]
    python scripts/test_site.py stop [--name NAME]
    python scripts/test_site.py restart [--name NAME]
    python scripts/test_site.py deprovision [--name NAME] [--remove-volumes] [--remove-files]
    python scripts/test_site.py status [--name NAME]

Default test site name: siteflow-test
Default template: static
"""

import argparse
import sys
import json
import urllib.request
import urllib.error

DEFAULT_NAME = "siteflow-test"
DEFAULT_TEMPLATE = "static"
API_BASE = "http://localhost:8000"


def api_request(method: str, endpoint: str, data: dict | None = None) -> dict:
    """Make an API request and return JSON response."""
    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}

    body = json.dumps(data).encode("utf-8") if data else None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            error_json = json.loads(error_body)
            detail = error_json.get("detail", error_body)
        except json.JSONDecodeError:
            detail = error_body
        print(f"Error {e.code}: {detail}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}")
        print(f"Make sure the backend is running at {API_BASE}")
        sys.exit(1)


def provision(name: str, template: str) -> None:
    """Provision a new test site."""
    print(f"Provisioning site '{name}' with template '{template}'...")

    result = api_request("POST", "/api/provision/", {
        "name": name,
        "template": template,
    })

    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    if result.get("path"):
        print(f"Path: {result['path']}")
    if result.get("domain"):
        print(f"Domain: {result['domain']}")


def deprovision(name: str, remove_volumes: bool, remove_files: bool) -> None:
    """Deprovision a test site."""
    print(f"Deprovisioning site '{name}'...")
    if remove_volumes:
        print("  (will remove Docker volumes)")
    if remove_files:
        print("  (will remove site files)")

    result = api_request("DELETE", "/api/provision/", {
        "name": name,
        "remove_volumes": remove_volumes,
        "remove_files": remove_files,
    })

    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")


def site_action(name: str, action: str) -> None:
    """Start, stop, or restart a site."""
    print(f"Running '{action}' on site '{name}'...")

    result = api_request("POST", f"/api/sites/{name}/{action}", {})

    print(f"Status: {result.get('status', 'unknown')}")
    if result.get("message"):
        print(f"Message: {result['message']}")
    if result.get("output"):
        print(f"Output:\n{result['output']}")


def get_status(name: str) -> None:
    """Get site status."""
    print(f"Getting status for site '{name}'...")

    result = api_request("GET", "/api/sites", None)

    sites = result.get("sites", [])
    site = next((s for s in sites if s["name"] == name), None)

    if site:
        print(f"Name: {site['name']}")
        print(f"Status: {site['status']}")
        print(f"Path: {site['path']}")
        if site.get("caddy_domains"):
            print(f"Domains: {', '.join(site['caddy_domains'])}")
        if site.get("containers"):
            print("Containers:")
            for c in site["containers"]:
                print(f"  - {c['name']}: {c['status']}")
    else:
        print(f"Site '{name}' not found")
        print(f"Available sites: {[s['name'] for s in sites]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test site management for siteflow-dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # provision
    p_provision = subparsers.add_parser("provision", help="Create a new test site")
    p_provision.add_argument("--name", "-n", default=DEFAULT_NAME, help=f"Site name (default: {DEFAULT_NAME})")
    p_provision.add_argument("--template", "-t", default=DEFAULT_TEMPLATE,
                            choices=["static", "node", "python", "wordpress"],
                            help=f"Template type (default: {DEFAULT_TEMPLATE})")

    # deprovision
    p_deprovision = subparsers.add_parser("deprovision", help="Remove a test site")
    p_deprovision.add_argument("--name", "-n", default=DEFAULT_NAME, help=f"Site name (default: {DEFAULT_NAME})")
    p_deprovision.add_argument("--remove-volumes", "-v", action="store_true", help="Remove Docker volumes")
    p_deprovision.add_argument("--remove-files", "-f", action="store_true", help="Remove site files")

    # start
    p_start = subparsers.add_parser("start", help="Start a test site")
    p_start.add_argument("--name", "-n", default=DEFAULT_NAME, help=f"Site name (default: {DEFAULT_NAME})")

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop a test site")
    p_stop.add_argument("--name", "-n", default=DEFAULT_NAME, help=f"Site name (default: {DEFAULT_NAME})")

    # restart
    p_restart = subparsers.add_parser("restart", help="Restart a test site")
    p_restart.add_argument("--name", "-n", default=DEFAULT_NAME, help=f"Site name (default: {DEFAULT_NAME})")

    # status
    p_status = subparsers.add_parser("status", help="Get test site status")
    p_status.add_argument("--name", "-n", default=DEFAULT_NAME, help=f"Site name (default: {DEFAULT_NAME})")

    args = parser.parse_args()

    if args.command == "provision":
        provision(args.name, args.template)
    elif args.command == "deprovision":
        deprovision(args.name, args.remove_volumes, args.remove_files)
    elif args.command == "start":
        site_action(args.name, "start")
    elif args.command == "stop":
        site_action(args.name, "stop")
    elif args.command == "restart":
        site_action(args.name, "restart")
    elif args.command == "status":
        get_status(args.name)


if __name__ == "__main__":
    main()
