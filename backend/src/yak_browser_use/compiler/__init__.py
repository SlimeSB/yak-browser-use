"""Compiler — pipeline.yaml parsing, DAG construction, handler resolution, and code generation."""

from yak_browser_use.compiler.models import StepDef, PipelineDef
from yak_browser_use.compiler.parser import parse_pipeline, inject_params_to_pipeline
from yak_browser_use.compiler.graph import build_graph, get_execution_order, validate_file_refs
from yak_browser_use.compiler.resolver import resolve, resolve_with_generator
from yak_browser_use.compiler.generator import generate_handler_prompt, generate_handler, compile_handler_code
from yak_browser_use.compiler.generator import model_actions_to_ops, write_pipeline_learned
from yak_browser_use.compiler.diff import diff_ops, filter_rejected, add_to_rejected, save_suggestions
from yak_browser_use.compiler.diff import merge_extra_ops, extract_summary

__all__ = [
    "parse_pipeline",
    "inject_params_to_pipeline",
    "StepDef",
    "PipelineDef",
    "build_graph",
    "get_execution_order",
    "validate_file_refs",
    "resolve",
    "resolve_with_generator",
    "generate_handler_prompt",
    "generate_handler",
    "compile_handler_code",
    "model_actions_to_ops",
    "write_pipeline_learned",
    "diff_ops",
    "filter_rejected",
    "add_to_rejected",
    "save_suggestions",
    "merge_extra_ops",
    "extract_summary",
]
