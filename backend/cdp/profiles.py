"""Chrome profile discovery and management.

Lists user data directories for Chrome, Edge, and Brave, and reads
profile metadata from Local State.
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

_active_profile: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_profile", default=None
)


def get_active_profile() -> str | None:
    """Return the currently active profile name (from env or context var)."""
    return os.getenv("YBU_CHROME_PROFILE") or _active_profile.get()


def set_active_profile(name: str | None) -> None:
    """Set the active profile name for the current context."""
    _active_profile.set(name)


def list_user_data_dirs() -> list[Path]:
    """Return known browser user-data directories, ordered by priority.

    Priority: Edge > Chrome > Brave (Windows).
    """
    system = sys.platform
    dirs: list[Path] = []
    if system == "win32":
        user = os.environ.get("USERPROFILE", "")
        if user:
            dirs = [
                Path(user) / "AppData/Local/Microsoft/Edge/User Data",
                Path(user) / "AppData/Local/Google/Chrome/User Data",
                Path(user) / "AppData/Local/BraveSoftware/Brave-Browser/User Data",
            ]
    elif system == "darwin":
        home = os.environ.get("HOME", "")
        if home:
            dirs = [
                Path(home) / "Library/Application Support/Google/Chrome",
                Path(home) / "Library/Application Support/Microsoft Edge",
                Path(home) / "Library/Application Support/BraveSoftware/Brave-Browser",
            ]
    else:
        home = os.environ.get("HOME", "")
        if home:
            dirs = [
                Path(home) / ".config/google-chrome",
                Path(home) / ".config/microsoft-edge",
                Path(home) / ".config/brave",
            ]
    return dirs


def get_chrome_user_data_dir() -> Path | None:
    """Return the best available browser user-data directory.

    Prefers a path that already contains a ``Default`` profile.
    Falls back to the first existing data directory.
    """
    candidates = list_user_data_dirs()
    for p in candidates:
        if p.exists() and (p / "Default").is_dir():
            return p
    for p in candidates:
        if p.exists():
            return p
    return None


def list_chrome_profiles() -> list[dict[str, Any]]:
    """Parse Local State and return a list of known Chrome profiles.

    Returns a list of dicts with keys:
        directory, display_name, is_logged_in, user_name, is_ephemeral.
    """
    user_data_dir = get_chrome_user_data_dir()
    if not user_data_dir:
        return []

    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        return []

    try:
        data = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cannot read Local State (%s): %s", local_state_path, e)
        return []

    info_cache = data.get("profile", {}).get("info_cache", {})
    profiles = []
    for dir_name, info in info_cache.items():
        profiles.append({
            "directory": dir_name,
            "display_name": info.get("name", "")
            or info.get("gaia_name", "")
            or dir_name,
            "is_logged_in": bool(info.get("gaia_name") or info.get("user_name")),
            "user_name": info.get("gaia_name") or info.get("user_name") or "",
            "is_ephemeral": info.get("is_ephemeral", False),
        })

    profiles.sort(
        key=lambda p: (
            0 if p["directory"] == "Default" else 1,
            p["display_name"],
        )
    )
    return profiles
