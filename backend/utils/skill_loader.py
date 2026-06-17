"""Lightweight skill loader — project-local alternative to Hermes skill_view()."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from utils.logging import get_logger

logger = get_logger(__name__)

SKILL_DIRS = [Path(__file__).resolve().parent.parent / "prompts" / "skill"]

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")


def _validate_skill_name(name: str) -> str | None:
    if not name or not isinstance(name, str):
        return "name is required"
    if not _SKILL_NAME_RE.match(name):
        return f"Invalid skill name: '{name}'"
    return None


def _normalize_skill_path(name: str) -> Path | None:
    for base in SKILL_DIRS:
        subdir = base / name / "SKILL.md"
        if subdir.exists():
            return subdir
        flat = base / f"{name}.md"
        if flat.exists():
            return flat
    return None


def skill_view(name: str) -> dict:
    """Load a skill document by name from the skill directories.

    Searches ``prompts/skill/{name}/SKILL.md`` (subdirectory format) first,
    then ``prompts/skill/{name}.md`` (flat file) as fallback.
    Parses YAML frontmatter (between ``---`` fences)
    and returns the metadata, body, and linked-files list.

    Returns:
        Dict with keys ``metadata`` (dict), ``body`` (str),
        ``linked_files`` (list[str]), and ``source`` (Path).
        If the skill file is not found, returns ``{"error": "..."}``.
    """
    err = _validate_skill_name(name)
    if err:
        return {"error": err}

    path = _normalize_skill_path(name)
    if path is None:
        logger.warning("Skill '%s' not found in %s", name, [str(d) for d in SKILL_DIRS])
        return {"error": f"Skill '{name}' not found in {[str(d) for d in SKILL_DIRS]}"}

    logger.info("Loaded skill '%s' from %s", name, path)
    return _parse_skill(path)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _try_parse_yaml(text: str) -> tuple[dict | None, bool]:
    """Parse a YAML string with automatic repair for common formatting errors.

    Returns (parsed_dict, was_repaired).  ``was_repaired`` is True when the
    original text failed to parse but automatic repair succeeded.
    """
    if not text or not text.strip():
        return None, False

    try:
        result = yaml.safe_load(text)
        if isinstance(result, dict):
            return result, False
        return None, False
    except yaml.YAMLError:
        pass

    repaired = _repair_yaml(text)
    if repaired is None:
        return None, False

    try:
        result = yaml.safe_load(repaired)
        if isinstance(result, dict):
            logger.debug("YAML auto-repair succeeded")
            return result, True
    except yaml.YAMLError:
        pass

    return None, False


def _repair_yaml(text: str) -> str | None:
    """Attempt to repair common YAML formatting errors produced by LLMs.

    Handles: tab→spaces, invisible control chars.
    Note: this only runs after yaml.safe_load raises YAMLError, so it targets
    syntax errors (not semantic issues like unquoted colons that parse as
    nested mappings).
    """
    changed = False
    repaired_lines: list[str] = []

    for line in text.split("\n"):
        original = line
        line = line.replace("\t", "    ")
        line = line.rstrip("\x00\x01\x02\x03\x04\x05\x06\x07\x08"
                           "\x0b\x0c\x0e\x0f\x10\x11\x12\x13\x14\x15"
                           "\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f")
        if line != original:
            changed = True
        repaired_lines.append(line)

    if not changed:
        return None

    return "\n".join(repaired_lines)


def _parse_skill(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")

    metadata: dict = {}
    body = raw

    m = _FRONTMATTER_RE.match(raw)
    if m:
        fm_text = m.group(1)
        metadata, _repaired = _try_parse_yaml(fm_text)
        if metadata is None:
            logger.warning("Skill %s has invalid YAML frontmatter, treating as plain body", path)
            metadata = {}
            body = raw
        else:
            body = raw[m.end():].strip()
    else:
        metadata = {}

    linked_files: list[str] = []
    if isinstance(metadata, dict):
        linked_files = metadata.pop("linked_files", [])

    return {
        "metadata": metadata,
        "body": body,
        "linked_files": linked_files,
        "source": str(path),
    }
