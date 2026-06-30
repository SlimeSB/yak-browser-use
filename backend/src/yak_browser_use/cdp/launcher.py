"""Chrome launching utilities.

Provides functions to start/restart a user-installed Chrome with
``--remote-debugging-port``, or to launch an isolated Playwright
Chromium instance as a last resort.
"""

from __future__ import annotations

import asyncio
import locale
import os
import platform
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from yak_browser_use.utils._path import temp_root
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

# Module-level state for active processes
_user_chrome_process: Any = None
_playwright_instance: Any = None
_playwright_browser: Any = None
_launched_pids: set[int] = set()
_temp_user_data_dir: str | None = None  # set when profile_name not given; cleaned on shutdown

# Base directory for isolated profiles
_ISO_PROFILES_DIR = Path.home() / ".yak-browser-use" / "profiles"


def _detect_lang() -> str:
    try:
        code, _ = locale.getdefaultlocale()
        if code:
            lang = code.replace("_", "-")
            return lang
    except Exception:
        logger.debug("_detect_lang: locale detection failed, falling back to zh-CN", exc_info=True)
    return "zh-CN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_chrome_exe() -> str | None:
    """Locate a Chrome/Edge/Chromium executable on the system."""
    candidates: list[Path] = []
    system = platform.system()
    if system == "Windows":
        prog = os.environ.get("ProgramFiles", "C:\\Program Files")
        prog86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        local = Path.home() / "AppData/Local"
        candidates = [
            Path(prog86) / "Microsoft/Edge/Application/msedge.exe",
            local / "Microsoft/Edge/Application/msedge.exe",
            Path(prog) / "Google/Chrome/Application/chrome.exe",
            Path(prog86) / "Google/Chrome/Application/chrome.exe",
            local / "Google/Chrome/Application/chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
        ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def get_isolated_profile_dir(name: str) -> Path:
    """Return the path to an isolated profile directory for *name*."""
    return _ISO_PROFILES_DIR / name


# ---------------------------------------------------------------------------
# Launch functions
# ---------------------------------------------------------------------------

async def launch_user_chrome(profile_name: str | None = None) -> str | None:
    """Start user-installed Chrome with remote debugging on port 9222.

    Returns the ``webSocketDebuggerUrl`` on success, or ``None`` if no
    Chrome executable is found.
    """
    global _user_chrome_process

    # Terminate any previously launched user Chrome process
    if _user_chrome_process is not None:
        try:
            _user_chrome_process.terminate()
            await _user_chrome_process.wait()
        except Exception:
            logger.debug("launch_user_chrome: failed to terminate previous process", exc_info=True)

    port = 9222

    # Check if a browser is already listening on port 9222
    from .discover import _check_port, _fetch_json

    if await _check_port("127.0.0.1", port):
        logger.info("Port %d in use — checking for existing debug endpoint", port)
        data = await _fetch_json(f"http://127.0.0.1:{port}/json/version")
        if data and "webSocketDebuggerUrl" in data:
            return data["webSocketDebuggerUrl"]

    exe = _find_chrome_exe()
    if not exe:
        logger.info("No Chrome/Edge executable found")
        return None

    logger.info("Launching user Chrome with profile=%s", profile_name)
    try:
        args = [
            exe,
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            "--force-renderer-accessibility",
            f"--lang={_detect_lang()}",
        ]
        if profile_name:
            args.append(f"--profile-directory={profile_name}")

        _user_chrome_process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to launch Chrome: {e}") from e

    if _user_chrome_process.pid:
        _launched_pids.add(_user_chrome_process.pid)

    for i in range(30):
        logger.debug("launch_user_chrome: retry %d/30", i + 1)

        returncode = _user_chrome_process.returncode
        if returncode is not None:
            logger.info("Chrome exited early (code=%d)", returncode)
            if _user_chrome_process.pid:
                _launched_pids.discard(_user_chrome_process.pid)
            _user_chrome_process = None
            return None

        data = await _fetch_json(
            f"http://127.0.0.1:{port}/json/version", timeout=2.0
        )
        if data and "webSocketDebuggerUrl" in data:
            logger.info("launch_user_chrome: ready on port %d", port)
            return data["webSocketDebuggerUrl"]
        await asyncio.sleep(0.5)

    logger.warning("launch_user_chrome: timed out waiting for debug port")
    if _user_chrome_process is not None:
        try:
            _user_chrome_process.terminate()
        except Exception:
            logger.debug("launch_user_chrome: failed to terminate on timeout", exc_info=True)
        if _user_chrome_process.pid:
            _launched_pids.discard(_user_chrome_process.pid)
        _user_chrome_process = None
    return None


async def launch_isolated_chrome(
    profile_name: str | None = None,
) -> str:
    """Launch an isolated browser as the last resort.

    If Edge is detected it is launched directly; otherwise Playwright's
    bundled Chromium is used.

    Returns the ``webSocketDebuggerUrl``.
    """
    global _playwright_instance, _playwright_browser, _user_chrome_process, _temp_user_data_dir

    logger.info("Launching isolated browser, profile=%s", profile_name or "temp")

    exe = _find_chrome_exe()

    # Pick a random available port, then release it immediately
    # so the browser can bind to it
    port_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        port_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port_sock.bind(("127.0.0.1", 0))
        port = port_sock.getsockname()[1]
    except Exception:
        port_sock.close()
        raise
    port_sock.close()  # Release port — browser needs to bind it

    if profile_name:
        user_data_dir = str(get_isolated_profile_dir(profile_name))
        os.makedirs(user_data_dir, exist_ok=True)
    else:
        ts = str(int(__import__("time").time()))
        user_data_dir = str(temp_root() / f"ybu_chrome_{ts}")
        os.makedirs(user_data_dir, exist_ok=True)
        _temp_user_data_dir = user_data_dir

    # Terminate any previously launched process before overwriting
    if _user_chrome_process is not None:
        try:
            if _user_chrome_process.pid:
                _launched_pids.discard(_user_chrome_process.pid)
            _user_chrome_process.terminate()
            await _user_chrome_process.wait()
        except Exception:
            logger.debug("launch_isolated: failed to terminate previous chrome", exc_info=True)
        _user_chrome_process = None
    if _playwright_browser is not None:
        try:
            await _playwright_browser.close()
        except Exception:
            logger.debug("launch_isolated: failed to close playwright browser", exc_info=True)
        _playwright_browser = None
    if _playwright_instance is not None:
        try:
            await _playwright_instance.stop()
        except Exception:
            logger.debug("launch_isolated: failed to stop playwright instance", exc_info=True)
        _playwright_instance = None
    try:

        if exe and "msedge" in exe.lower():
            logger.info("Launching Edge via subprocess with profile: %s", user_data_dir)

            try:
                _user_chrome_process = await asyncio.create_subprocess_exec(
                    exe,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={user_data_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--remote-allow-origins=*",
                    "--force-renderer-accessibility",
                    f"--lang={_detect_lang()}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                if _user_chrome_process.pid:
                    _launched_pids.add(_user_chrome_process.pid)
            except Exception as e:
                raise RuntimeError(f"Failed to launch Edge: {e}") from e
        else:
            logger.info("No Edge detected, falling back to Playwright bundled Chromium")

            try:
                from playwright.async_api import async_playwright
            except ImportError:
                raise RuntimeError(
                    "Cannot find or launch Chrome. "
                    "Ensure Chrome is running, or install playwright "
                    "(`uv add playwright && playwright install chromium`)."
                )

            try:
                _playwright_instance = await async_playwright().start()
                _playwright_browser = await _playwright_instance.chromium.launch(
                    headless=False,
                    channel=None,
                    args=[
                        f"--remote-debugging-port={port}",
                        f"--user-data-dir={user_data_dir}",
                        "--force-renderer-accessibility",
                        f"--lang={_detect_lang()}",
                    ],
                )
            except Exception as e:
                raise RuntimeError(f"Failed to launch Playwright browser: {e}") from e

        from .discover import _fetch_json

        for i in range(30):
            logger.debug("launch_isolated_chrome: retry %d/30", i + 1)
            data = await _fetch_json(
                f"http://127.0.0.1:{port}/json/version", timeout=2.0
            )
            if data and "webSocketDebuggerUrl" in data:
                logger.info("launch_isolated_chrome: ready on port %d", port)
                return data["webSocketDebuggerUrl"]
            await asyncio.sleep(0.5)

        raise RuntimeError(
            "Cannot obtain isolated browser WS URL (browser launch timed out)."
        )
    except Exception:
        await cleanup_isolated()
        raise



async def restart_user_chrome() -> str:
    """Force-kill existing Chrome processes and relaunch with debugging.

    Falls back to :func:`launch_isolated_chrome` if user Chrome cannot
    be started.
    """
    global _user_chrome_process

    exe = _find_chrome_exe()
    if not exe:
        raise RuntimeError("No Chrome/Edge browser found")

    # Find a user-data directory
    from .profiles import list_user_data_dirs

    profile_dir: str | None = None
    for base in list_user_data_dirs():
        if base.exists():
            profile_dir = str(base)
            break
    if not profile_dir:
        raise RuntimeError("No Chrome/Edge user data directory found")

    exe_lower = exe.lower()
    proc_name = "msedge.exe" if "edge" in exe_lower else "chrome.exe"

    logger.info("Killing existing browser processes (PIDs: %s)", _launched_pids)
    killed_pids = list(_launched_pids)
    for pid in killed_pids:
        try:
            if platform.system() == "Windows":
                await asyncio.to_thread(
                    subprocess.run, ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=10,
                )
            else:
                await asyncio.to_thread(
                    subprocess.run, ["kill", "-9", str(pid)], timeout=10,
                )
        except Exception:
            logger.debug("Failed to kill PID %d", pid, exc_info=True)
    _launched_pids.clear()

    # Also kill crashpad handler helper
    if platform.system() == "Windows":
        try:
            await asyncio.to_thread(
                subprocess.run, ["taskkill", "/F", "/IM", "chrome_crashpad_handler.exe"],
                capture_output=True, timeout=5,
            )
        except Exception:
            logger.debug("Failed to kill chrome_crashpad_handler", exc_info=True)

    await asyncio.sleep(3.0)

    # Verify killed PIDs are gone; retry if any still alive
    if platform.system() == "Windows" and killed_pids:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["tasklist", "/NH"],
                capture_output=True, text=True, errors="replace", timeout=5,
            )
            for pid in killed_pids:
                if str(pid) in result.stdout:
                    logger.info("Chrome (PID %d) still alive, retrying kill", pid)
                    await asyncio.to_thread(
                        subprocess.run, ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=10,
                    )
                    await asyncio.sleep(2.0)
                    break
        except Exception:
            logger.debug("restart_user_chrome: second kill attempt failed", exc_info=True)

    port = 9222
    logger.info("Relaunching %s with --remote-debugging-port=%d", exe, port)
    try:
        _user_chrome_process = await asyncio.create_subprocess_exec(
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            f"--lang={_detect_lang()}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to launch {proc_name}: {e}") from e

    if _user_chrome_process.pid:
        _launched_pids.add(_user_chrome_process.pid)

    async def _log_stderr() -> None:
        try:
            if _user_chrome_process is not None and _user_chrome_process.stderr is not None:
                err = await asyncio.wait_for(
                    _user_chrome_process.stderr.read(), timeout=5.0
                )
                if err:
                    text = err.decode("utf-8", errors="replace")[:1000]
                    logger.warning("Chrome stderr on startup: %s", text)
        except asyncio.TimeoutError:
            logger.debug("stderr read timed out (expected while Chrome is running)")
        except Exception:
            logger.debug("restart_user_chrome: failed to read Chrome stderr", exc_info=True)

    stderr_task = asyncio.create_task(_log_stderr())

    from .discover import _fetch_json

    for i in range(30):
        logger.debug("restart_user_chrome: retry %d/30", i + 1)

        returncode = _user_chrome_process.returncode
        if returncode is not None:
            stderr_task.cancel()
            logger.info(
                "Chrome exited early (code=%d), falling back to isolated",
                returncode,
            )
            if _user_chrome_process.pid:
                _launched_pids.discard(_user_chrome_process.pid)
            _user_chrome_process = None
            return await launch_isolated_chrome()

        data = await _fetch_json(
            f"http://127.0.0.1:{port}/json/version", timeout=2.0
        )
        if data and "webSocketDebuggerUrl" in data:
            logger.info("restart_user_chrome: ready on port %d", port)
            stderr_task.cancel()
            return data["webSocketDebuggerUrl"]
        await asyncio.sleep(0.5)

    stderr_task.cancel()
    if _user_chrome_process is not None:
        try:
            _user_chrome_process.terminate()
        except Exception:
            logger.debug("restart_user_chrome: failed to terminate on timeout", exc_info=True)
        if _user_chrome_process.pid:
            _launched_pids.discard(_user_chrome_process.pid)
        _user_chrome_process = None

    logger.warning("User Chrome restart timed out, falling back to isolated")
    return await launch_isolated_chrome()


async def cleanup_isolated() -> None:
    """Clean up all browser processes started by this module."""
    global _playwright_instance, _playwright_browser, _user_chrome_process, _temp_user_data_dir

    if _user_chrome_process is not None:
        logger.info("Terminating user Chrome process")
        try:
            _user_chrome_process.terminate()
        except Exception:
            logger.debug("cleanup_isolated: failed to terminate Chrome process", exc_info=True)
        _user_chrome_process = None

    if _playwright_browser:
        logger.info("Closing isolated Playwright browser")
        try:
            await _playwright_browser.close()
        except Exception:
            logger.debug("cleanup_isolated: failed to close Playwright browser", exc_info=True)
        _playwright_browser = None

    if _playwright_instance:
        try:
            await _playwright_instance.stop()
        except Exception:
            logger.debug("cleanup_isolated: failed to stop Playwright instance", exc_info=True)
        _playwright_instance = None

    if _temp_user_data_dir:
        temp_path = Path(_temp_user_data_dir)
        if temp_path.exists():
            logger.info("Removing temp user data dir: %s", _temp_user_data_dir)
            shutil.rmtree(temp_path, ignore_errors=True)
        _temp_user_data_dir = None

    _launched_pids.clear()


def get_launched_process() -> Any | None:
    """Return the currently tracked browser subprocess, if any.

    Returns ``None`` when no subprocess was spawned (e.g. connecting to
    an already-running browser) or after the process has been cleaned up.
    """
    return _user_chrome_process
