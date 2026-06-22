"""Prompt template loader with {variable} substitution."""

from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, **variables: str) -> str:
    """Load a prompt template by name (without .md suffix).

    Supports {variable} placeholder substitution via keyword arguments.
    Only explicitly-passed variable names are replaced. Unreferenced
    {placeholders} in the template remain as-is (no KeyError).

    Uses custom string replacement (not str.format()) to avoid
    KeyError from natural {literal} characters in prompt files.
    """
    path = (_PROMPTS_DIR / name).with_suffix(".md")
    if not path.exists():
        logger.warning("Prompt file not found: %s", path)
        return ""
    logger.debug("Loaded prompt: %s", path)
    text = path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{key}}}", value)
    return text


def load_skill(name: str) -> str:
    """Load a skill's body (without YAML frontmatter) for prompt injection.

    Returns the body text, or an empty string if the skill is not found
    or has an error.
    """
    from utils.skill_loader import skill_view

    result = skill_view(name)
    if "error" in result:
        logger.warning("load_skill: skill '%s' not available: %s", name, result["error"])
        return ""
    return result.get("body", "")


def build_system_prompt() -> str:
    """Build the full system prompt including auto-injected system skills.

    Loads ``chat/system`` and appends the body of every skill tagged
    with ``system``.  Uses ``skill_list(include_body=True)`` so every
    skill is parsed only once.
    """
    prompt = load_prompt("chat/system")

    error_recovery = load_prompt("guidance/error_recovery")
    if error_recovery:
        prompt += "\n\n" + error_recovery

    from utils.skill_loader import skill_list

    skills = skill_list(include_body=True)
    for s in skills:
        if "system" in (s.get("tags") or []):
            body = s.get("body", "")
            if body:
                prompt += "\n\n" + body

    return prompt
