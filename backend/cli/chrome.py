"""Chrome debugging and browser operation CLI commands."""

from __future__ import annotations

import sys

from utils.logging import get_logger

logger = get_logger(__name__)


# ── Helper: pretty-print helpers ────────────────────────────────────────────────

def _pf(k: str, v: object, indent: int = 22) -> str:
    """Pad field name and value for aligned output."""
    return f"  {k + ':':<{indent}}{v}"


def _yes(val: object) -> str:
    return f"\033[32m{val}\033[0m" if sys.stdout.isatty() else str(val)


def _no(val: object) -> str:
    return f"\033[31m{val}\033[0m" if sys.stdout.isatty() else str(val)


def _warn(val: object) -> str:
    return f"\033[33m{val}\033[0m" if sys.stdout.isatty() else str(val)


def _bold(val: object) -> str:
    return f"\033[1m{val}\033[0m" if sys.stdout.isatty() else str(val)


def _dim(val: object) -> str:
    return f"\033[2m{val}\033[0m" if sys.stdout.isatty() else str(val)


def _emoji_ok(mark: str = "\u2713") -> str:
    return f"\033[32m{mark}\033[0m" if sys.stdout.isatty() else mark


def _emoji_fail(mark: str = "\u2717") -> str:
    return f"\033[31m{mark}\033[0m" if sys.stdout.isatty() else mark


# ── Command implementations ─────────────────────────────────────────────────────

async def _cmd_chrome_status() -> None:
    """Snapshot: process, ports, env vars, DevToolsActivePort."""
    from cdp.launcher import _find_chrome_exe, _fetch_browser_info

    print(_bold("\n\u2550\u2550\u2550 Chrome Status Snapshot \u2550\u2550\u2550\n"))

    # Browser info
    print(_bold("\u25a0 Browser"))
    exe_path = _find_chrome_exe()
    print(_pf("Executable", exe_path or _no("not found")))

    # Environment variables
    import os
    print(_bold("\n\u25a0 Environment Variables"))
    for var in ("YBU_CDP_URL", "YBU_WSS_URL"):
        val = os.getenv(var)
        print(_pf(var, val if val else _dim("(not set)")))

    # Process
    print(_bold("\n\u25a0 Process"))
    try:
        from cdp.discover import is_chrome_running
        running, count = await is_chrome_running()
        print(_pf("Running", _yes("yes") if running else _no("no")))
        print(_pf("Count", count))
    except Exception as e:
        print(_pf("Status", _no(f"check failed: {e}")))

    # Connection
    print(_bold("\n\u25a0 Connection"))
    try:
        from cdp import discover_ws_url
        ws_url = await discover_ws_url()
        if ws_url:
            print(_pf("WebSocket URL", ws_url[:80]))
            bi = await _fetch_browser_info(ws_url)
            if bi.get("browser"):
                print(_pf("Browser version", bi["browser"]))
            if bi.get("protocol_version"):
                print(_pf("CDP protocol", bi["protocol_version"]))
            print()
            print(f"  {_emoji_ok()} {_yes('Connectable')}")
        else:
            print()
            print(f"  {_emoji_fail()} {_no('No connectable Chrome instance found')}")
    except Exception as e:
        print(f"  {_emoji_fail()} {_no(f'Discovery failed: {e}')}")


