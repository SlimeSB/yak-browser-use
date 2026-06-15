"""todo tool — Agent-facing function for task list management.

Called by _execute_single_tool_call with a TodoStore instance injected
via ContextVar. Not registered as a BaseTool — it's a harness-level tool.
"""

from __future__ import annotations

import json

from tools.todo_store import TodoStore
from utils.logging import get_logger

logger = get_logger(__name__)


async def todo(
    todos: list | None = None,
    merge: bool = False,
    store: TodoStore | None = None,
) -> str:
    """Read or write the current session's task list.

    Args:
        todos: Optional list of task dicts to write. If None, read-only.
        merge: If True, merge by id instead of replacing the whole list.
        store: The TodoStore instance for this session.

    Returns:
        JSON string of the current task list.
    """
    if store is None:
        return json.dumps([], ensure_ascii=False)

    if todos is not None:
        store.write(todos, merge=merge)

    items = store.read()
    return json.dumps(items, ensure_ascii=False)
