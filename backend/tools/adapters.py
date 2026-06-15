"""Data format adapters for browser-use pipelines.

Converts between CSV and JSON formats, and provides field mapping utilities.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

CAPABILITIES: list[str] = []


# ── CSV ↔ JSON ──


async def csv_to_json(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Convert CSV input files to JSON output.

    Parameters in **params:
        delimiter (str): CSV delimiter (default: ',').
        encoding (str): File encoding (default: 'utf-8-sig').
        key_field (str): If set, output a dict keyed by this field instead of a list.
        pretty (bool): Pretty-print JSON output (default: True).
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("csv_to_json: starting with %d input file(s), output_dir=%s", len(files), output_dir)

    delimiter = params.get("delimiter", ",")
    encoding = params.get("encoding", "utf-8-sig")
    key_field = params.get("key_field")
    pretty = params.get("pretty", True)

    all_records: list[dict] = []
    for filepath in files:
        with open(filepath, "r", encoding=encoding) as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                all_records.append(dict(row))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = _output_name(files[0], ".json")

    if key_field:
        keyed = {}
        for record in all_records:
            k = record.get(key_field)
            if k:
                keyed[str(k)] = record
        output_data = keyed
    else:
        output_data = all_records

    indent = 2 if pretty else None
    with open(out_dir / out_name, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=indent)

    logger.debug("csv_to_json: %d records -> %s", len(all_records), out_dir / out_name)
    print(f"csv_to_json: {len(all_records)} records -> {out_dir / out_name}")


async def json_to_csv(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Convert JSON input files to CSV output.

    Parameters in **params:
        delimiter (str): CSV delimiter (default: ',').
        encoding (str): File encoding (default: 'utf-8').
        fields (list[str]): Specific fields/columns to include (default: all).
        flatten (bool): Flatten nested dict values with dot notation (default: False).
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("json_to_csv: starting with %d input file(s), output_dir=%s", len(files), output_dir)

    delimiter = params.get("delimiter", ",")
    encoding = params.get("encoding", "utf-8")
    fields = params.get("fields")
    flatten = params.get("flatten", False)

    all_records: list[dict] = []
    for filepath in files:
        records = _load_json_records(filepath)
        all_records.extend(records)

    if not all_records:
        print("json_to_csv: no records found")
        return

    # Optionally flatten nested dicts
    if flatten:
        flattened = []
        for record in all_records:
            flat = _flatten_dict(record)
            flattened.append(flat)
        all_records = flattened

    # Determine field names
    if fields:
        fieldnames = fields
    else:
        # Union of all keys across records
        fieldnames = list(dict.fromkeys(k for r in all_records for k in r.keys()))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = _output_name(files[0], ".csv")

    with open(out_dir / out_name, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for record in all_records:
            writer.writerow({k: record.get(k, "") for k in fieldnames})

    logger.debug("json_to_csv: %d records -> %s", len(all_records), out_dir / out_name)
    print(f"json_to_csv: {len(all_records)} records -> {out_dir / out_name}")


# ── Field mapping ──


async def apply_field_mapping(
    input_files: dict[str, str],
    output_dir: str,
    **params: Any,
) -> None:
    """Apply a field mapping / rename to records.

    Parameters in **params:
        mapping (dict[str, str]): Source field -> target field name mapping.
        drop_others (bool): Drop fields not in the mapping (default: False).
        default (Any): Default value for missing source fields.
    """
    files = _resolve_input_files(input_files)
    if not files:
        raise FileNotFoundError("No input files found from input_files mapping")

    logger.debug("apply_field_mapping: starting with %d input file(s), output_dir=%s", len(files), output_dir)

    mapping = params.get("mapping", {})
    drop_others = params.get("drop_others", False)
    default = params.get("default", "")

    if not mapping:
        raise ValueError("apply_field_mapping requires a 'mapping' parameter")

    all_records: list[dict] = []
    for filepath in files:
        ext = filepath.suffix.lower()
        if ext == ".json":
            all_records.extend(_load_json_records(filepath))
        elif ext == ".csv":
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                all_records.extend(list(reader))

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

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = _output_name(files[0], ".json")

    with open(out_dir / out_name, "w", encoding="utf-8") as f:
        json.dump(mapped_records, f, ensure_ascii=False, indent=2)

    logger.debug("apply_field_mapping: %d records -> %s", len(mapped_records), out_dir / out_name)
    print(f"apply_field_mapping: {len(mapped_records)} records -> {out_dir / out_name}")


# ── helpers ──


def _resolve_input_files(input_files: dict[str, str]) -> list[Path]:
    paths = []
    for key, path_str in input_files.items():
        p = Path(path_str)
        if p.exists():
            paths.append(p)
    return paths


def _load_json_records(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list):
                return val
        return [data]
    return []


def _output_name(source: Path, target_ext: str) -> str:
    """Generate an output filename based on the first input file."""
    stem = source.stem
    # Remove double extensions like .json.json
    base_ext = target_ext.rsplit(".", 1)[0]
    if base_ext:
        while stem.endswith(base_ext):
            stem = stem.rsplit(".", 1)[0]
    return f"{stem}{target_ext}"


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
