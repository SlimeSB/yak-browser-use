"""Compiler — pipeline.yaml parsing, DAG construction, handler resolution, and code generation."""

from compiler.models import StepDef, PipelineDef
from compiler.parser import parse_pipeline, inject_params_to_pipeline
from compiler.graph import build_graph, get_execution_order, validate_file_refs
from compiler.resolver import resolve, resolve_with_generator
from compiler.generator import generate_handler_prompt, generate_handler, compile_handler_code
from compiler.generator import model_actions_to_ops, write_pipeline_learned
from compiler.diff import diff_ops, filter_rejected, add_to_rejected, save_suggestions
from compiler.diff import merge_extra_ops, extract_summary

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
