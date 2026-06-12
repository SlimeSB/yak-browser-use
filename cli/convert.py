from __future__ import annotations

import sys
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


async def _cmd_convert(path: str, output: str | None = None, name: str | None = None) -> None:
    """Convert a natural-language document to pipeline.yaml format.

    Args:
        path: Path to the input document.
        output: Output file path (default: <cwd>/<stem>.pipeline.yaml).
        name: Pipeline name (default: inferred from filename).
    """
    from converter.convert import convert_document

    input_path = Path(path)

    if not input_path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    if name is None:
        name = input_path.stem

    if output is None:
        output_path = Path.cwd() / f"{input_path.stem}.pipeline.yaml"
    else:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path

    result = await convert_document(str(input_path), pipeline_name=name)

    output_path.write_text(result, encoding="utf-8")
    print(f"\u2705 Written to: {output_path.resolve()}")
