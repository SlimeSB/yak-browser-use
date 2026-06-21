"""Parameter template resolver — resolves {path} and ${path} references
in tool call arguments against a shared_store dict.

Returns (resolved_params, errors) — a deep copy with all templates resolved,
and a list of failed paths. Original params are never modified.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_SENTINEL = object()

_TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")
_PATH_PATTERN = re.compile(r"\{([\w.]+)\}")


def resolve_params(params: dict, shared_store: dict | None) -> tuple[dict, list[str]]:
    """Resolve parameter templates in a params dict.

    Supports two syntaxes:
    - ``{path}`` — whole-string reference (fullmatch), bare data lookup
    - ``${path}`` — string template replacement (sub) or whole-string (fullmatch)

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
        return {k: _resolve_recursive(v, store, errors) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_resolve_recursive(item, store, errors) for item in obj]

    if isinstance(obj, str):
        return _resolve_template_string(obj, store, errors)

    return obj


def _resolve_template_string(s: str, store: dict, errors: list[str]) -> Any:
    # {path} fullmatch — whole-string reference (primary syntax)
    m = _PATH_PATTERN.fullmatch(s.strip())
    if m:
        return _resolve_path(store, m.group(1), errors)

    # ${path} fullmatch — whole-string reference
    m = _TEMPLATE_PATTERN.fullmatch(s.strip())
    if m:
        path = m.group(1)
        if _has_nested_template(path):
            return s
        return _resolve_path(store, path, errors)

    # ${path} sub — partial template replacement
    def _replacer(match: re.Match) -> str:
        path = match.group(1)
        if _has_nested_template(path):
            return match.group(0)
        value = _get_nested(store, path)
        if value is _SENTINEL:
            errors.append(path)
            return match.group(0)
        if isinstance(value, str):
            return value
        errors.append(path)
        return match.group(0)

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
