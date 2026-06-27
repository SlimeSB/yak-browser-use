"""Parameter template resolver — resolves {*path} and ${path} references
in tool call arguments against a shared_store dict.

Returns (resolved_params, errors) — a deep copy with all templates resolved,
and a list of failed paths. Original params are never modified.

Syntax reference
----------------

Three syntaxes exist for different use cases; they are NOT interchangeable.

``{*path}`` — whole-string pointer (shared_store data lookup)
    Regex: ``{\*([\\w.]+)}``, fullmatch only.
    The ENTIRE string must be ``{*key}`` — partial matches are ignored so
    that JSON literal braces (e.g. ``{"a": 1}``) never trigger resolution.
    The ``*`` prefix marks this as an explicit shared_store pointer.
    Returns the store value AS-IS — can be any type (str, int, list, dict,
    None, etc.).
    Use when the entire parameter value IS a reference to a shared_store
    slot (e.g. passing a prior step's full output as the next tool's input).
    This is the canonical syntax for shared_store read pointers.

``${path}`` — template interpolation (substitution or whole-string)
    Regex: ``\\${([^}]+)}``, matches both full-string and partial.
    - Full-match: behaves like ``{*path}`` — whole-string replacement.
    - Partial (sub): replaces inline ``${key}`` occurrences within a larger
      string. The result is ALWAYS a string (non-string store values cause
      a resolve error).
    The ``$`` prefix disambiguates braces from JSON — safe for use inside
    longer strings like ``"https://${host}/api/v1"``.
    Use when you need to interpolate a value inside a larger string.

``{path}`` — DEPRECATED (bare data lookup, no sigil)
    Previously used for whole-string replacement. Still supported for
    backward compatibility, but new code should prefer ``{*path}`` for
    explicit pointer semantics.

Pick ``{*path}`` when:
    - The whole parameter is a shared_store pointer reference
    - You want to preserve the store value's type (list, dict etc.)

Pick ``${path}`` when:
    - You need inline interpolation inside a larger string
    - The store value is / should be coerced to a string
"""

from __future__ import annotations

import copy
import re
from typing import Any

_SENTINEL = object()

_POINTER_PATTERN = re.compile(r"\{\*([\w.]+)\}")  # {*key}
_PATH_PATTERN = re.compile(r"\{([\w.]+)\}")        # {key} — deprecated compat
_TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_params(params: dict, shared_store: dict | None) -> tuple[dict, list[str]]:
    """Resolve parameter templates in a params dict.

    Supports two syntaxes:
    - ``{*path}`` — whole-string pointer (primary), fullmatch
    - ``{path}`` — whole-string (deprecated compat), fullmatch
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
    # {*path} fullmatch — whole-string pointer (primary syntax)
    m = _POINTER_PATTERN.fullmatch(s.strip())
    if m:
        return _resolve_path(store, m.group(1), errors)

    # {path} fullmatch — whole-string reference (deprecated compat)
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


def strip_pointer(s: str) -> str:
    """Strip {*…} wrapper from a pointer string, or return as-is.

    ``strip_pointer("{*my_table}")`` → ``"my_table"``
    ``strip_pointer("my_table")``    → ``"my_table"``
    """
    if not isinstance(s, str):
        return s
    m = _POINTER_PATTERN.fullmatch(s.strip())
    return m.group(1) if m else s
