"""
validate.py — Validation for pipeline.yaml documents.

Validates that pipeline.yaml documents are well-formed YAML and
pass Pydantic schema validation.
"""
from __future__ import annotations

import yaml
from pydantic import ValidationError

from compiler.schema import PipelineYaml
from utils.logging import get_logger

logger = get_logger(__name__)


def validate_pipeline(text: str) -> bool:
    """Quick validation: check that pipeline.yaml is valid.

    Returns True if the text is parseable YAML that passes schema validation.
    Returns False otherwise.
    """
    if not text or not text.strip():
        return False

    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return False
        PipelineYaml.model_validate(data)
        return True
    except (yaml.YAMLError, ValidationError):
        return False


def validate_pipeline_strict(text: str) -> tuple[bool, list[str]]:
    """Detailed validation with error messages.

    Args:
        text: The pipeline.yaml content to validate.

    Returns:
        (is_valid, error_messages) tuple.
    """
    errors: list[str] = []

    if not text or not text.strip():
        errors.append("pipeline.yaml content is empty")
        return False, errors

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        errors.append(f"YAML syntax error: {e}")
        return False, errors

    if not isinstance(data, dict):
        errors.append("Pipeline YAML must be a top-level mapping")
        return False, errors

    try:
        PipelineYaml.model_validate(data)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e}")
        return False, errors

    return True, []


def show_draft(text: str) -> None:
    """Display draft pipeline.yaml content in terminal."""
    logger.debug("Showing draft")
    print("\n" + "=" * 60)
    print("  Draft pipeline.yaml — Review before proceeding")
    print("=" * 60 + "\n")

    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            print(f"\033[2;37m{line}\033[0m")
        elif ":" in stripped and not stripped.startswith("-"):
            key_part = stripped.split(":", 1)[0]
            rest = line[len(key_part):]
            print(f"\033[32m{key_part}\033[0m{rest}")
        elif stripped.startswith("- "):
            inner = stripped[2:]
            if ":" in inner:
                k, _, v = inner.partition(":")
                print(f"  \033[33m- {k}:\033[0m{v}")
            else:
                print(line)
        else:
            print(line)

    print("\n" + "-" * 60)
    print("  Press Enter to confirm | Ctrl+C to cancel")
    print("-" * 60)


def confirm_execution() -> bool:
    """Wait for user confirmation. Returns False on Ctrl+C."""
    logger.debug("Waiting for user confirmation")
    try:
        input()
        return True
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled")
        return False
