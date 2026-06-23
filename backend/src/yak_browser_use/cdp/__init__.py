"""CDP layer — Chrome DevTools Protocol connection, discovery, profiles, and session tracking."""

from __future__ import annotations

from .discover import discover_ws_url
from .launcher import (
    launch_user_chrome,
    launch_isolated_chrome,
    restart_user_chrome,
    cleanup_isolated,
)
from .playwright_bridge import PlaywrightBridge
from .helpers import CDPHelpers
from .profiles import (
    list_user_data_dirs,
    list_chrome_profiles,
    get_chrome_user_data_dir,
    get_active_profile,
    set_active_profile,
)
from .session import Session, get_session, set_session, list_sessions, remove_session

__all__ = [
    "discover_ws_url",
    "launch_user_chrome",
    "launch_isolated_chrome",
    "restart_user_chrome",
    "cleanup_isolated",
    "PlaywrightBridge",
    "CDPHelpers",
    "list_user_data_dirs",
    "list_chrome_profiles",
    "get_chrome_user_data_dir",
    "get_active_profile",
    "set_active_profile",
    "Session",
    "get_session",
    "set_session",
    "list_sessions",
    "remove_session",
]
