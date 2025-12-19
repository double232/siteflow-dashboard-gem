from __future__ import annotations

import os
from pathlib import Path


def resolve_local_path(raw_path: str | None) -> str:
    """Normalize user-provided paths so they work on Windows and Unix.

    - Expands ~
    - Converts WSL-style paths (/mnt/c/...) to Windows drive paths when running on Windows
    """
    if not raw_path:
        return ""

    path = os.path.expanduser(raw_path.strip())
    if os.name != "nt":
        return path

    # Normalize slashes for easier detection
    normalized = path.replace("\\", "/")
    if normalized.startswith("/mnt/"):
        parts = normalized.split("/")
        if len(parts) >= 4 and len(parts[2]) == 1:
            drive_letter = parts[2].upper()
            remainder = Path(*parts[3:])
            path = str(Path(f"{drive_letter}:\\") / remainder)

    return path

