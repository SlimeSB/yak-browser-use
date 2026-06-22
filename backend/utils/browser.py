"""LLM factory — creates an LLMClient instance from config."""
from __future__ import annotations

import json
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


def _get_config_path() -> Path:
    p = Path(__file__).resolve().parent.parent.parent / "userdata" / "provider.json"
    logger.debug("Config path: %s", p)
    return p


def _load_config() -> dict:
    p = _get_config_path()
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            logger.debug("Loaded config from %s", p)
            return cfg
        except Exception as e:
            logger.debug("Failed to load config from %s: %s", p, e)
            pass
    logger.debug("No config file found at %s", p)
    return {}


def create_llm(model: str | None = None) -> object:
    """Create an LLMClient instance.

    Reads from <project>/userdata/provider.json.
    """
    from llm.client import LLMClient

    cfg = _load_config()

    model_name = model or cfg.get("model", "gpt-4o")
    api_key = cfg.get("api_key", "")
    api_base = cfg.get("api_base", "")

    if not api_key:
        raise ValueError(
            "LLM provider not configured. "
            "Please go to Settings → LLM Provider to set your API Key and Model."
        )

    kwargs: dict = {"model": model_name}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["base_url"] = api_base

    return LLMClient(**kwargs)
