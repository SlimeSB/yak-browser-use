"""TodoStore — per-session task list with CRUD, merge, dedup, and cap.

Each chat session owns one TodoStore instance. The store is passed to
the `todo()` tool via a ContextVar set in `api/service.py`.
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

MAX_ITEMS = 256
MAX_CONTENT_CHARS = 4000
VALID_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled"})

current_store: contextvars.ContextVar = contextvars.ContextVar("todo_store", default=None)


@dataclass
class TodoStore:
    """In-memory task list for a single chat session."""

    _items: list[dict] = field(default_factory=list)

    def read(self) -> list[dict]:
        return list(self._items)

    def write(self, todos: object, merge: object = False) -> list[dict]:
        if not isinstance(todos, list):
            return self.read()

        if not isinstance(merge, bool):
            merge = False

        logger.debug("TodoStore write: %d items, merge=%s", len(todos), merge)
        if merge:
            self._merge(todos)
        else:
            self._replace(todos)

        self._cap()
        return self.read()

    def clear(self) -> None:
        self._items.clear()

    def _replace(self, todos: list) -> None:
        self._items = [self._normalize(item) for item in todos]

    def _merge(self, todos: list) -> None:
        index = {item.get("id"): i for i, item in enumerate(self._items)}
        for incoming in todos:
            if not isinstance(incoming, dict):
                continue
            normalized = self._normalize(incoming)
            item_id = normalized["id"]
            if item_id in index:
                existing = self._items[index[item_id]]
                if "content" in incoming:
                    existing["content"] = normalized["content"]
                if "status" in incoming and isinstance(incoming.get("status"), str) and incoming["status"] in VALID_STATUSES:
                    existing["status"] = normalized["status"]
            else:
                self._items.append(normalized)
                index[item_id] = len(self._items) - 1

    def _normalize(self, item: dict) -> dict:
        if not isinstance(item, dict):
            item = {}

        item_id = item.get("id")
        if not item_id or not isinstance(item_id, str):
            item_id = uuid.uuid4().hex[:8]

        content = item.get("content")
        if not content or not isinstance(content, str):
            content = "(no description)"

        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS - 20] + "\u2026 [truncated]"

        status = item.get("status", "pending")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            status = "pending"

        return {"id": item_id, "content": content, "status": status}

    def _cap(self) -> None:
        if len(self._items) > MAX_ITEMS:
            dropped = len(self._items) - MAX_ITEMS
            self._items = self._items[:MAX_ITEMS]
            logger.warning("TodoStore: capped at %d items, dropped %d", MAX_ITEMS, dropped)
