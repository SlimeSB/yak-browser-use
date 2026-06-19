"""Persistent parameter system — replaces the old credentials/keyring system.

Stores key-value parameters in a plain JSON file.
No environment variables, no keyring — just a simple JSON store.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent.parent / "userdata" / "params.json"


class ParamRef:
    """Opaque parameter reference — holds only the key name, not the value.
    
    ``str(ref)`` and ``repr(ref)`` return ``<param:key>`` placeholders.
    JSON serialization raises TypeError to prevent accidental leaks.
    """

    __slots__ = ("_key",)

    def __init__(self, key: str) -> None:
        object.__setattr__(self, "_key", key)

    @property
    def key(self) -> str:
        return self._key

    def __str__(self) -> str:
        return f"<param:{self._key}>"

    def __repr__(self) -> str:
        return f"<param:{self._key}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ParamRef):
            return NotImplemented
        return self._key == other._key

    def __hash__(self) -> int:
        return hash(self._key)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ParamRef is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ParamRef is immutable")


class ParamManager:
    """Manages persistent parameters stored in a JSON file.
    
    Thread-safe for single-process use. Not for concurrent multi-process access.
    """

    def __init__(self, store_path: str | Path | None = None):
        self._path = Path(store_path) if store_path else _DEFAULT_STORE_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, key: str) -> str | None:
        data = self._load()
        value = data.get(key)
        if value is not None:
            logger.debug("Param hit: %s", key)
        else:
            logger.debug("Param miss: %s", key)
        return value

    def set(self, key: str, value: str) -> None:
        logger.info("Param set: %s", key)
        data = self._load()
        data[key] = value
        self._save(data)

    def list_keys(self) -> list[str]:
        return list(self._load().keys())

    def delete(self, key: str) -> None:
        logger.info("Param delete: %s", key)
        data = self._load()
        data.pop(key, None)
        self._save(data)

    def resolve(self, ref: ParamRef | str) -> str:
        """Resolve a ParamRef or key string to its stored value.
        
        Raises RuntimeError if key is not found.
        """
        key = ref.key if isinstance(ref, ParamRef) else ref
        value = self.get(key)
        if value is None:
            available = self.list_keys()
            hint = f" Available keys: {available}" if available else " No keys stored."
            raise RuntimeError(f"Parameter '{key}' not found.{hint}")
        return value


# Module-level convenience singleton
_default_manager = ParamManager()


def resolve_param(ref: ParamRef | str) -> str:
    return _default_manager.resolve(ref)


def list_param_keys() -> list[str]:
    return _default_manager.list_keys()


def delete_param(key: str) -> None:
    _default_manager.delete(key)
