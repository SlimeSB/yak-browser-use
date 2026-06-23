"""Simple session tracking for CDP daemon connections.

Stores (name → ws_url) mappings in a module-level dict with LRU eviction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

_MAX_SESSIONS = 100


@dataclass
class Session:
    """Lightweight session record for a CDP daemon connection."""

    name: str
    ws_url: str = ""
    session_id: str = ""
    target_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


# Module-level session store
_sessions: dict[str, Session] = {}


def _evict_lru() -> None:
    """Evict the least recently used session when over limit."""
    if len(_sessions) <= _MAX_SESSIONS:
        return
    oldest = min(_sessions.keys(), key=lambda k: _sessions[k].last_active)
    del _sessions[oldest]


def get_session(name: str) -> Session | None:
    """Look up a session by name."""
    return _sessions.get(name)


def set_session(name: str, ws_url: str = "", *,
                session_id: str = "", target_id: str = "") -> Session:
    """Create or update a session record.

    Args:
        name: Session name.
        ws_url: WebSocket URL.
        session_id: CDP session ID.
        target_id: CDP target ID.
    """
    existing = _sessions.get(name)
    if existing:
        existing.ws_url = ws_url or existing.ws_url
        existing.session_id = session_id or existing.session_id
        existing.target_id = target_id or existing.target_id
        existing.last_active = time.time()
        return existing
    session = Session(
        name=name,
        ws_url=ws_url,
        session_id=session_id,
        target_id=target_id,
    )
    _sessions[name] = session
    _evict_lru()
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
