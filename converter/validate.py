"""
validate.py — Post-conversion validation for agent.md documents.

Validates that generated agent.md documents are well-formed, contain
the required structural elements, and pass basic integrity checks.
"""
from __future__ import annotations

import re

from utils.logging import get_logger

logger = get_logger(__name__)


def validate_agentmd(text: str) -> bool:
    """Quick validation: check that agent.md has minimum required structure.

    Returns True if the text contains frontmatter, a title, and at least
    one step heading. Returns False otherwise.
    """
    if not text or not text.strip():
        return False

    has_frontmatter = text.strip().startswith("---")
    has_steps = bool(re.search(r"^##\s+", text, re.MULTILINE))
    has_title = bool(re.search(r"^#\s+", text, re.MULTILINE))

    return has_frontmatter and has_title and has_steps


def validate_agentmd_strict(text: str) -> tuple[bool, list[str]]:
    """Detailed validation with error messages.

    Args:
        text: The agent.md content to validate.

    Returns:
        (is_valid, error_messages) tuple.
    """
    errors: list[str] = []

    if not text or not text.strip():
        errors.append("agent.md content is empty")
        return False, errors

    lines = text.strip().split("\n")
    logger.debug("Validating agent.md: %d lines", len(lines))

    if not lines[0].startswith("---"):
        errors.append("Missing YAML frontmatter (file should start with ---)")

    step_count = len(re.findall(r"^##\s+", text, re.MULTILINE))
    if step_count == 0:
        errors.append("Missing step definitions (need at least one ## heading)")

    if not re.search(r"^#\s+", text, re.MULTILINE):
        errors.append("Missing pipeline title (need a # level-1 heading)")

    return len(errors) == 0, errors


def show_draft(text: str) -> None:
    """Display draft agent.md content in terminal with ANSI highlighting."""
    logger.debug("Showing draft")
    print("\n" + "=" * 60)
    print("  Draft agent.md — Review before proceeding")
    print("=" * 60 + "\n")

    for line in text.split("\n"):
        if line.startswith("# "):
            print(f"\033[1;36m{line}\033[0m")
        elif line.startswith("## "):
            print(f"\033[1;33m{line}\033[0m")
        elif line.startswith("> "):
            print(f"\033[2m{line}\033[0m")
        elif line.startswith("---"):
            print(f"\033[2;34m{line}\033[0m")
        elif line.strip().startswith(("depends_on:", "input:", "output:", "browser:")):
            print(f"\033[32m{line}\033[0m")
        else:
            print(line)

    print("\n" + "-" * 60)
    print("  Press Enter to confirm | Ctrl+C to cancel")
    print("-" * 60)


def confirm_execution() -> bool:
    """Wait for user confirmation. Returns False on Ctrl+C."""
    logger.debug("Waiting for user confirmation")
    try:
        input()
        return True
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled")
        return False
