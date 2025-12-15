"""Input validation and sanitization for SiteFlow.

Provides validators for site names, domains, branches, and git URLs to prevent
command injection and path traversal attacks.
"""

from __future__ import annotations

import re
import shlex
from urllib.parse import urlparse


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


# Allowed git hosts for cloning
ALLOWED_GIT_HOSTS = {
    "github.com",
    "gitlab.com",
    "bitbucket.org",
}


def validate_site_name(name: str) -> str:
    """Validate and sanitize a site name.

    Site names must be:
    - 1-63 characters long
    - Lowercase alphanumeric with hyphens
    - Cannot start or end with a hyphen
    - No consecutive hyphens

    Returns the validated name (lowercased).
    Raises ValidationError if invalid.
    """
    if not name:
        raise ValidationError("Site name cannot be empty")

    name = name.lower().strip()

    if len(name) > 63:
        raise ValidationError("Site name must be 63 characters or less")

    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', name):
        raise ValidationError(
            "Site name must be lowercase alphanumeric with optional hyphens, "
            "cannot start/end with hyphen"
        )

    if '--' in name:
        raise ValidationError("Site name cannot contain consecutive hyphens")

    return name


def validate_domain(domain: str) -> str:
    """Validate a domain name.

    Domains must be:
    - Valid hostname format
    - No path, query, or fragment components
    - No protocol prefix (will be stripped if present)

    Returns the validated domain.
    Raises ValidationError if invalid.
    """
    if not domain:
        raise ValidationError("Domain cannot be empty")

    domain = domain.strip().lower()

    # Strip protocol if present
    if domain.startswith("http://"):
        domain = domain[7:]
    elif domain.startswith("https://"):
        domain = domain[8:]

    # Remove trailing slash and any path
    domain = domain.split("/")[0]

    # Validate hostname format
    if not re.match(r'^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$', domain):
        raise ValidationError(f"Invalid domain format: {domain}")

    # Check each label
    labels = domain.split(".")
    if len(labels) < 2:
        raise ValidationError("Domain must have at least two labels (e.g., example.com)")

    for label in labels:
        if not label:
            raise ValidationError("Domain labels cannot be empty")
        if len(label) > 63:
            raise ValidationError("Domain labels must be 63 characters or less")
        if label.startswith("-") or label.endswith("-"):
            raise ValidationError("Domain labels cannot start or end with hyphen")

    return domain


def validate_branch(branch: str) -> str:
    """Validate a git branch name.

    Branch names:
    - Cannot contain shell metacharacters
    - Cannot start with - (flag injection)
    - Limited to safe characters

    Returns the validated branch.
    Raises ValidationError if invalid.
    """
    if not branch:
        raise ValidationError("Branch name cannot be empty")

    branch = branch.strip()

    if len(branch) > 255:
        raise ValidationError("Branch name too long")

    # Reject dangerous characters
    if branch.startswith("-"):
        raise ValidationError("Branch name cannot start with hyphen")

    # Allow alphanumeric, hyphens, underscores, slashes, dots
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._/-]*$', branch):
        raise ValidationError(
            "Branch name can only contain alphanumeric characters, "
            "hyphens, underscores, dots, and slashes"
        )

    # Reject path traversal
    if ".." in branch:
        raise ValidationError("Branch name cannot contain '..'")

    return branch


def validate_git_url(url: str, allow_any_host: bool = False) -> str:
    """Validate and normalize a git URL.

    - Converts git@ format to HTTPS
    - Validates against allowlisted hosts (unless allow_any_host=True)
    - Ensures .git suffix

    Returns normalized HTTPS URL.
    Raises ValidationError if invalid.
    """
    if not url:
        raise ValidationError("Git URL cannot be empty")

    url = url.strip()

    # Convert git@ format to HTTPS
    if url.startswith("git@"):
        match = re.match(r"git@([^:]+):(.+)", url)
        if not match:
            raise ValidationError(f"Invalid git@ URL format: {url}")
        host, path = match.groups()
        url = f"https://{host}/{path}"

    # Parse URL
    parsed = urlparse(url)

    # Require HTTPS
    if parsed.scheme not in ("https", "http"):
        raise ValidationError("Git URL must use HTTPS")

    if not parsed.netloc:
        raise ValidationError("Git URL must include a host")

    # Check against allowlist
    host = parsed.netloc.lower()
    if not allow_any_host and host not in ALLOWED_GIT_HOSTS:
        raise ValidationError(
            f"Git host '{host}' not allowed. "
            f"Allowed hosts: {', '.join(sorted(ALLOWED_GIT_HOSTS))}"
        )

    # Ensure .git suffix
    path = parsed.path
    if not path.endswith(".git"):
        path = path.rstrip("/") + ".git"

    return f"https://{host}{path}"


def validate_container_name(name: str) -> str:
    """Validate a Docker container name.

    Container names must match Docker's naming rules:
    - Alphanumeric, hyphens, underscores
    - Cannot start with hyphen

    Returns validated name.
    Raises ValidationError if invalid.
    """
    if not name:
        raise ValidationError("Container name cannot be empty")

    name = name.strip()

    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$', name):
        raise ValidationError(
            "Container name must be alphanumeric with optional "
            "hyphens, underscores, and dots"
        )

    if len(name) > 128:
        raise ValidationError("Container name too long")

    return name


def quote_shell_arg(arg: str) -> str:
    """Safely quote a string for use in shell commands.

    Uses shlex.quote to prevent shell injection.
    """
    return shlex.quote(arg)


def safe_path_join(base: str, *parts: str) -> str:
    """Safely join path components, preventing traversal.

    Validates that the result stays within the base directory.
    """
    import os

    # Normalize base
    base = os.path.normpath(base)

    # Join and normalize
    result = base
    for part in parts:
        # Reject absolute paths and traversal
        if os.path.isabs(part):
            raise ValidationError("Path component cannot be absolute")
        if ".." in part:
            raise ValidationError("Path component cannot contain '..'")
        result = os.path.normpath(os.path.join(result, part))

    # Verify result is under base
    if not result.startswith(base):
        raise ValidationError("Path traversal detected")

    return result
