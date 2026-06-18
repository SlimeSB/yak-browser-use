"""Chat mode runner — lightweight entry point for conversation_loop.

Handles browser lifecycle management (connect, navigate, disconnect)
and launches the conversation_loop for interactive chat sessions.

For preset replay mode, see runner_preset.py.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Callable

from utils.logging import get_logger

# Re-export preset runner functions for backward compatibility
from engine.runner_preset import (  # noqa: F401
    run_pipeline,
    _step_type,
    _collect_input_files,
)

logger = get_logger(__name__)


async def run_chat_loop(
    *,
    llm_call: Callable,
    messages: list[dict] | None = None,
    cdp_helpers: object | None = None,
    tools_dir: Path | None = None,
    pipeline_name: str = "chat",
    system_prompt: str = "",
) -> dict:
    """Launch the conversation_loop for chat mode.

    This is a thin wrapper that ensures browser connectivity and
    then delegates to conversation_loop.run_conversation_loop().

    Args:
        llm_call: Async callable(messages, tools) -> LLMResponse.
        messages: Initial conversation messages.
        cdp_helpers: CDPHelpers instance (will auto-connect if None).
        tools_dir: Directory for tool modules.
        pipeline_name: Pipeline name for workspace context.
        system_prompt: System prompt text (loaded from prompts/ if empty).

    Returns:
        Dict with final_response, status, messages, budget, stats.
    """
    from engine._harness.conversation_loop import run_conversation_loop
    from engine._harness.tools import get_all_tools
    from prompts._loader import build_system_prompt

    if messages is None:
        messages = []

    if not system_prompt:
        system_prompt = build_system_prompt()

    if cdp_helpers is None:
        cdp_helpers = await _ensure_browser_connected()

    if tools_dir is None:
        tools_dir = Path("tools")

    result = await run_conversation_loop(
        llm_call=llm_call,
        system_prompt=system_prompt,
        messages=messages,
        tools=get_all_tools(),
        cdp_helpers=cdp_helpers,
        tools_dir=tools_dir,
        pipeline_name=pipeline_name,
    )

    return {
        "response": result.final_response,
        "status": "completed" if not result.interrupted else "cancelled",
        "messages": result.messages,
        "budget": result.budget.to_dict(),
        "turn_count": result.turn_count,
        "duration_ms": result.duration_ms,
    }


async def _ensure_browser_connected() -> object:
    """Connect to Chrome browser via PlaywrightBridge.

    Returns a CDPHelpers instance for browser operations.
    """
    from cdp.playwright_bridge import PlaywrightBridge
    from cdp.helpers import CDPHelpers
    from cdp.discover import discover_ws_url

    try:
        ws_url = await discover_ws_url()
        if ws_url is None:
            raise RuntimeError("Cannot discover Chrome debug URL")
        cdp_url = re.sub(r'^ws', 'http', ws_url)
        bridge = PlaywrightBridge(cdp_url)
        await bridge.start()
        helpers = CDPHelpers(bridge)
        logger.info("Browser connected for chat mode")
        try:
            await helpers.add_dom_highlights()
        except Exception:
            logger.warning("initial highlight injection failed", exc_info=True)
        return helpers
    except Exception as e:
        logger.error("Failed to connect browser: %s", e)
        raise
