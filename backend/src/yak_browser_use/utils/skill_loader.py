"""Lightweight skill loader — project-local alternative to Hermes skill_view()."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

SKILL_DIRS = [Path(__file__).resolve().parent.parent / "prompts" / "skill"]

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")


def _validate_skill_name(name: str) -> str | None:
    if not name or not isinstance(name, str):
        return "name is required"
    if not _SKILL_NAME_RE.match(name):
        return (
            f"Invalid skill name: '{name}'. "
            "Skill names must match the pattern: lowercase letters, digits, "
            "and hyphens only (1-64 chars, no leading/trailing hyphens)."
        )
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
        return {"error": f"Skill '{name}' not found"}

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
            if _repaired:
                logger.debug("YAML auto-repair succeeded for %s", path)
            body = raw[m.end():].strip()
    else:
        metadata = {}

    linked_files: list[str] = []
    if isinstance(metadata, dict):
        linked_files = metadata.get("linked_files", [])

    return {
        "metadata": metadata,
        "body": body,
        "linked_files": linked_files,
        "source": str(path),
    }


def skill_list(include_body: bool = False) -> list[dict]:
    """List all available skills across all SKILL_DIRS.

    Scans subdirectory format (``name/SKILL.md``) first, then flat files
    (``name.md``) as fallback.  Subdirectory format takes priority over
    flat files for the same name (no duplicates).

    Skips hidden files/dirs (``.`` prefix) and ``__pycache__``.
    Results are sorted alphabetically by name.

    When *include_body* is True each entry also contains the ``body`` key
    (frontmatter-stripped Markdown), avoiding a second file read + parse
    by the caller.
    """
    seen: set[str] = set()
    result: list[dict] = []

    for base in SKILL_DIRS:
        if not base.exists():
            continue

        for entry in sorted(base.iterdir()):
            entry_name = entry.name

            if entry_name.startswith(".") or entry_name == "__pycache__":
                continue

            if entry.is_dir():
                skill_file = entry / "SKILL.md"
                if not skill_file.exists():
                    continue
                name = entry_name
                parsed = _parse_skill(skill_file)
            elif entry.is_file() and entry.suffix == ".md":
                name = entry.stem
                parsed = _parse_skill(entry)
            else:
                continue

            if name in seen:
                continue
            seen.add(name)

            metadata = parsed.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            entry_data: dict = {
                "name": name,
                "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []),
            }
            if include_body:
                entry_data["body"] = parsed.get("body", "")

            result.append(entry_data)

    result.sort(key=lambda s: s["name"])
    return result


def _build_skill_content(name: str, description: str, content: str, tags: list[str] | None = None) -> str:
    """Assemble a complete skill file from parameters.

    Frontmatter is generated via ``yaml.dump`` with consistent formatting.
    """
    fm: dict = {"name": name, "description": description}
    if tags:
        fm["tags"] = tags

    dumped = yaml.dump(
        fm,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()

    return f"---\n{dumped}\n---\n\n{content}"


def skill_create(name: str, description: str, content: str, tags: list[str] | None = None) -> dict:
    """Create a new skill in subdirectory format.

    Frontmatter is generated from parameters — the caller does not need
    to write YAML.
    """
    err = _validate_skill_name(name)
    if err:
        return {"ok": False, "error": err}

    if not description or not isinstance(description, str):
        return {"ok": False, "error": "description is required"}

    if not content or not isinstance(content, str) or not content.strip():
        return {"ok": False, "error": "content is required"}

    if _normalize_skill_path(name) is not None:
        return {"ok": False, "error": f"Skill '{name}' already exists"}

    if tags is not None:
        if not isinstance(tags, list):
            return {"ok": False, "error": "tags must be a list"}
        for t in tags:
            if not isinstance(t, str) or not t.strip():
                return {"ok": False, "error": "tags cannot be empty"}
        tags = list(dict.fromkeys(tags))
        tags = [t for t in tags if t != "system"]

    base = SKILL_DIRS[0]
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=False)

    full = _build_skill_content(name, description, content, tags)
    (skill_dir / "SKILL.md").write_text(full, encoding="utf-8")

    logger.info("Created skill '%s' at %s", name, skill_dir)
    return {"ok": True, "result": f"Skill '{name}' created successfully"}


def skill_edit(name: str, content: str, raw: bool = False) -> dict:
    """Edit an existing skill's body (default) or replace the entire file (raw=True).

    In non-raw mode the original frontmatter is preserved and only the body
    is replaced.  Flat-file skills are automatically migrated to subdirectory
    format on edit.
    """
    err = _validate_skill_name(name)
    if err:
        return {"ok": False, "error": err}

    if not content or not isinstance(content, str) or not content.strip():
        return {"ok": False, "error": "content is required"}

    path = _normalize_skill_path(name)
    if path is None:
        return {"ok": False, "error": f"Skill '{name}' not found"}

    original_parsed = _parse_skill(path)
    original_metadata = original_parsed.get("metadata", {})
    if not isinstance(original_metadata, dict):
        original_metadata = {}
    has_system = "system" in (original_metadata.get("tags") or [])

    if raw:
        m = _FRONTMATTER_RE.match(content)
        if not m:
            return {"ok": False, "error": "content must contain valid YAML frontmatter with 'name' and 'description' fields"}
        fm_text = m.group(1)
        new_meta, _repaired = _try_parse_yaml(fm_text)
        if new_meta is None or not isinstance(new_meta, dict):
            return {"ok": False, "error": "content must contain valid YAML frontmatter with 'name' and 'description' fields"}
        if "name" not in new_meta or "description" not in new_meta:
            return {"ok": False, "error": "content must contain valid YAML frontmatter with 'name' and 'description' fields"}
        if has_system and "system" not in (new_meta.get("tags") or []):
            return {"ok": False, "error": "cannot remove 'system' tag from pre-installed skill"}
        path.write_text(content, encoding="utf-8")
        logger.info("Raw-edited skill '%s' at %s", name, path)
        return {"ok": True, "result": f"Skill '{name}' updated successfully"}

    migrated = False
    is_flat = path.parent.name != name

    if is_flat:
        base = SKILL_DIRS[0]
        skill_dir = base / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        new_path = skill_dir / "SKILL.md"
        migrated = True
    else:
        new_path = path

    raw_text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(raw_text)
    if m:
        fm_block = raw_text[:m.end()]
    else:
        fm_block = None

    body_content = content
    cm = _FRONTMATTER_RE.match(content)
    if cm:
        body_content = content[cm.end():].strip()

    if fm_block is not None:
        new_full = fm_block.rstrip() + "\n\n" + body_content + "\n"
    else:
        new_full = body_content.rstrip() + "\n"
    new_path.write_text(new_full, encoding="utf-8")

    if migrated:
        path.unlink()
        logger.info("Edited skill '%s' (migrated from flat file)", name)
        return {"ok": True, "result": f"Skill '{name}' updated successfully (migrated from flat file format)"}

    logger.info("Edited skill '%s' at %s", name, new_path)
    return {"ok": True, "result": f"Skill '{name}' updated successfully"}


def skill_delete(name: str, absorbed_into: str | None = None) -> dict:
    """Delete a skill.  Skills with the ``system`` tag are protected.

    If *absorbed_into* is provided the return message records the merge
    target but does NOT automatically merge content.
    """
    err = _validate_skill_name(name)
    if err:
        return {"ok": False, "error": err}

    path = _normalize_skill_path(name)
    if path is None:
        return {"ok": False, "error": f"Skill '{name}' not found"}

    parsed = _parse_skill(path)
    metadata = parsed.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    if "system" in (metadata.get("tags") or []):
        return {"ok": False, "error": f"Cannot delete pre-installed skill '{name}' (protected by 'system' tag)"}

    is_subdir = path.parent.name == name
    base = SKILL_DIRS[0]

    if is_subdir:
        shutil.rmtree(path.parent)
        flat = base / f"{name}.md"
        if flat.exists():
            flat.unlink()
    else:
        path.unlink()

    if absorbed_into:
        msg = (
            f"Skill '{name}' deleted, absorbed into '{absorbed_into}'. "
            "Note: content was NOT automatically merged — "
            f"please use skill_edit on '{absorbed_into}' to incorporate any relevant content."
        )
    else:
        msg = f"Skill '{name}' deleted successfully"

    logger.info("Deleted skill '%s'%s", name, f" (absorbed into '{absorbed_into}')" if absorbed_into else "")
    return {"ok": True, "result": msg}
