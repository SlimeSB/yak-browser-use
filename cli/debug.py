"""Debug commands: chrome, events, checkpoints, state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


async def _cmd_debug(cmd: str, **kwargs) -> None:
    """Dispatch debug commands.

    Args:
        cmd: Debug subcommand (chrome, events, checkpoints, state).
        **kwargs: Additional keyword arguments specific to the subcommand.
    """
    if cmd == "chrome":
        await _debug_chrome()
    elif cmd == "events":
        await _debug_events(tail=kwargs.get("tail", False))
    elif cmd == "checkpoints":
        await _debug_checkpoints(last=kwargs.get("last", False))
    elif cmd == "state":
        _debug_state(kwargs.get("path", ""))


async def _debug_chrome() -> None:
    """Diagnose Chrome connectivity at all levels."""
    logger.info("=== Chrome Connection Diagnostics ===\n")

    try:
        from cdp import discover_ws_url
        ws_url = await discover_ws_url()
        if ws_url:
            logger.info("\u2713 Chrome WebSocket URL: %s...", ws_url[:80])
        else:
            logger.warning("\u2717 No connectable Chrome instance found")
            logger.info("  Please ensure Chrome is running with one of:")
            logger.info("  1. chrome.exe --remote-debugging-port=9222")
            logger.info("  2. Set LBU_CDP_URL environment variable")
            logger.info("  3. Set LBU_WSS_URL environment variable")
    except Exception as e:
        logger.warning("\u2717 Chrome discovery failed: %s", e)


async def _debug_events(tail: bool = False) -> None:
    """Monitor EventSink events."""
    logger.info("EventSink monitoring removed in new architecture (each run creates its own EventSink)")
    logger.info("See: <workspace>/<run_id>/_events.jsonl")


async def _debug_checkpoints(last: bool = False) -> None:
    """View checkpoint history."""
    from engine.checkpoint import MemorySaver

    if not last:
        logger.info("Usage: lbu debug checkpoints --last")
        logger.info("View the latest checkpoint")
        return

    saver = MemorySaver()
    threads = list(saver._storage.keys())

    if not threads:
        logger.info("No checkpoint records")
        return

    for thread_id in threads[-3:]:
        entries = saver.list_checkpoints(thread_id)
        latest = entries[-1] if entries else None
        if latest:
            logger.info("\nThread: %s", thread_id)
            logger.info("  Step:  %s", latest.get('step_index'))
            logger.info("  Time:  %s", latest.get('timestamp'))
            state_data = latest.get("state", {}).get("data", {})
            summary = {k: str(v)[:80] for k, v in state_data.items()}
            logger.info("  Data:  %s", json.dumps(summary, ensure_ascii=False))


def _debug_state(path: str) -> None:
    """Pretty-print a state.json file.

    Args:
        path: Path to state.json.
    """
    state_path = Path(path)
    if not state_path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        logger.info(json.dumps(data, ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        logger.error("JSON decode error: %s", e)
        sys.exit(1)
