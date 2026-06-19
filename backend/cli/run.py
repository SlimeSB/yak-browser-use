"""CLI command to run a pipeline.yaml.

Usage:
  ybu run <path>              # Execute synchronously, print result
  ybu run <path> -D key=val   # Pass pipeline params
"""

from __future__ import annotations

import json
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


async def _cmd_run(path: str, params: dict | None = None) -> None:
    """Run a pipeline synchronously (blocks until done)."""
    input_path = Path(path)
    if not input_path.exists():
        logger.error("File not found: %s", path)
        raise SystemExit(1)

    pipeline_text = input_path.read_text(encoding="utf-8")

    # 1. Parse pipeline
    parsed, steps = _prepare_steps(pipeline_text, input_path)
    logger.info("Pipeline: %s  Steps: %d", parsed.name, len(steps))

    # 2. Inject params into both text (for snapshot) and steps
    if params:
        from compiler.parser import inject_params_to_pipeline

        pipeline_text = inject_params_to_pipeline(pipeline_text, params)
        for step in steps:
            if step.get("is_goal"):
                desc = step.get("goal_description", "") or step.get("description", "")
                extras = " | ".join(f"{k}={v}" for k, v in params.items())
                step["goal_description"] = f"{desc} (params: {extras})"

    # 3. Connect to Chrome
    try:
        from cdp import discover_ws_url
        from cdp.playwright_bridge import PlaywrightBridge
        from cdp.helpers import CDPHelpers

        ws_url = await discover_ws_url()
        bridge = PlaywrightBridge(ws_url)
        await bridge.start()
        browser = CDPHelpers(bridge)
    except Exception as e:
        logger.error("Cannot connect to Chrome: %s", e)
        raise SystemExit(1)

    # 4. Prepare guardian
    from engine._lifecycle.guardian import (
        create_guardian_from_frontmatter,
        inject_guardian_config_to_steps,
    )

    inject_guardian_config_to_steps(steps, parsed.frontmatter)
    guardian = create_guardian_from_frontmatter(parsed.frontmatter)

    from engine.agent import create_pipeline_llm_call

    llm_call = create_pipeline_llm_call(persist_id=f"pipeline_{parsed.name}")

    # 5. Run pipeline (blocks until done; handles workspace, run_id, status internally)
    from engine.runner_preset import run_pipeline

    try:
        result = await run_pipeline(
            pipeline_name=parsed.name,
            steps=steps,
            cdp_helpers=browser,
            pipeline_path=input_path,
            frontmatter=parsed.frontmatter,
            guardian=guardian,
            llm_call=llm_call,
        )
    finally:
        await bridge.stop()
        from cdp import cleanup_isolated

        await cleanup_isolated()

    # 6. Print summary
    status = "completed" if not result.errors else "failed"
    elapsed = getattr(result, "elapsed", 0)
    elapsed_str = f"{elapsed:.1f}s" if elapsed < 120 else f"{elapsed / 60:.1f}m"

    print()
    print("=" * 50)
    print(f"  Pipeline: {parsed.name}")
    print(f"  Status:   {status}")
    print(f"  Elapsed:  {elapsed_str}")
    print(f"  Steps:    {len(steps)}")
    print(f"  Run ID:   {result.run_id}")
    print(f"  Workspace: userdata/workspaces/{parsed.name}/runs/{result.run_id}/")
    if result.errors:
        for err in result.errors:
            print(f"  ✗ {err}")
    print("=" * 50)
    print()

    if result.errors:
        raise SystemExit(1)


def _prepare_steps(content: str, pipeline_path: Path) -> tuple[any, list[dict]]:
    """Parse pipeline.yaml and prepare ordered steps. (from api/routes.py)"""
    from compiler.context import resolve_context
    from compiler.graph import build_graph, get_execution_order, validate_file_refs
    from compiler.parser import parse_pipeline
    from compiler.resolver import resolve

    parsed = parse_pipeline(content)
    context = resolve_context(parsed.frontmatter, pipeline_path)
    if context:
        for step in parsed.steps:
            step.system_prompt = context

    dag = build_graph(parsed.steps)
    validate_file_refs(parsed.steps)
    execution_order = get_execution_order(dag)

    step_key_map = {s.key: s for s in parsed.steps}
    ordered_steps = [step_key_map[k] for k in execution_order]

    steps_data: list[dict] = []
    for step in ordered_steps:
        handler = resolve(step, parsed.name)
        step_data = step.to_runtime_dict(handler)
        steps_data.append(step_data)

    logger.info("Prepared %d steps for pipeline '%s'", len(steps_data), parsed.name)
    return parsed, steps_data
