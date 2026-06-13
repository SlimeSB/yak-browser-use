"""Generic data processing tools for browser-use pipelines.

Functions follow the convention:
    CAPABILITIES = []  # or ["browser"] if CDP needed

    async def my_tool(input_files: dict[str, str], output_dir: str, **params) -> None:
        ...
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

CAPABILITIES: list[str] = []


def _resolve_input_files(input_files: dict[str, str]) -> list[Path]:
    """Resolve input file paths from the file mapping."""
    paths = []
    for key, path_str in input_files.items():
        p = Path(path_str)
        if p.exists():
            paths.append(p)
    return paths


def _load_records(path: Path) -> list[dict]:
    """Load records from a JSON or CSV file."""
    ext = path.suffix.lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Try common structures
            for val in data.values():
                if isinstance(val, list):
                    return val
            return [data]
        return []
    elif ext == ".csv":
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return list(reader)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def _save_records(records: list[dict], output_dir: str, name: str) -> Path:
    """Save records as JSON to the output directory."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return out_path


# ── filter_data ──


async def filter_data(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Filter records by matching criteria.

    Parameters in **params:
        field (str): The field name to filter on.
        value (str): The value to match (exact match).
        pattern (str): Regex pattern to match against the field.
        min (float): Minimum numeric value (inclusive).
        max (float): Maximum numeric value (inclusive).
        exclude (bool): If True, exclude matching records instead of including.
        key_field (str): Field to check for key presence (e.g., in a list).
        key_values (list): Values the key_field must be in (or not in if exclude=True).
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("filter_data: starting, %d input file(s), params=%s", len(files), str(params))

    all_records: list[dict] = []
    for f in files:
        all_records.extend(_load_records(f))

    field = params.get("field")
    value = params.get("value")
    pattern = params.get("pattern")
    min_val = params.get("min")
    max_val = params.get("max")
    exclude = params.get("exclude", False)
    key_field = params.get("key_field")
    key_values = params.get("key_values")

    filtered = list(all_records)

    if field and value is not None:
        filtered = [
            r for r in filtered
            if (str(r.get(field, "")) == str(value)) != exclude
        ]

    if field and pattern:
        compiled = re.compile(pattern)
        filtered = [
            r for r in filtered
            if bool(compiled.search(str(r.get(field, "")))) != exclude
        ]

    if min_val is not None:
        try:
            filtered = [
                r for r in filtered
                if float(r.get(field or "price", 0)) >= min_val
            ]
        except (ValueError, TypeError):
            pass

    if max_val is not None:
        try:
            filtered = [
                r for r in filtered
                if float(r.get(field or "price", 0)) <= max_val
            ]
        except (ValueError, TypeError):
            pass

    if key_field and key_values:
        filtered = [
            r for r in filtered
            if (r.get(key_field) in key_values) != exclude
        ]

    out_path = _save_records(filtered, output_dir, "filtered.json")
    print(f"filter_data: {len(all_records)} -> {len(filtered)} records written to {out_path}")


# ── sort_data ──


async def sort_data(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Sort records by a given field.

    Parameters in **params:
        field (str): The field name to sort by (required).
        reverse (bool): Sort descending if True (default: False).
        numeric (bool): Treat field values as numbers when sorting (default: True).
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("sort_data: starting, %d input file(s), params=%s", len(files), str(params))

    all_records: list[dict] = []
    for f in files:
        all_records.extend(_load_records(f))

    field = params.get("field", "")
    reverse = params.get("reverse", False)
    numeric = params.get("numeric", True)

    if not field:
        raise ValueError("sort_data requires a 'field' parameter")

    def sort_key(record: dict) -> Any:
        raw = record.get(field, "")
        if numeric:
            try:
                return float(raw)
            except (ValueError, TypeError):
                return raw
        return str(raw)

    sorted_records = sorted(all_records, key=sort_key, reverse=reverse)

    out_path = _save_records(sorted_records, output_dir, "sorted.json")
    print(f"sort_data: {len(sorted_records)} records sorted by '{field}' -> {out_path}")


# ── deduplicate ──


async def deduplicate(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Remove duplicate records based on key fields.

    Parameters in **params:
        key (str | list[str]): Field name(s) to use for dedup (default: first field).
        keep (str): 'first' or 'last' occurrence to keep (default: 'first').
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("deduplicate: starting, %d input file(s), params=%s", len(files), str(params))

    all_records: list[dict] = []
    for f in files:
        all_records.extend(_load_records(f))

    keys = params.get("key")
    keep = params.get("keep", "first")

    if isinstance(keys, str):
        keys = [keys]
    if not keys and all_records:
        # Default to the first available field
        keys = [list(all_records[0].keys())[0]]

    if not keys:
        raise ValueError("deduplicate requires a 'key' parameter or input with fields")

    seen: set = set()
    deduped: list[dict] = []

    records_iter = all_records if keep == "first" else reversed(all_records)

    for record in records_iter:
        # Build composite key
        composite = tuple(str(record.get(k, "")) for k in keys)
        if composite not in seen:
            seen.add(composite)
            deduped.append(record)

    if keep == "last":
        deduped.reverse()

    out_path = _save_records(deduped, output_dir, "deduped.json")
    print(f"deduplicate: {len(all_records)} -> {len(deduped)} records -> {out_path}")


# ── map_fields ──


async def map_fields(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Rename or remap fields in records.

    Parameters in **params:
        mapping (dict[str, str]): Old field name -> new field name.
        drop_missing (bool): Drop records missing required fields (default: False).
        defaults (dict[str, Any]): Default values for fields that don't exist.
        keep_original (bool): Keep original fields alongside renamed ones (default: False).
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("map_fields: starting, %d input file(s), params=%s", len(files), str(params))

    all_records: list[dict] = []
    for f in files:
        all_records.extend(_load_records(f))

    mapping = params.get("mapping", {})
    drop_missing = params.get("drop_missing", False)
    defaults = params.get("defaults", {})
    keep_original = params.get("keep_original", False)

    if not mapping:
        raise ValueError("map_fields requires a 'mapping' parameter")

    mapped_records: list[dict] = []
    for record in all_records:
        if drop_missing:
            if any(record.get(old) is None for old in mapping):
                continue

        new_record = dict(record) if keep_original else {}
        for old_key, new_key in mapping.items():
            value = record.get(old_key, defaults.get(old_key))
            new_record[new_key] = value

        mapped_records.append(new_record)

    out_path = _save_records(mapped_records, output_dir, "mapped.json")
    print(f"map_fields: {len(all_records)} -> {len(mapped_records)} records -> {out_path}")
