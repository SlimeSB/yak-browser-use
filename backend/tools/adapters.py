"""Data format adapters for browser-use pipelines.

Converts between CSV and JSON formats, and provides field mapping utilities.
Migrated to ToolContext — functions receive ``ctx: ToolContext`` instead
of raw ``input_files`` / ``output_dir``.
"""
from __future__ import annotations

from typing import Any

from engine.ops import ToolContext
from utils.logging import get_logger

logger = get_logger(__name__)


async def csv_to_json(ctx: ToolContext, params: dict) -> dict:
    """Convert CSV input files to JSON output.

    Parameters in **params:
        delimiter (str): CSV delimiter (default: ',').
        encoding (str): File encoding (default: 'utf-8-sig').
        key_field (str): If set, output a dict keyed by this field instead of a list.
        pretty (bool): Pretty-print JSON output (default: True).
    """
    delimiter = params.get("delimiter", ",")
    key_field = params.get("key_field")

    all_records = await ctx.load_all_records()
    if not all_records:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("csv_to_json: starting with %d input file(s)", len(ctx.input_files))

    if key_field:
        keyed = {}
        for record in all_records:
            k = record.get(key_field)
            if k:
                keyed[str(k)] = record
        output_data = keyed
    else:
        output_data = all_records

    await ctx.save_json(output_data, "output.json")
    return {"ok": True, "count": len(all_records)}


async def json_to_csv(ctx: ToolContext, params: dict) -> dict:
    """Convert JSON input files to CSV output.

    Parameters in **params:
        delimiter (str): CSV delimiter (default: ',').
        encoding (str): File encoding (default: 'utf-8').
        fields (list[str]): Specific fields/columns to include (default: all).
        flatten (bool): Flatten nested dict values with dot notation (default: False).
    """
    fields = params.get("fields")
    flatten = params.get("flatten", False)

    all_records = await ctx.load_all_records()
    if not all_records:
        return {"ok": True, "count": 0, "message": "no records found"}

    logger.debug("json_to_csv: starting with %d input file(s)", len(ctx.input_files))

    if flatten:
        flattened = []
        for record in all_records:
            flat = _flatten_dict(record)
            flattened.append(flat)
        all_records = flattened

    if fields:
        fieldnames = fields
    else:
        fieldnames = list(dict.fromkeys(k for r in all_records for k in r.keys()))

    await ctx.save_csv(all_records, "output.csv")
    return {"ok": True, "count": len(all_records), "fields": fieldnames}


async def apply_field_mapping(ctx: ToolContext, params: dict) -> dict:
    """Apply a field mapping / rename to records.

    Parameters in **params:
        mapping (dict[str, str]): Source field -> target field name mapping.
        drop_others (bool): Drop fields not in the mapping (default: False).
        default (Any): Default value for missing source fields.
    """
    mapping = params.get("mapping", {})
    drop_others = params.get("drop_others", False)
    default = params.get("default", "")

    if not mapping:
        raise ValueError("apply_field_mapping requires a 'mapping' parameter")

    all_records = await ctx.load_all_records()
    if not all_records:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("apply_field_mapping: starting with %d input file(s)", len(ctx.input_files))

    mapped_records = []
    for record in all_records:
        mapped = {}
        for src_field, tgt_field in mapping.items():
            value = record.get(src_field, default)
            mapped[tgt_field] = value
        if not drop_others:
            for k, v in record.items():
                if k not in mapping:
                    mapped[k] = v
        mapped_records.append(mapped)

    await ctx.save_json(mapped_records, "mapped.json")
    return {"ok": True, "count": len(mapped_records)}


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dict into dot-notation keys."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
