"""Tool debugging CLI commands: prompt preview, dry-run, _PH- lifecycle testing."""

from __future__ import annotations

import sys
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


async def _cmd_tool_prompt(pipeline_path: str, step_key: str | None = None) -> None:
    """Preview subagent goal templates for all _PH- tool steps (no LLM call).

    Args:
        pipeline_path: Path to the pipeline.yaml file.
        step_key: Optional step key to filter on.
    """
    from api.service import PipelineService

    path = Path(pipeline_path)
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    content = path.read_text(encoding="utf-8")
    parsed, steps_data = PipelineService.prepare_steps(content, pipeline_path=path)

    tool_steps = [s for s in steps_data if s.get("tool_name", "").startswith("_PH-")]
    if not tool_steps:
        logger.info("No _PH- tool steps found")
        return

    matched = False
    print(f"\n\u2550\u2550\u2550 Tool Generation Prompt Preview \u2014 {path.name} \u2550\u2550\u2550\n")

    for step in tool_steps:
        step_key_val = step.get("key", "?")
        if step_key and step_key != step_key_val:
            continue

        matched = True

        tool_name = step.get("tool_name", "")
        real_name = tool_name[4:] if tool_name.startswith("_PH-") else tool_name
        desc = step.get("description", "")
        params = step.get("params", {})
        output_files = step.get("output", [])

        print(f"\u25a0 Step: {step.get('name', '?')} (key={step_key_val})")
        print(f"  tool: {tool_name} \u2192 {real_name}")
        print(f"  desc: {desc[:100]}")
        print(f"  input: {step.get('input', {})}")
        print(f"  output: {output_files}")
        print(f"  params: {params}")

        box_draw = "\u2500"
        print(f"\n  {box_draw * 60}")
        print(f"  Subagent Goal Template for: {tool_name}")
        print(f"  {box_draw}")
        print(f"  Generate a Python tool function named '{real_name}'.")
        print(f"  Description: {desc}")
        print(f"  Parameters: {params}")
        print(f"  Required output files: {output_files}")
        print(f"  Function signature: def {real_name}(input_files: dict[str, str], output_dir: str, **params) -> None")
        print(f"  Write code to: tools_dir/{tool_name}.py")
        print(f"  Only import from whitelist (stdlib + bundled_deps from runtime-whitelist.json)")
        print(f"  {box_draw * 60}\n")

    if not matched and step_key:
        logger.error("Step key '%s' not found (available: %s)", step_key, [s.get("key") for s in tool_steps])
        sys.exit(1)


async def _cmd_tool_dry_run(pipeline_path: str) -> None:
    """Compile pipeline.yaml without executing — display the full DAG and step info.

    Args:
        pipeline_path: Path to the pipeline.yaml file.
    """
    from api.service import PipelineService
    from compiler.graph import build_graph, get_execution_order, validate_file_refs

    path = Path(pipeline_path)
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    from engine.runner import _step_type
    content = path.read_text(encoding="utf-8")
    parsed, steps_data = PipelineService.prepare_steps(content, pipeline_path=path)

    print(f"\n\u2550\u2550\u2550 Pipeline Dry-Run: {parsed.name} \u2550\u2550\u2550\n")

    dag = build_graph(parsed.steps)
    execution_order = get_execution_order(dag)

    print("\u25a0 Basic Info")
    print(f"  Name:       {parsed.name}")
    print(f"  Description: {parsed.description or '(none)'}")
    print(f"  Steps:      {len(parsed.steps)}")
    print(f"  DAG Nodes:  {len(dag['nodes'])}")
    print(f"  DAG Edges:  {len(dag['edges'])}")
    arrow = " \u2192 "
    print(f"  Execution:  {arrow.join(execution_order)}\n")

    print("\u25a0 Step Details")
    for i, step in enumerate(steps_data):
        step_type = _step_type(step)
        icon = {"browser": "\u25cf", "goal": "\u2726", "tool": "\u25c6"}.get(step_type, "?")

        tool_info = ""
        if step.get("tool_name"):
            tool_name = step["tool_name"]
            if tool_name.startswith("_PH-"):
                tool_info = f" [_PH-generated] \u2192 {tool_name[4:]}"
            else:
                tool_info = f" [static tool] {tool_name}"

        print(f"\n  [{i + 1}/{len(steps_data)}] {icon} {step.get('name', '?')} ({step_type}){tool_info}")
        if step.get("description"):
            print(f"      desc: {step['description'][:120]}")
        if step.get("depends_on"):
            print(f"      depends: {step['depends_on']}")
        if step.get("browser_ops"):
            print(f"      browser ops ({len(step['browser_ops'])}): {[op.get('type', '?') for op in step['browser_ops']]}")
        if step.get("input"):
            print(f"      input: {step['input']}")
        if step.get("output"):
            print(f"      output: {step['output']}")

    # File reference validation
    print("\n\u25a0 File Reference Validation")
    try:
        validate_file_refs(parsed.steps)
        print("  \u2713 Passed")
    except ValueError as e:
        print(f"  \u2717 {e}")

    print(f"\n\u25a0 Registered Tools ({len(parsed.steps)} steps)")
    for step in steps_data:
        tn = step.get("tool_name")
        if tn:
            print(f"  - {tn}")


