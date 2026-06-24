"""Chrome DevTools Protocol WebSocket URL discovery.

Provides 6 fallback levels:
1. YBU_CDP_URL env var → query /json/version
2. YBU_WSS_URL env var → direct WS URL
3. DevToolsActivePort file scan (Chrome/Edge/Brave profiles under %LOCALAPPDATA%)
4. Port scan (9222, 9223)
5. Launch user Chrome as fallback (delegated to launcher)
6. Launch isolated Playwright Chromium (delegated to launcher)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

# Reusable aiohttp session (lazily created).
_session: "aiohttp.ClientSession | None" = None


async def _get_session() -> "aiohttp.ClientSession":
    """Return the shared aiohttp ClientSession, creating it if needed."""
    global _session
    import aiohttp

    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def cleanup() -> None:
    """Close the shared aiohttp ClientSession on shutdown."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_json(url: str, timeout: float = 3.0) -> dict | None:
    """HTTP GET a JSON endpoint. Returns parsed dict or None."""
    import aiohttp

    try:
        session = await _get_session()
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        logger.debug("_fetch_json exception for url=%s", url, exc_info=True)
    logger.debug("_fetch_json failed for url=%s", url)
    return None


async def _check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if *port* on *host* is open."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        logger.debug("_check_port: failed for %s:%s", host, port, exc_info=True)
        return False


def _read_devtools_active_port(profile_path: Path) -> tuple[int, str] | None:
    """Read DevToolsActivePort file and return (port, ws_path)."""
    port_file = profile_path / "DevToolsActivePort"
    if not port_file.exists():
        return None
    try:
        text = port_file.read_text(encoding="utf-8").strip()
        lines = text.split("\n")
        if len(lines) >= 2:
            port = int(lines[0].strip())
            ws_path = lines[1].strip()
            return port, ws_path
    except (ValueError, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# Level-specific discovery functions
# ---------------------------------------------------------------------------

async def _ws_from_cdp_url(cdp_url: str) -> str | None:
    """Level 1: query *cdp_url*/json/version for webSocketDebuggerUrl."""
    if not cdp_url:
        return None
    url = cdp_url.rstrip("/") + "/json/version"
    data = await _fetch_json(url)
    if data and "webSocketDebuggerUrl" in data:
        return data["webSocketDebuggerUrl"]
    return None


async def _ws_from_devtools_active_port(
    profiles: list[Path],
) -> str | None:
    """Level 3: scan DevToolsActivePort files in browser user-data dirs."""
    for base_path in profiles:
        if not base_path.exists():
            continue
        result = _read_devtools_active_port(base_path)
        if result is None:
            for subdir in base_path.iterdir():
                if subdir.is_dir() and subdir.name != "System Profile":
                    result = _read_devtools_active_port(subdir)
                    if result:
                        break
        if result:
            port, ws_path = result
            ok = await _check_port("127.0.0.1", port)
            if ok:
                ws_url = f"ws://127.0.0.1:{port}{ws_path}"
                logger.debug("DevToolsActivePort -> %s", ws_url)
                return ws_url
    return None


async def _ws_from_port_scan() -> str | None:
    """Level 4: probe ports 9222 and 9223 for a CDP endpoint."""
    for port in (9222, 9223):
        ok = await _check_port("127.0.0.1", port)
        if not ok:
            continue
        data = await _fetch_json(f"http://127.0.0.1:{port}/json/version")
        if data and "webSocketDebuggerUrl" in data:
            ws_url = data["webSocketDebuggerUrl"]
            logger.debug("Port scan -> %s", ws_url)
            return ws_url
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def discover_ws_url(
    timeout: int = 30, profile_name: str | None = None
) -> str:
    """Discover a CDP WebSocket URL through 6 fallback levels.

    Parameters
    ----------
    timeout:
        Maximum time in seconds to wait for browser launch (levels 5-6).
    profile_name:
        Optional Chrome profile directory name for launch fallbacks.

    Returns
    -------
    A ``ws://`` or ``wss://`` URL.

    Raises
    ------
    RuntimeError
        If all 6 discovery levels fail.
    """
    # Overall timeout applied to levels 5-6 (browser launch)
    # Levels 1-4 have internal timeouts and should complete quickly
    try:
        ws_url = await asyncio.wait_for(
            _discover_inner(profile_name), timeout=timeout
        )
        return ws_url
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"Chrome discovery timed out after {timeout}s"
        )


async def _discover_inner(profile_name: str | None) -> str:
    """Inner discovery logic (no timeout)."""
    # Level 1: YBU_CDP_URL → query /json/version
    cdp_url = os.environ.get("YBU_CDP_URL", "").strip()
    if cdp_url:
        ws_url = await _ws_from_cdp_url(cdp_url)
        if ws_url:
            logger.info("Level 1: YBU_CDP_URL -> %s", ws_url)
            return ws_url

    # Level 2: YBU_WSS_URL → direct WS URL
    wss_url = os.environ.get("YBU_WSS_URL", "").strip()
    if wss_url:
        logger.info("Level 2: YBU_WSS_URL -> %s", wss_url)
        return wss_url

    # Level 3: DevToolsActivePort file scan
    from .profiles import list_user_data_dirs

    profiles = list_user_data_dirs()
    ws_url = await _ws_from_devtools_active_port(profiles)
    if ws_url:
        logger.info("Level 3: DevToolsActivePort -> %s", ws_url)
        return ws_url

    # Level 4: Port scan 9222/9223
    ws_url = await _ws_from_port_scan()
    if ws_url:
        logger.info("Level 4: Port scan -> %s", ws_url)
        return ws_url

    # Level 5: Launch user Chrome
    from .launcher import launch_user_chrome

    ws_url = await launch_user_chrome(profile_name)
    if ws_url:
        logger.info("Level 5: User Chrome -> %s", ws_url)
        return ws_url

    # Level 6: Launch isolated Playwright Chromium
    from .launcher import launch_isolated_chrome

    ws_url = await launch_isolated_chrome(profile_name)
    if ws_url:
        logger.info("Level 6: Isolated browser -> %s", ws_url)
        return ws_url

    raise RuntimeError(
        "Cannot discover Chrome WebSocket URL (all 6 levels failed)"
    )