async def _cmd_chrome_inspect() -> None:
    """Deep diagnostics — test each discovery level step by step."""
    from cdp.discover import _check_port
    from cdp.launcher import _find_chrome_exe, _fetch_browser_info

    print(_bold("\n\u2550\u2550\u2550 Chrome Deep Diagnostics \u2550\u2550\u2550\n"))

    # Step 0: Executable
    print(_bold("[0/5] Executable"))
    exe = _find_chrome_exe()
    if exe:
        print(f"  {_emoji_ok()} {exe}")
    else:
        print(f"  {_emoji_fail()} No Chrome/Edge/Brave executable found")
        print(f"    {_warn('Diagnostics stopped: no browser executable')}")
        return

    # Step 1: Quick win via env vars
    import os
    print(_bold("\n[1/5] Environment Variables (fast path)"))
    cdp = os.getenv("YBU_CDP_URL")
    wss = os.getenv("YBU_WSS_URL")

    if cdp:
        from cdp.discover import _ws_from_cdp_url
        ws = await _ws_from_cdp_url(cdp)
        if ws:
            print(f"  {_emoji_ok()} YBU_CDP_URL → available: {ws[:60]}...")
            bi = await _fetch_browser_info(ws)
            if bi.get("browser"):
                print(f"    {_dim('Browser:')} {bi['browser']}")
            return
        else:
            print(f"  {_emoji_fail()} YBU_CDP_URL set but unreachable: {cdp}")

    if wss:
        print(f"  {_emoji_ok()} YBU_WSS_URL → {wss[:60]}...")
        bi = await _fetch_browser_info(wss)
        if bi.get("browser"):
            print(f"    {_dim('Browser:')} {bi['browser']}")
        return

    print(f"  {_dim('Not set, continuing to next level')}")

    # Step 2: Process check
    print(_bold("\n[2/5] Chrome Process"))
    try:
        from cdp.discover import is_chrome_running
        running, count = await is_chrome_running()
        if running:
            print(f"  {_emoji_ok()} Chrome is running ({count} processes)")
        else:
            print(f"  {_dim('Chrome not running, will be auto-started when needed')}")
    except Exception as e:
        print(f"  {_emoji_fail()} Process check failed: {e}")

    # Step 3: DevToolsActivePort scan
    from cdp.profiles import list_user_data_dirs
    print(_bold("\n[3/5] DevToolsActivePort File Scan"))
    profiles = list_user_data_dirs()
    ws = None
    for udd in profiles:
        port_file = udd / "DevToolsActivePort"
        if port_file.exists():
            try:
                port_text = port_file.read_text(encoding="utf-8").strip()
                port_num = int(port_text.split("\n")[0].strip())
                ws_url = f"ws://127.0.0.1:{port_num}/devtools/browser/"
                bi = await _fetch_browser_info(ws_url)
                if bi.get("browser"):
                    ws = ws_url
                    print(f"  {_emoji_ok()} Found: {ws[:60]}...")
                    print(f"    {_dim('Browser:')} {bi['browser']}")
                    break
            except (ValueError, Exception):
                continue
    if not ws:
        print(f"  {_dim('Not found')}")

    # Step 4: Port scan
    print(_bold("\n[4/5] Port Scan (9222, 9223)"))
    for port in (9222, 9223):
        ok = await _check_port("127.0.0.1", port)
        if ok:
            from cdp.discover import _ws_from_port_scan
            ws_url = await _ws_from_port_scan()
            if ws_url:
                print(f"  {_emoji_ok()} Port {port} \u2192 WS URL ready: {ws_url[:60]}...")
                bi = await _fetch_browser_info(ws_url)
                if bi.get("browser"):
                    print(f"    {_dim('Browser:')} {bi['browser']}")
                return
            else:
                print(f"  {_emoji_fail()} Port {port} open but WS URL unavailable")
        else:
            print(f"  {_dim(f'Port {port}: unreachable')}")

    # Summary
    print()
    print(f"  {_emoji_fail()} {_no('All discovery levels exhausted: no Chrome debug endpoint found')}")
    print(f"\n  {_warn('Suggestions:')}")
    bullet = chr(0x2022)  # bullet character
    em_dash = chr(0x2014)  # em dash
    print(f"    {_dim(f'{bullet} ybu chrome launch     {em_dash} launch user Chrome (non-destructive)')}")
    print(f"    {_dim(f'{bullet} ybu chrome restart    {em_dash} kill & restart Chrome')}")
    print(f"    {_dim(f'{bullet} ybu chrome isolated   {em_dash} launch isolated Playwright browser')}")


