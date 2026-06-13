"""LLM factory — creates a BrowserUse LLM instance from config."""
from __future__ import annotations

import json
import os
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


def _get_config_path() -> Path:
    p = Path.home() / ".ybu" / "provider.json"
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
    """Create a browser-use LLM instance.

    Reads from ~/.ybu/provider.json first, then falls back to
    YBU_MODEL / YBU_API_KEY / YBU_API_BASE env vars.
    """
    from browser_use.llm.openai.chat import ChatOpenAI

    cfg = _load_config()

    model_name = model or cfg.get("model") or os.environ.get("YBU_MODEL", "gpt-4o")
    api_key = cfg.get("api_key") or os.environ.get("YBU_API_KEY", "")
    api_base = cfg.get("api_base") or os.environ.get("YBU_API_BASE", "")

    kwargs: dict = {"model": model_name}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["base_url"] = api_base

    return ChatOpenAI(**kwargs)
