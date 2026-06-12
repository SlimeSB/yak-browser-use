"""
resolver.py — Three-level handler resolution for step definitions.

Resolves a StepDef to an executable Python handler function through
three tiers:
1. Static handler (pre-written .py file in tasks/<pipeline>/handlers/)
2. Cached handler from a previous LLM generation run
3. LLM generation (returns None — caller should invoke generator.py)
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from compiler.parser import StepDef
from utils.logging import get_logger

logger = get_logger(__name__)

# Default locations for handler discovery
TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


def resolve(step_def: StepDef, pipeline_name: str) -> Callable | None:
    """Three-tier handler resolution for a step definition.

    Tier 1 — Static handler: tasks/<pipeline_name>/handlers/<step_key>.py
    Tier 2 — Cached generated: generated/<pipeline_name>/<step_key>.py
    Tier 3 — LLM generation: returns None (caller should invoke generator)

    Args:
        step_def: The step definition to resolve a handler for.
        pipeline_name: Name of the pipeline the step belongs to.

    Returns:
        A callable handler function, or None if generation is needed.
    """
    step_key = step_def.key

    # Tier 1: Static handler file
    handler_dir = TASKS_DIR / pipeline_name / "handlers"
    handler_file = handler_dir / f"{step_key}.py"
    logger.debug("Tier 1: checking %s", handler_file)
    if handler_file.exists():
        logger.debug("Tier 1: found handler for %s", step_def.name)
        return _load_handler_from_file(handler_file)

    # Fallback to exec.py (legacy format)
    exec_file = TASKS_DIR / pipeline_name / "exec.py"
    if exec_file.exists():
        return _load_handler_from_file(exec_file)

    # Tier 2: Cached generated handler
    generated_dir = Path("generated") / pipeline_name
    generated_file = generated_dir / f"{step_key}.py"
    logger.debug("Tier 2: checking generated handler for %s", step_def.key)
    if generated_file.exists():
        return _load_handler_from_file(generated_file)

    # Tier 3: Needs LLM generation
    logger.debug("Tier 3: LLM generation needed for %s", step_def.name)
    return None


def _load_handler_from_file(file_path: Path) -> Callable | None:
    """Load a handler function from a Python file.

    Looks for a callable named 'handle', 'main', or 'run' in the module.
    """
    import importlib.util
    import sys

    try:
        spec = importlib.util.spec_from_file_location(
            f"handler_{file_path.stem}",
            str(file_path),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "handle"):
                return module.handle
            if hasattr(module, "main"):
                return module.main
            if hasattr(module, "run"):
                return module.run
    except Exception:
        logger.exception("Failed to load handler from %s", file_path)

    return None


def resolve_with_generator(
    step_def: StepDef,
    pipeline_name: str,
    generate_fn: Callable | None = None,
) -> Callable | None:
    """Resolve handler, using an optional generator function as fallback.

    Args:
        step_def: The step definition to resolve.
        pipeline_name: Pipeline name for path discovery.
        generate_fn: Optional async generator function(step_def, pipeline_name)
                     that returns a callable or None.

    Returns:
        A callable handler, or None if all tiers fail.
    """
    handler = resolve(step_def, pipeline_name)
    if handler:
        return handler

    if generate_fn:
        return generate_fn(step_def, pipeline_name)

    return None
