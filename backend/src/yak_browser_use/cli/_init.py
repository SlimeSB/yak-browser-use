from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from yak_browser_use.utils._path import project_root


_INITIALIZED = False


def init_cli(level: str | None = None) -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    root_env = project_root() / ".env"
    local_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=root_env)
    if local_env.exists():
        load_dotenv(dotenv_path=local_env, override=True)

    from yak_browser_use.utils.logging import setup_logging
    setup_logging(level=level)
