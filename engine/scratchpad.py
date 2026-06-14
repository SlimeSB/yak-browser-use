"""Scratchpad — in-memory cache for heavy browser data (HTML, elements, etc.)

Keeps large data out of LLM message context. Data is stored per-session
and lives only in memory for the lifetime of the process.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ScratchpadRecord:
    """Cached snapshot data for a single browser session."""

    url: str = ""
    title: str = ""
    elements: list[dict] = field(default_factory=list)
    element_map: dict[str, str] = field(default_factory=dict)
    raw_html: str = ""
    summary: str = ""


_scratchpads: dict[str, ScratchpadRecord] = {}


def get(session_id: str = "default") -> ScratchpadRecord:
    """Get (or auto-create) the scratchpad record for a session."""
    if session_id not in _scratchpads:
        _scratchpads[session_id] = ScratchpadRecord()
    return _scratchpads[session_id]


def clear(session_id: str = "default") -> None:
    """Remove a session's scratchpad data to free memory."""
    _scratchpads.pop(session_id, None)
    logger.debug("scratchpad[%s]: cleared", session_id)


def clear_all() -> None:
    """Remove all scratchpad data."""
    count = len(_scratchpads)
    _scratchpads.clear()
    logger.debug("scratchpad: cleared all (%d sessions)", count)


def store(snapshot_dict: dict, session_id: str = "default") -> None:
    """Store snapshot data into the scratchpad record.

    Extracts url, title, elements from the dict. Builds element_map from
    elements (ref → selector). Generates a human-readable summary.
    Call this after browser_snapshot returns.
    """
    record = get(session_id)

    record.url = snapshot_dict.get("url", "")
    record.title = snapshot_dict.get("title", "")
    record.elements = snapshot_dict.get("elements", [])
    record.element_map = _build_element_map(record.elements)
    record.summary = _build_summary(record)

    logger.debug(
        "scratchpad[%s]: stored %d elements, title=%s",
        session_id,
        len(record.elements),
        record.title[:40] if record.title else "(none)",
    )


def store_raw_html(html: str, session_id: str = "default") -> None:
    """Update only raw_html without touching other fields.

    Used by browser_source to cache HTML after a snapshot already exists.
    """
    record = get(session_id)
    record.raw_html = html
    logger.debug("scratchpad[%s]: stored raw_html (%d chars)", session_id, len(html))


def sync_element_map(elements: list[dict], session_id: str = "default") -> None:
    """Sync element_map from external elements list (e.g. from add_dom_highlights).

    Does not overwrite url, title, raw_html or other fields.
    """
    record = get(session_id)
    record.element_map = _build_element_map(elements)
    logger.debug(
        "scratchpad[%s]: synced element_map (%d entries)",
        session_id,
        len(record.element_map),
    )


def _build_element_map(elements: list[dict]) -> dict[str, str]:
    """Build {ref: selector} map from elements list."""
    element_map: dict[str, str] = {}
    for el in elements:
        ref = el.get("ref", "")
        selector = el.get("selector", "")
        if ref and selector:
            element_map[ref] = selector
    return element_map


def _build_summary(record: ScratchpadRecord) -> str:
    """Generate a one-line human-readable summary."""
    parts: list[str] = []

    if record.title:
        parts.append(f"页面标题: {record.title}")

    el_count = len(record.elements)
    if el_count > 0:
        parts.append(f"{el_count}个可交互元素")

    if not parts:
        return "页面快照已获取"

    return " | ".join(parts)
