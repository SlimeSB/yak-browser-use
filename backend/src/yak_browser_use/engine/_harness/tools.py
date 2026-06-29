"""Tool registration — OpenAI-compatible tool definitions via ToolRegistry.

All tool schemas are now defined in ``tools.registry.build_registry()``.
These functions delegate to the registry for production use.
"""

from __future__ import annotations

from typing import Any

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


def get_all_tools() -> list[dict[str, Any]]:
    """Get the full list of registered tools.

    Returns:
        List of OpenAI-compatible tool definitions.
    """
    from yak_browser_use.tools.registry import registry, build_registry

    if not registry._tools:
        build_registry()

    tools = registry.get_schemas()
    logger.debug("get_all_tools: registered %d tools", len(tools))
    return tools
