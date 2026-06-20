"""
parser.py — Parse pipeline.yaml files into structured step definitions.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from compiler.models import PipelineDef
from compiler.schema import PipelineYaml
from utils.logging import get_logger

logger = get_logger(__name__)


# ── Template resolution (inline, lightweight) ──

_TEMPLATE_PATTERN = re.compile(r"\{\{template:([a-zA-Z0-9_-]+)\}\}")
_PROMPTS_DIR: Path | None = None


def _get_prompts_dir() -> Path:
    global _PROMPTS_DIR
    if _PROMPTS_DIR is None:
        _PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
    return _PROMPTS_DIR


def _resolve_templates(text: str) -> str:
    """Replace {{template:xxx}} placeholders with prompt file content."""

    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        tmpl_path = _get_prompts_dir() / f"{name}.md"
        if tmpl_path.is_file():
            return tmpl_path.read_text(encoding="utf-8").strip()
        logger.warning("Template '%s' not found at %s", name, tmpl_path)
        return match.group(0)

    return _TEMPLATE_PATTERN.sub(_replacer, text)


# ── Main parser ──


def parse_pipeline(text: str, strict_mode: bool = False) -> PipelineDef:
    """Parse pipeline.yaml text content into structured step definitions.

    Args:
        text: Full text content of a pipeline.yaml file.
        strict_mode: Reserved for future use (Pydantic always raises on invalid data).

    Returns:
        PipelineDef containing parsed steps and frontmatter configuration.

    Raises:
        yaml.YAMLError: When YAML syntax is invalid.
        pydantic.ValidationError: When YAML is syntactically correct but fails schema validation.
    """
    text = _resolve_templates(text)

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        logger.exception("Failed to parse pipeline YAML")
        raise

    if not isinstance(data, dict):
        raise yaml.YAMLError("Pipeline YAML must be a mapping at the top level")

    pipeline = PipelineYaml.model_validate(data)
    return pipeline.to_pipeline_def()


def inject_params_to_pipeline(yaml_text: str, params: dict | None) -> str:
    """Substitute {{param_name}} placeholders in pipeline YAML with actual values.

    Replaces template placeholders at the YAML structure level (after parsing),
    avoiding YAML injection risks that text-level str.replace would introduce.

    If YAML parsing fails, falls back to direct string replacement so that
    partially-formed templates are still usable.

    Args:
        yaml_text: Raw pipeline.yaml text containing {{param}} placeholders.
        params: Dict of parameter name to value mappings.

    Returns:
        Pipeline YAML text with all matching placeholders replaced.
    """
    if not params:
        return yaml_text

    try:
        data = yaml.safe_load(yaml_text)
        if data is None:
            return yaml_text
        _inject_recursive(data, params)
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except yaml.YAMLError:
        logger.warning(
            "YAML parse failed during param injection, falling back to string replacement"
        )
        return _PH_PATTERN.sub(lambda m: str(params.get(m.group(1), m.group(0))), yaml_text)


_PH_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _replace_placeholders(text: str, params: dict) -> str:
    """Replace all {{key}} placeholders in text with param values."""
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        if key in params:
            return str(params[key])
        logger.warning("Placeholder '{{%s}}' has no matching parameter, keeping as-is", key)
        return m.group(0)

    return _PH_PATTERN.sub(_replacer, text)


def _inject_recursive(node, params: dict) -> None:
    """Recursively walk dict/list, replacing {{key}} in string values."""
    if isinstance(node, dict):
        for key, val in node.items():
            if isinstance(val, str):
                node[key] = _replace_placeholders(val, params)
            elif isinstance(val, (dict, list)):
                _inject_recursive(val, params)
    elif isinstance(node, list):
        for i, val in enumerate(node):
            if isinstance(val, str):
                node[i] = _replace_placeholders(val, params)
            elif isinstance(val, (dict, list)):
                _inject_recursive(val, params)
