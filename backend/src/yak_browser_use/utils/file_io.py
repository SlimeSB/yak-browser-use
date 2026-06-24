"""File I/O utilities — atomic writes, input resolution, JSON loading."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable


def atomic_write(target: Path, write_fn: Callable[[Path], None]) -> None:
    """Write to *target* atomically via a temporary file and rename.

    Args:
        target: The final file path.
        write_fn: A callable that receives a temp *Path* and writes data to it.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix or ".tmp"
    prefix = f"_atomic_{target.stem}_"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=str(target.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        write_fn(tmp)
        os.replace(str(tmp), str(target))
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def resolve_input_files(input_files: dict[str, str]) -> list[Path]:
    """Resolve input file paths from *input_files* mapping, returning only existing files."""
    return [Path(path_str) for path_str in input_files.values() if Path(path_str).exists()]


def load_json_records(path: Path) -> list[dict]:
    """Load records from a JSON file, handling both list and dict top-level structures.

    *list* values are returned directly.
    *dict* values — each value is checked; if any value is a list it is returned,
    otherwise the dict is wrapped in a single-element list.
    """
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
