"""Tool registration — OpenAI-compatible tool definitions via ToolRegistry.

All tool schemas are now defined in ``tools.registry.build_registry()``.
These functions delegate to the registry for production use.
"""

from __future__ import annotations

from typing import Any

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


def get_all_tools(include_goal_run: bool = True) -> list[dict[str, Any]]:
    """Get the full list of registered tools.

    Args:
        include_goal_run: If True, include the goal_run tool.

    Returns:
        List of OpenAI-compatible tool definitions.
    """
    from yak_browser_use.tools.registry import registry, build_registry

    if not registry._tools:
        build_registry()

    tools = registry.get_schemas()
    if not include_goal_run:
        tools = [t for t in tools if t["function"]["name"] != "goal_run"]
    logger.debug("get_all_tools: registered %d tools (include_goal_run=%s)", len(tools), include_goal_run)
    return tools


def get_browser_tools() -> list[dict[str, Any]]:
    """Get only browser atomics (no goal_run)."""
    from yak_browser_use.tools.registry import registry, build_registry

    if not registry._tools:
        build_registry()

    tools = [t for t in registry.get_schemas() if t["function"]["name"].startswith("browser_")]
    logger.debug("get_browser_tools: registered %d tools", len(tools))
    return tools
