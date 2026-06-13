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
