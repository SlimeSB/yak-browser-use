"""Lightweight skill loader — project-local alternative to Hermes skill_view()."""

from __future__ import annotations

from pathlib import Path

import yaml

SKILL_DIRS = [Path("prompts/skill")]


def skill_view(name: str) -> dict:
    """Load a skill document by name from the skill directories.

    Searches ``prompts/skill/{name}.md`` (and any extra dirs added to
    ``SKILL_DIRS``).  Parses YAML frontmatter (between ``---`` fences)
    and returns the metadata, body, and linked-files list.

    Returns:
        Dict with keys ``metadata`` (dict), ``body`` (str),
        ``linked_files`` (list[str]), and ``source`` (Path).
        If the skill file is not found, returns ``{"error": "..."}``.
    """
    for base in SKILL_DIRS:
        path = base / f"{name}.md"
        if path.exists():
            return _parse_skill(path)
    return {"error": f"Skill '{name}' not found in {[str(d) for d in SKILL_DIRS]}"}


def _parse_skill(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")

    metadata: dict = {}
    body = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            metadata = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()

    linked_files: list[str] = []
    if isinstance(metadata, dict):
        linked_files = metadata.pop("linked_files", [])

    return {
        "metadata": metadata,
        "body": body,
        "linked_files": linked_files,
        "source": str(path),
    }
