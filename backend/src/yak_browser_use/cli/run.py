"""CLI command to run a pipeline.yaml.

Usage:
  ybu run <path>              # Execute synchronously, print result
  ybu run <path> -D key=val   # Pass pipeline params
"""

from __future__ import annotations

import json
from pathlib import Path

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


async def _cmd_run(path: str, params: dict | None = None) -> None:
    """Run a pipeline synchronously (blocks until done)."""
    from yak_browser_use.tools.registry import build_registry
    build_registry()

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
        from yak_browser_use.compiler.parser import inject_params_to_pipeline

        pipeline_text = inject_params_to_pipeline(pipeline_text, params)
        for step in steps:
            if step.get("is_goal"):
                desc = step.get("goal_description", "") or step.get("description", "")
                extras = " | ".join(f"{k}={v}" for k, v in params.items())
                step["goal_description"] = f"{desc} (params: {extras})"

    # 3. Connect to Chrome
    try:
        from cdp import discover_ws_url
        from yak_browser_use.cdp.playwright_bridge import PlaywrightBridge
        from yak_browser_use.cdp.helpers import CDPHelpers

        ws_url = await discover_ws_url()
        bridge = PlaywrightBridge(ws_url)
        await bridge.start()
        browser = CDPHelpers(bridge)
    except Exception as e:
        logger.error("Cannot connect to Chrome: %s", e)
        raise SystemExit(1)

    # 4. Run pipeline (blocks until done; handles workspace, run_id, status internally)
    from yak_browser_use.engine.runner_preset import run_pipeline

    try:
        result = await run_pipeline(
            pipeline_name=parsed.name,
            steps=steps,
            cdp_helpers=browser,
            pipeline_path=input_path,
            frontmatter=parsed.frontmatter,
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
    """Parse pipeline.yaml and prepare ordered steps."""
    from yak_browser_use.compiler.prepare import prepare_steps
    return prepare_steps(content, pipeline_path)
