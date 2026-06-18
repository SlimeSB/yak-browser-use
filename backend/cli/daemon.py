"""Daemon lifecycle CLI commands (process-internal mode)."""

from __future__ import annotations

import sys

from utils.logging import get_logger

logger = get_logger(__name__)


async def _cmd_daemon_start() -> None:
    """Start the Chrome daemon."""
    from api.state import engine_state

    if engine_state.current_state != "idle":
        print(f"  Daemon current state: {engine_state.current_state}")
        print("  To reconnect, run 'daemon stop' first")
        return

    try:
        ws_url = await engine_state.connect_chrome()
        print("  \u2713 Chrome daemon connected")
        print(f"    CDP URL: {ws_url[:80]}")
    except Exception as e:
        print(f"  \u2717 Failed: {e}")
        sys.exit(1)


async def _cmd_daemon_stop() -> None:
    """Stop the Chrome daemon."""
    from api.state import engine_state

    try:
        await engine_state.disconnect_chrome()
        print("  \u2713 Chrome daemon disconnected")
    except RuntimeError as e:
        print(f"  ! Cannot disconnect: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"  \u2717 Failed: {e}")
        sys.exit(1)


async def _cmd_daemon_status() -> None:
    """Show daemon status."""
    from api.state import engine_state

    connected = engine_state.chrome_connected
    print("  Daemon Status")
    print(f"    Connected:       {'yes' if connected else 'no'}")
    print(f"    State:           {engine_state.current_state}")
    if connected and engine_state.bridge:
        print(f"    CDP URL:         {engine_state.bridge._cdp_url[:80]}")
    if engine_state._running_pipeline:
        rp = engine_state._running_pipeline
        print(f"    Active Pipeline: {getattr(rp, 'run_id', '?')} ({getattr(rp, 'pipeline_name', '?')})")
    else:
        print("    Active Pipeline: none")


async def dispatch(cmd: str) -> None:
    """Dispatch a daemon subcommand.

    Args:
        cmd: Subcommand name (start, stop, status).
    """
    handlers = {
        "start": _cmd_daemon_start,
        "stop": _cmd_daemon_stop,
        "status": _cmd_daemon_status,
    }
    handler = handlers.get(cmd)
    if handler is None:
        logger.error("Unknown daemon subcommand: %s (available: start, stop, status)", cmd)
        sys.exit(1)
    await handler()
