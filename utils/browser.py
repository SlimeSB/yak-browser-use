"""LLM factory — creates a BrowserUse LLM instance from config."""
from __future__ import annotations

import os


def create_llm(model: str | None = None) -> object:
    """Create a browser-use LLM instance.
    
    Reads LBU_MODEL / LBU_API_KEY / LBU_API_BASE / LBU_PROVIDER
    from environment, or falls back to sensible defaults.
    """
    from browser_use.llm import LLM

    provider = os.environ.get("LBU_PROVIDER", "openrouter")
    model_name = model or os.environ.get("LBU_MODEL", "deepseek/deepseek-chat")
    api_key = os.environ.get("LBU_API_KEY", "")
    api_base = os.environ.get("LBU_API_BASE", "")

    kwargs = {
        "model": model_name,
        "provider": provider,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    return LLM(**kwargs)
