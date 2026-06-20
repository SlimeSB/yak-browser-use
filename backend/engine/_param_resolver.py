"""Parameter template resolver — resolves ${path.to.field} and {_source_key: "name"}
references in tool call arguments against a shared_store dict.

Returns (resolved_params, errors) — a deep copy with all templates resolved,
and a list of failed paths. Original params are never modified.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_SENTINEL = object()

_TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_params(params: dict, shared_store: dict | None) -> tuple[dict, list[str]]:
    """Resolve parameter templates in a params dict.

    Supports two consumer syntaxes:
    - ``${path.to.field}`` — string template replacement (Preset mode)
    - ``{_source_key: "name"}`` — whole-dict replacement (Chat mode),
      internally converted to ``${name.data}``

    Args:
        params: The raw parameters dict (e.g. LLM tool call args).
        shared_store: The runtime data bus dict, or None.

    Returns:
        (resolved_params, errors) where *resolved_params* is a deep copy
        with all templates resolved, and *errors* is a list of failed
        path strings (empty when all resolved successfully).
    """
    store: dict = shared_store or {}
    errors: list[str] = []
    resolved = _resolve_recursive(copy.deepcopy(params), store, errors)
    return resolved, errors


def _resolve_recursive(obj: Any, store: dict, errors: list[str]) -> Any:
    if isinstance(obj, dict):
        if _is_source_key_ref(obj):
            key = obj["_source_key"]
            return _resolve_path(store, f"{key}.data", errors)
        return {k: _resolve_recursive(v, store, errors) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_resolve_recursive(item, store, errors) for item in obj]

    if isinstance(obj, str):
        return _resolve_template_string(obj, store, errors)

    return obj


def _is_source_key_ref(obj: dict) -> bool:
    return len(obj) == 1 and "_source_key" in obj


def _resolve_template_string(s: str, store: dict, errors: list[str]) -> Any:
    m = _TEMPLATE_PATTERN.fullmatch(s.strip())
    if m:
        path = m.group(1)
        if _has_nested_template(path):
            return s
        return _resolve_path(store, path, errors)

    def _replacer(match: re.Match) -> str:
        path = match.group(1)
        if _has_nested_template(path):
            return match.group(0)
        value = _get_nested(store, path)
        if value is _SENTINEL:
            errors.append(path)
            return f"__RESOLVE_FAILED__:{path}"
        if isinstance(value, str):
            return value
        return str(value)

    return _TEMPLATE_PATTERN.sub(_replacer, s)


def _has_nested_template(path: str) -> bool:
    return "${" in path


def _resolve_path(store: dict, path: str, errors: list[str]) -> Any:
    value = _get_nested(store, path)
    if value is _SENTINEL:
        errors.append(path)
        return f"__RESOLVE_FAILED__:{path}"
    return value


def _get_nested(d: dict, path: str) -> Any:
    keys = path.split(".")
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return _SENTINEL
    return d