async def _cmd_chrome_connect() -> None:
    """Establish a WebSocket connection (full discovery chain)."""
    from cdp import discover_ws_url
    from cdp.launcher import _fetch_browser_info

    print(_bold("\n\u2550\u2550\u2550 Chrome Connection Attempt \u2550\u2550\u2550\n"))

    try:
        ws_url = await discover_ws_url()
    except Exception as e:
        print(f"  {_emoji_fail()} Connection failed: {_no(str(e))}")
        return

    if ws_url:
        print(f"  {_emoji_ok()} WebSocket URL: {_yes(ws_url[:80])}")
        bi = await _fetch_browser_info(ws_url)
        if bi.get("browser"):
            print(f"    {_dim('Browser:')} {_yes(bi['browser'])}")
        if bi.get("protocol_version"):
            print(f"    {_dim('CDP protocol:')} {bi['protocol_version']}")
        return

    print(f"  {_emoji_fail()} {_no('Cannot discover or launch Chrome')}")


async def _cmd_chrome_launch(profile: str | None = None) -> None:
    """Launch user Chrome (non-destructive)."""
    from cdp.launcher import launch_user_chrome, _fetch_browser_info
    from cdp.profiles import get_active_profile

    effective_profile = profile or get_active_profile()

    print(_bold("\n\u2550\u2550\u2550 Launching User Chrome \u2550\u2550\u2550\n"))
    if effective_profile:
        print(f"  {_dim(f'Profile: {effective_profile}')}")
    print(f"  {_dim('Attempting launch (will not kill existing process)...')}")

    try:
        ws_url = await launch_user_chrome(profile=effective_profile)
    except Exception as e:
        print(f"  {_emoji_fail()} Launch failed: {_no(str(e))}")
        return

    if ws_url:
        print(f"  {_emoji_ok()} Launch successful!")
        print(f"  {_pf('WebSocket URL', ws_url[:80])}")
        bi = await _fetch_browser_info(ws_url)
        if bi.get("browser"):
            print(f"  {_pf('Browser version', bi['browser'])}")
        return

    print(f"  {_emoji_fail()} {_no('Chrome did not start (may already be running without debug port)')}")
    print(f"    {_warn('Tip: try ybu chrome restart to force a restart')}")


async def _cmd_chrome_restart() -> None:
    """Force-kill Chrome and relaunch with remote debugging."""
    from cdp.launcher import restart_user_chrome, _fetch_browser_info

    print(_bold("\n\u2550\u2550\u2550 Force-Restarting Chrome \u2550\u2550\u2550\n"))
    print(f"  {_dim('Killing all Chrome processes and restarting...')}")

    try:
        ws_url = await restart_user_chrome()
    except Exception as e:
        print(f"  {_emoji_fail()} Restart failed: {_no(str(e))}")
        print(f"    {_dim('Please try closing Chrome manually and retry')}")
        return

    if ws_url:
        print(f"  {_emoji_ok()} {_yes('Chrome restarted with debug port open!')}")
        print(f"  {_pf('WebSocket URL', ws_url[:80])}")
        bi = await _fetch_browser_info(ws_url)
        if bi.get("browser"):
            print(f"  {_pf('Browser version', bi['browser'])}")
        return

    print(f"  {_emoji_fail()} {_no('Cannot obtain Chrome WS URL')}")


async def _cmd_chrome_isolated() -> None:
    """Launch isolated Chrome via Playwright."""
    from cdp.launcher import launch_isolated_chrome, _fetch_browser_info

    print(_bold("\n\u2550\u2550\u2550 Launching Isolated Chrome \u2550\u2550\u2550\n"))

    try:
        ws_url = await launch_isolated_chrome()
    except ImportError:
        print(f"  {_emoji_fail()} {_no('Playwright not installed')}")
        print(f"    {_warn('Install with:')}")
        print(f"    {_dim('  uv add playwright && playwright install chromium')}")
        return
    except Exception as e:
        print(f"  {_emoji_fail()} Launch failed: {_no(str(e))}")
        return

    if ws_url:
        print(f"  {_emoji_ok()} {_yes('Isolated Chrome started!')}")
        print(f"  {_pf('WebSocket URL', ws_url[:80])}")
        bi = await _fetch_browser_info(ws_url)
        if bi.get("browser"):
            print(f"  {_pf('Browser version', bi['browser'])}")
        return

    print(f"  {_emoji_fail()} {_no('Isolated Chrome launch failed')}")


