"""Generic data processing tools for browser-use pipelines.

Migrated to ToolContext — functions receive ``ctx: ToolContext`` instead
of raw ``input_files`` / ``output_dir``.
"""
from __future__ import annotations

import re
from typing import Any

from engine.ops import ToolContext
from utils.logging import get_logger

logger = get_logger(__name__)


async def filter_data(ctx: ToolContext, params: dict) -> dict:
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
    all_records = await ctx.load_all_records()
    if not all_records:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("filter_data: starting, %d input file(s), params=%s", len(ctx.input_files), str(params))

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

    await ctx.save_json(filtered, "filtered.json")
    return {"ok": True, "input_count": len(all_records), "output_count": len(filtered)}


async def sort_data(ctx: ToolContext, params: dict) -> dict:
    """Sort records by a given field.

    Parameters in **params:
        field (str): The field name to sort by (required).
        reverse (bool): Sort descending if True (default: False).
        numeric (bool): Treat field values as numbers when sorting (default: True).
    """
    all_records = await ctx.load_all_records()
    if not all_records:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("sort_data: starting, %d input file(s), params=%s", len(ctx.input_files), str(params))

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

    await ctx.save_json(sorted_records, "sorted.json")
    return {"ok": True, "count": len(sorted_records), "field": field}


async def deduplicate(ctx: ToolContext, params: dict) -> dict:
    """Remove duplicate records based on key fields.

    Parameters in **params:
        key (str | list[str]): Field name(s) to use for dedup (default: first field).
        keep (str): 'first' or 'last' occurrence to keep (default: 'first').
    """
    all_records = await ctx.load_all_records()
    if not all_records:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("deduplicate: starting, %d input file(s), params=%s", len(ctx.input_files), str(params))

    keys = params.get("key")
    keep = params.get("keep", "first")

    if isinstance(keys, str):
        keys = [keys]
    if not keys and all_records:
        keys = [list(all_records[0].keys())[0]]

    if not keys:
        raise ValueError("deduplicate requires a 'key' parameter or input with fields")

    seen: set = set()
    deduped: list[dict] = []

    records_iter = all_records if keep == "first" else reversed(all_records)

    for record in records_iter:
        composite = tuple(str(record.get(k, "")) for k in keys)
        if composite not in seen:
            seen.add(composite)
            deduped.append(record)

    if keep == "last":
        deduped.reverse()

    await ctx.save_json(deduped, "deduped.json")
    return {"ok": True, "input_count": len(all_records), "output_count": len(deduped)}


async def map_fields(ctx: ToolContext, params: dict) -> dict:
    """Rename or remap fields in records.

    Parameters in **params:
        mapping (dict[str, str]): Old field name -> new field name.
        drop_missing (bool): Drop records missing required fields (default: False).
        defaults (dict[str, Any]): Default values for fields that don't exist.
        keep_original (bool): Keep original fields alongside renamed ones (default: False).
    """
    all_records = await ctx.load_all_records()
    if not all_records:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("map_fields: starting, %d input file(s), params=%s", len(ctx.input_files), str(params))

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

    await ctx.save_json(mapped_records, "mapped.json")
    return {"ok": True, "input_count": len(all_records), "output_count": len(mapped_records)}
