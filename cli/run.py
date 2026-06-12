from __future__ import annotations

import time
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

try:
    from engine.runner import run_pipeline  # noqa: E402
except ImportError:
    logger.warning("engine.runner not available yet; some features may be limited")


async def _cmd_run(
    path: str,
    convert: bool = False,
    verbose: bool = False,
    mode: str = "auto",
    params: dict | None = None,
) -> None:
    """Execute agent.md or convert + execute.

    Args:
        path: Path to the input file.
        convert: Force conversion even if the file looks like agent.md.
        verbose: Print full event stream output.
        mode: Pipeline execution mode (auto, static, learn, replay).
        params: Pipeline parameters from CLI (-D key=value).
    """
    input_path = Path(path)
    if not input_path.exists():
        logger.error("File not found: %s", path)
        raise SystemExit(1)

    content = input_path.read_text(encoding="utf-8")
    is_agent_md = _detect_agent_md(input_path, content)

    if convert or not is_agent_md:
        content = await _convert_to_agent_md(path, content)
        if content is None:
            raise SystemExit(1)

    result = await _execute_pipeline(input_path, content, params=params)
    _print_summary(result)

    browser = result.get("browser")
    if browser and hasattr(browser, "_daemon"):
        await browser._daemon.stop()

    from cdp import cleanup_isolated
    await cleanup_isolated()


def _detect_agent_md(input_path: Path, content: str) -> bool:
    """Determine whether a file is already in agent.md format."""
    return (
        input_path.suffix == ".agent.md"
        or (content.strip().startswith("---") and "## " in content)
    )


async def _convert_to_agent_md(path: str, content: str) -> str | None:
    """Convert a document to agent.md format.

    Args:
        path: Original file path.
        content: Original file content.

    Returns:
        The converted agent.md text, or None if cancelled/failed.
    """
    logger.info("Converting document to agent.md: %s", path)
    from converter.convert import convert_document
    from converter.validate import confirm_execution, show_draft, validate_agentmd_strict

    agent_md = await convert_document(path)
    show_draft(agent_md)

    is_valid, errors = validate_agentmd_strict(agent_md)
    if not is_valid:
        logger.error("Generated agent.md has issues: %s", errors)
        return None

    if not confirm_execution():
        return None

    return agent_md


async def _execute_pipeline(input_path: Path, content: str, params: dict | None = None) -> dict:
    """Parse and execute a pipeline.

    Args:
        input_path: Path object for the input file.
        content: agent.md text content.
        params: CLI-injected parameters.

    Returns:
        Dict containing parsed, ctx, browser, daemon, elapsed.
    """
    from api.service import PipelineService
    from compiler.parser import inject_params_to_frontmatter

    _start_time = time.time()

    # Inject params into frontmatter (so goal steps can use them)
    content = inject_params_to_frontmatter(content, params)

    parsed, resolved_steps = PipelineService.prepare_steps(content, agent_md_path=input_path)

    # ── Validate required params ──
    required = parsed.frontmatter.get("required_params", [])
    if isinstance(required, list) and required:
        if not params:
            logger.error("Missing required params: %s. Pass them with -D key=value", ", ".join(required))
            raise SystemExit(1)
        missing = [p for p in required if p not in params]
        if missing:
            logger.error("Missing required params: %s. Pass them with -D key=value", ", ".join(missing))
            raise SystemExit(1)

    # Inject params into goal step descriptions
    if params:
        for step in resolved_steps:
            if step.get("is_goal"):
                desc = step.get("goal_description", "") or step.get("description", "")
                extras = " | ".join(f"{k}={v}" for k, v in params.items())
                step["goal_description"] = f"{desc} (args: {extras})"

    if not parsed.steps:
        logger.error("No steps found in agent.md")
        raise SystemExit(1)

    logger.info("\nPipeline: %s", parsed.name)
    logger.info("Steps:    %d", len(parsed.steps))
    logger.info("Steps:    %s", " → ".join(s.name for s in parsed.steps))

    for step_data in resolved_steps:
        if step_data.get("handler") is not None:
            logger.info("  \u2713 %s \u2192 static handler", step_data["name"])
        elif step_data.get("is_goal"):
            logger.info("  \u2726 %s \u2192 Agent goal: %s", step_data["name"], step_data.get("description", "")[:60])
        elif step_data.get("browser_ops"):
            logger.info("  \u25cf %s \u2192 browser ops (%d operations)", step_data["name"], len(step_data["browser_ops"]))
        else:
            logger.info("  ? %s \u2192 needs LLM-generated handler", step_data["name"])

    try:
        from cdp import discover_ws_url
        from cdp.daemon import CDPDaemon
        from cdp.helpers import CDPHelpers

        logger.info("\nConnecting to Chrome...")
        ws_url = await discover_ws_url()
        logger.info("  Chrome WS URL: %s...", ws_url[:60])

        daemon = CDPDaemon(ws_url)
        await daemon.start()
        await daemon.attach_first_page()
        await daemon.enable_default_domains()

        browser = CDPHelpers(daemon)
        logger.info("  Chrome connected\n")
    except Exception as e:
        logger.warning("  Cannot connect to Chrome (%s), running in headless mode\n", e)
        # Check if any steps need browser capabilities
        for step_data in resolved_steps:
            if step_data.get("browser_ops") or step_data.get("is_goal"):
                logger.warning("  \u26a0 Step '%s' needs a browser but Chrome is unavailable — execution will fail", step_data.get("name", "?"))
        browser = None
        ws_url = ""
        daemon = None

    from engine._lifecycle.guardian import create_guardian_from_frontmatter
    guardian = create_guardian_from_frontmatter(parsed.frontmatter)
    if guardian.approval_steps:
        logger.info("  Guardian enabled: approval steps=%s", guardian.approval_steps)

    ctx = await run_pipeline(
        pipeline_name=parsed.name,
        steps=resolved_steps,
        cdp_helpers=browser,
        agent_md_path=input_path,
        frontmatter=parsed.frontmatter,
        guardian=guardian,
    )

    return {
        "parsed": parsed,
        "ctx": ctx,
        "browser": browser,
        "daemon": daemon,
        "elapsed": time.time() - _start_time,
    }


def _print_summary(result: dict) -> None:
    """Print a summary of execution results.

    Args:
        result: The result dict from _execute_pipeline.
    """
    parsed = result["parsed"]
    ctx = result["ctx"]
    status = "completed" if not ctx.errors else "failed"

    logger.info("\nExecution complete: %s", status)
    if ctx.errors:
        logger.error("Errors (%d):", len(ctx.errors))
        for err in ctx.errors:
            logger.error("  - %s", err)

    elapsed = result.get("elapsed", 0)
    elapsed_str = f"{elapsed:.1f}s" if elapsed < 120 else f"{elapsed / 60:.1f}m"

    print()
    print("=" * 50)
    print(f"  Pipeline: {parsed.name}")
    print(f"  Status:   {status}")
    print(f"  Elapsed:  {elapsed_str}")
    print(f"  Steps:    {len(parsed.steps)}")
    print(f"  Run ID:   {ctx.run_id}")
    print(f"  Workspace: data/workspaces/{parsed.name}/")
    if ctx.errors:
        for err in ctx.errors:
            print(f"  \u2717 {err}")
    print("=" * 50)
    print()