# ── CDP helper ──────────────────────────────────────────────────────────────────

async def _with_cdp(fn):
    """Obtain a WS connection, set up a daemon, execute an operation, then disconnect."""
    from cdp import discover_ws_url
    from cdp.daemon import CDPDaemon
    from cdp.helpers import CDPHelpers

    ws_url = await discover_ws_url()
    if not ws_url:
        print("Cannot discover or connect to Chrome")
        sys.exit(1)

    daemon = CDPDaemon(ws_url)
    await daemon.start()
    try:
        await daemon.attach_first_page()
        helpers = CDPHelpers(daemon)
        await fn(helpers)
    finally:
        await daemon.stop()


# ── Browser operation commands ──────────────────────────────────────────────────

async def _cmd_chrome_goto(url: str) -> None:
    async def _(helpers):
        await helpers.goto_url(url)
        print(f"  \u2713 goto {url}")
    await _with_cdp(_)


async def _cmd_chrome_click(selector: str) -> None:
    async def _(helpers):
        await helpers.click_selector(selector)
        print(f"  \u2713 click {selector}")
    await _with_cdp(_)


async def _cmd_chrome_fill(selector: str, text: str) -> None:
    async def _(helpers):
        await helpers.fill_input(selector, text)
        print(f"  \u2713 fill {selector}")
    await _with_cdp(_)


async def _cmd_chrome_scroll(direction: str) -> None:
    async def _(helpers):
        amount = 500 if direction == "down" else -500
        await helpers.js(f"window.scrollBy(0, {amount})")
        print(f"  \u2713 scroll {direction}")
    await _with_cdp(_)


async def _cmd_chrome_back() -> None:
    async def _(helpers):
        await helpers.js("window.history.back()")
        print("  \u2713 back")
    await _with_cdp(_)