async def _cmd_tool_run_ph(pipeline_path: str, step_key: str, llm_response_path: str | None = None) -> None:
    """Single-step execute a _PH- tool (requires pre-generated code).

    Args:
        pipeline_path: Path to the pipeline.yaml file.
        step_key: Step key or name to run.
        llm_response_path: Ignored (kept for backward compat). Code generation
            is now handled by the ph-tool-generation skill.
    """
    from api.service import PipelineService
    from engine._lifecycle.tool_runner import ToolRunner
    from engine._lifecycle.guardian import Guardian
    from engine.events import EventSink
    from workspace.manager import WorkspaceManager

    path = Path(pipeline_path)
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    content = path.read_text(encoding="utf-8")
    parsed, steps_data = PipelineService.prepare_steps(content, pipeline_path=path)

    # Find the target step
    target_step = None
    for s in steps_data:
        if s.get("key") == step_key or s.get("name") == step_key:
            target_step = s
            break

    if not target_step:
        logger.error("Step not found: %s (available: %s)", step_key, [s.get("key") for s in steps_data])
        sys.exit(1)

    tool_name = target_step.get("tool_name", "")
    if not tool_name.startswith("_PH-"):
        logger.error("Step %s is not a _PH- tool step (tool_name=%s)", step_key, tool_name)
        sys.exit(1)

    wm = WorkspaceManager(parsed.name)
    wm.ensure_workspace()
    run_dir = wm.create_run()
    step_dir = run_dir / step_key
    step_dir.mkdir(parents=True, exist_ok=True)
    events = EventSink(run_dir)

    guardian = Guardian()
    runner = ToolRunner(wm.tools_dir, parsed.name, guardian)

    # Collect input files
    from engine.runner import _collect_input_files as collect_input_files
    input_files = collect_input_files(target_step.get("input", {}), run_dir)

    print("\n\u2550\u2550\u2550 _PH- Tool Execution Test \u2550\u2550\u2550\n")
    print(f"  Pipeline: {parsed.name}")
    print(f"  Step:     {target_step.get('name', '?')}")
    print(f"  Key:      {step_key}")
    print(f"  Tool:     {tool_name} \u2192 {tool_name[4:]}")
    print(f"  Input:    {input_files}")
    print(f"  Output:   {target_step.get('output', [])}")
    print(f"  Run Dir:  {run_dir}\n")

    # Step 1: Check tool exists
    if not runner.tool_exists(tool_name):
        print("  \u2717 Tool file not found. Use ph-tool-generation skill to generate code first.")
        events.close()
        sys.exit(1)

    # Step 2: Execute tool
    print("  \u25b6 Executing tool...\n")
    result = await runner.load_and_call(
        tool_name,
        input_files,
        str(step_dir),
        func_name=runner.strip_ph_prefix(tool_name),
        **target_step.get("params", {}),
    )

    print("\n  \u25a0 Execution Result:")
    for k, v in result.items():
        print(f"    {k}: {v}")

    if not result.get("ok"):
        events.close()
        return

    # Step 3: Validate output
    guard_result = guardian.validate_output(str(step_dir), target_step.get("output", []))
    print("\n  \u25a0 Guardian Result:")
    for k, v in guard_result.items():
        print(f"    {k}: {v}")

    if not guard_result.get("ok"):
        events.close()
        return

    # Step 4: Rename
    rename_result = runner.rename_ph_file(tool_name)
    print("\n  \u25a0 Rename Result:")
    for k, v in rename_result.items():
        print(f"    {k}: {v}")

    if rename_result.get("ok"):
        refs_result = runner.update_pipeline_refs(
            tool_name, runner.strip_ph_prefix(tool_name), path,
        )
        print("\n  \u25a0 Pipeline Refs Update:")
        for k, v in refs_result.items():
            print(f"    {k}: {v}")

    # Check generated files
    ph_path = wm.tools_dir / f"{tool_name}.py"
    real_path = wm.tools_dir / f"{tool_name[4:]}.py"
    ok_mark = "\u2713"
    fail_mark = "\u2717"
    print("  \u25a0 Generated Files:")
    print(f"    _PH- file:   {ph_path} {ok_mark + ' exists' if ph_path.exists() else fail_mark + ' not found'}")
    print(f"    Real file:   {real_path} {ok_mark + ' exists' if real_path.exists() else fail_mark + ' not found'}")

    events.close()


# dispatch handler registration table
_HANDLERS = {
    "prompt": _cmd_tool_prompt,
    "dry-run": _cmd_tool_dry_run,
    "run-ph": _cmd_tool_run_ph,
}


async def dispatch(cmd: str, **kwargs) -> None:
    """Dispatch a tool subcommand.

    Args:
        cmd: Subcommand name (prompt, dry-run, run-ph).
        **kwargs: Arguments specific to the subcommand.
    """
    handler = _HANDLERS.get(cmd)
    if handler is None:
        logger.error("Unknown tool subcommand: %s (available: %s)", cmd, ", ".join(_HANDLERS))
        sys.exit(1)
    await handler(**kwargs)
