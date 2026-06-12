from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

def load_prompt(name: str) -> str:
    """Load a prompt template by name (without .md suffix)."""
    path = (_PROMPTS_DIR / name).with_suffix(".md")
    return path.read_text(encoding="utf-8")