async def _cmd_chrome_snapshot(mode: str = "full") -> None:
    import base64
    import json as _json
    import time
    from pathlib import Path

    async def _(helpers):
        if mode == "interactive":
            result = await helpers.capture_snapshot_interactive()
            elements = result.get("elements", [])
            elements_path = Path("interactive_elements.json")
            elements_path.write_text(_json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
            degraded = " (degraded)" if result.get("degraded") else ""
            print(f"  \u2713 interactive snapshot saved: {elements_path.name} ({len(elements)} elements){degraded}")
        elif mode == "simplified":
            result = await helpers.capture_snapshot_simplified()
            summary = result.get("summary", "")
            lists_data = result.get("lists", [])
            tables_data = result.get("tables", [])
            Path("page_summary.txt").write_text(summary, encoding="utf-8")
            Path("detected_lists.json").write_text(_json.dumps(lists_data, ensure_ascii=False, indent=2), encoding="utf-8")
            Path("detected_tables.json").write_text(_json.dumps(tables_data, ensure_ascii=False, indent=2), encoding="utf-8")
            degraded = " (degraded)" if result.get("degraded") else ""
            print(f"  \u2713 simplified snapshot saved: page_summary.txt, detected_lists.json, detected_tables.json{degraded}")
        else:
            result = await helpers.capture_snapshot()
            ts = int(time.time())
            png_path = Path(f"snapshot_{ts}.png")
            html_path = Path(f"snapshot_{ts}.html")
            png_path.write_bytes(base64.b64decode(result["screenshot_base64"]))
            html_path.write_text(result["html"], encoding="utf-8")
            print(f"  \u2713 snapshot saved: {png_path.name}, {html_path.name}")
    await _with_cdp(_)


async def _cmd_chrome_source() -> None:
    async def _(helpers):
        html = await helpers.get_page_html()
        print(html)
    await _with_cdp(_)


async def _cmd_chrome_wait(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
    print(f"  \u2713 waited {seconds}s")


async def _cmd_chrome_eval(js: str) -> None:
    async def _(helpers):
        result = await helpers.js(js)
        if result is not None:
            print(str(result))
        else:
            print("null")
    await _with_cdp(_)


async def _cmd_chrome_tab(tab_cmd: str, targetId: str | None = None, url: str | None = None) -> None:
    if tab_cmd == "list":
        async def _(helpers):
            targets = await helpers._daemon._send("Target.getTargets")
            pages = targets.get("targetInfos", [])
            if not pages:
                print("  No tabs")
                return
            for t in pages:
                tid = t.get("targetId", "?")
                ttype = t.get("type", "?")
                turl = t.get("url", "")[:80]
                print(f"  {tid}  {ttype}  {turl}")
        await _with_cdp(_)
    elif tab_cmd == "switch":
        async def _(helpers):
            await helpers._daemon._send("Target.activateTarget", {"targetId": targetId})
            print(f"  \u2713 switched to {targetId}")
        await _with_cdp(_)
    elif tab_cmd == "close":
        async def _(helpers):
            await helpers._daemon._send("Target.closeTarget", {"targetId": targetId})
            print(f"  \u2713 closed {targetId}")
        await _with_cdp(_)
    elif tab_cmd == "new":
        async def _(helpers):
            result = await helpers._daemon._send("Target.createTarget", {"url": url or "about:blank"})
            tid = result.get("targetId", "")
            print(f"  \u2713 new tab: {tid}")
        await _with_cdp(_)


# ── Chrome Profile Management ───────────────────────────────────────────────────

async def _cmd_chrome_profile(profile_cmd: str, profile_name: str | None = None) -> None:
    from cdp.profiles import list_chrome_profiles, set_active_profile, get_active_profile

    if profile_cmd == "list":
        profiles = list_chrome_profiles()
        if not profiles:
            print("  No Chrome user profiles found")
            return
        print(f"  Chrome user profiles ({len(profiles)}):")
        for p in profiles:
            login_mark = " \U0001f511" if p.get("is_logged_in", False) else ""
            print(f"    {p.get('directory', '?'):<20}  {p.get('display_name', '?')}{login_mark}")

    elif profile_cmd == "use":
        if not profile_name:
            print("  Please specify a profile name")
            return
        set_active_profile(profile_name)
        print(f"  \u2713 Selected profile: {profile_name}")
        active = get_active_profile()
        print(f"  {_dim(f'Next chrome launch will use this profile (current: {active})')}")


# ── Dispatch ────────────────────────────────────────────────────────────────────

async def dispatch(cmd: str, **kwargs) -> None:
    """Dispatch chrome subcommand to handler."""
    handlers = {
        "status": _cmd_chrome_status,
        "inspect": _cmd_chrome_inspect,
        "connect": _cmd_chrome_connect,
        "launch": _cmd_chrome_launch,
        "restart": _cmd_chrome_restart,
        "isolated": _cmd_chrome_isolated,
        "goto": _cmd_chrome_goto,
        "click": _cmd_chrome_click,
        "fill": _cmd_chrome_fill,
        "scroll": _cmd_chrome_scroll,
        "back": _cmd_chrome_back,
        "snapshot": _cmd_chrome_snapshot,
        "source": _cmd_chrome_source,
        "wait": _cmd_chrome_wait,
        "eval": _cmd_chrome_eval,
        "tab": _cmd_chrome_tab,
        "profile": _cmd_chrome_profile,
    }
    handler = handlers.get(cmd)
    if handler is None:
        logger.error("Unknown chrome subcommand: %s (available: %s)", cmd, ", ".join(handlers))
        sys.exit(1)
    await handler(**kwargs)
