"""Simple session tracking for CDP daemon connections.

Stores (name → ws_url) mappings in a module-level dict.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Session:
    """Lightweight session record for a CDP daemon connection."""

    name: str
    ws_url: str = ""
    session_id: str = ""
    target_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


# Module-level session store — no SessionManager class needed.
_sessions: dict[str, Session] = {}


def get_session(name: str) -> Session | None:
    """Look up a session by name."""
    return _sessions.get(name)


def set_session(name: str, ws_url: str = "", **kwargs: str) -> Session:
    """Create or update a session record.

    Keyword arguments (**kwargs**) may include *session_id*, *target_id*.
    """
    existing = _sessions.get(name)
    if existing:
        existing.ws_url = ws_url or existing.ws_url
        existing.session_id = kwargs.get("session_id", existing.session_id)
        existing.target_id = kwargs.get("target_id", existing.target_id)
        existing.last_active = time.time()
        return existing
    session = Session(
        name=name,
        ws_url=ws_url,
        session_id=kwargs.get("session_id", ""),
        target_id=kwargs.get("target_id", ""),
    )
    _sessions[name] = session
    return session


def list_sessions() -> list[Session]:
    """Return all tracked sessions."""
    return list(_sessions.values())


def remove_session(name: str) -> None:
    """Remove a session by name."""
    _sessions.pop(name, None)


def touch_session(name: str) -> None:
    """Update last_active timestamp."""
    session = _sessions.get(name)
    if session:
        session.last_active = time.time()
