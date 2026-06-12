"""Agent integration — run goal steps via browser-use Agent.

Provides two entry points:
- run_goal_step() — goal_run tool backend (browser-use Agent)
- start_chat_agent() — chat mode conversation_loop entry
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


def _create_agent_tools(
    registry_tools: list,
    frontmatter: dict | None = None,
):
    """Create a browser-use Tools instance filtered by frontmatter.

    Args:
        registry_tools: List of BaseTool classes from ToolRegistry.
        frontmatter: Optional pipeline frontmatter with ``tools`` allow-list.

    Returns:
        A ``browser_use.Tools`` instance with registered tools.
    """
    from browser_use import Tools

    tools = Tools()
    allowed: set[str] | None = None
    if frontmatter and "tools" in frontmatter:
        allowed = set(frontmatter["tools"])

    for tool_cls in registry_tools:
        if not getattr(tool_cls, "agent_compatible", True):
            continue
        if allowed is not None and tool_cls.name not in allowed:
            continue
        _register_single_tool(tools, tool_cls)

    return tools


def _build_action_for_callable(func, param_defs: list[str], doc_str: str):
    """Build an async action with explicit parameters (no **kwargs).

    browser-use v0.12.9 rejects ``**kwargs`` in action function signatures,
    so we create a closure accepting only the named parameters the tool needs.

    Args:
        func: The callable to wrap.
        param_defs: List of parameter definitions (e.g. ``["browser", "url=str"]``).
        doc_str: Documentation string for the action.

    Returns:
        An async function with explicit parameter names.
    """
    param_names = [p.split(":")[0].split("=")[0].strip() for p in param_defs]
    call_args = ", ".join(f"{n}={n}" for n in param_names)
    code = (
        f"async def action_func({', '.join(param_defs)}):\n"
        f"    try:\n"
        f"        result = await func({call_args})\n"
        f"        return str(result) if result is not None else 'done'\n"
        f"    except Exception as exc:\n"
        f"        return f'Error: {{exc}}'\n"
    )
    # NOTE: exec() is safe here — inputs come from inspect.signature only
    namespace = {"func": func}
    exec(code, namespace)
    action_func = namespace["action_func"]
    action_func.__doc__ = doc_str
    return action_func


def _inspect_execute_params(tool_cls) -> list[str]:
    """Extract parameter definitions from a tool's execute method (excluding cls).

    Args:
        tool_cls: A BaseTool subclass.

    Returns:
        List of parameter strings (e.g. ``["browser", "url=str"]``).
    """
    sig = inspect.signature(tool_cls.execute)
    params: list[str] = []
    for name, param in sig.parameters.items():
        if name == "cls":
            continue
        if param.default is inspect.Parameter.empty:
            params.append(name)
        else:
            params.append(f"{name}={repr(param.default)}")
    return params


def _register_single_tool(tools, tool_cls) -> None:
    """Register a single BaseTool subclass in a browser-use Tools instance.

    Args:
        tools: A ``browser_use.Tools`` instance.
        tool_cls: A BaseTool subclass to register.
    """
    name = tool_cls.name
    desc = tool_cls.description or getattr(tool_cls, "llm_hint", "") or f"Tool: {name}"
    returns_doc = getattr(tool_cls, "returns", "") or ""
    doc_str = f"{desc}\nReturns: {returns_doc}" if returns_doc else desc

    param_defs = _inspect_execute_params(tool_cls)

    async def _invoke(*args, **kwargs):
        return await tool_cls.execute(*args, **kwargs)

    _action = _build_action_for_callable(_invoke, param_defs, doc_str)
    tools.registry.action(name or tool_cls.__name__)(_action)


async def run_goal_step(
    step_def: dict,
    cdp_helpers: object | None,
    step_dir: Path,
    pipeline_name: str,
    frontmatter: dict | None = None,
    source_text: str = "",
    tools_dir: Path | None = None,
    ws_url: str = "",
    agent_md_path: Path | None = None,
    system_prompt: str = "",
) -> dict:
    """Execute a goal step via browser-use Agent and write results.

    Args:
        step_def: Step definition dict with ``goal_description`` or ``description``.
        cdp_helpers: CDP helpers instance for browser access.
        step_dir: Step output directory for artifacts.
        pipeline_name: Pipeline name for workspace management.
        frontmatter: Optional pipeline frontmatter.
        source_text: Source agent.md text for diff/guard flow.
        tools_dir: Directory containing tool modules.
        ws_url: WebSocket URL for CDP connection. If empty, will try to discover.
        agent_md_path: Path to agent.md for writing learned ops.
        system_prompt: Optional system prompt extension.

    Returns:
        Dict with ``status``, ``learned_ops``, ``saved_version``,
        ``agent_history_path``, ``error_message``, ``error_code``.
    """
    from browser_use import Agent, Browser

    description = step_def.get("goal_description", "")
    if not description:
        description = step_def.get("description", "")
    if not description:
        description = step_def.get("name", "")

    # Prepare result container
    result: dict = {
        "status": "error",
        "learned_ops": [],
        "saved_version": None,
        "agent_history_path": None,
        "error_message": "",
        "error_code": "",
    }

    bu_browser: Browser | None = None
    agent: Agent | None = None

    try:
        # Create LLM from environment configuration
        llm = _create_llm()

        # Discover CDP WebSocket URL if not provided
        if not ws_url:
            ws_url = _discover_ws_url()

        bu_browser = Browser(cdp_url=ws_url, headless=False)

        # Register tools
        from tools.registry import ToolRegistry

        registry_tools = ToolRegistry.list_all()
        tools = _create_agent_tools(registry_tools, frontmatter)

        # Load workspace helpers
        _load_workspace_helpers(tools, pipeline_name)

        agent = Agent(
            task=description,
            llm=llm,
            browser=bu_browser,
            tools=tools,
            extend_system_message=system_prompt if system_prompt else None,
        )

        logger.info("goal agent start: %s", description[:80])
        await agent.run()

        _write_agent_history(agent, step_dir)
        result["agent_history_path"] = str(step_dir / "agent_history.json")

        if hasattr(agent, "history") and agent.history.is_done():
            logger.info("goal agent done (success)")
            result["saved_version"] = _get_latest_saved_version(pipeline_name)
            result["status"] = "success"

            # Extract learned ops from agent history
            model_actions = agent.history.model_actions()
            if model_actions:
                result["learned_ops"] = _extract_learned_ops(agent, model_actions)
        else:
            logger.warning("goal agent done (incomplete/failed)")
            _save_partial_ops(agent, pipeline_name, "latest")
            result["status"] = "partial"

            model_actions = agent.history.model_actions()
            if model_actions:
                result["learned_ops"] = _extract_learned_ops(agent, model_actions)

    except Exception as e:
        logger.error("goal agent error: %s", e)
        result["status"] = "error"
        result["error_message"] = str(e)
        result["error_code"] = "RUNTIME_ERROR"
        try:
            if agent and hasattr(agent, "history"):
                _write_agent_history(agent, step_dir, partial=True)
                result["agent_history_path"] = str(step_dir / "agent_history_partial.json")
        except Exception as write_err:
            logger.exception("failed to write partial agent history: %s", write_err)
        try:
            _save_partial_ops(agent, pipeline_name, "error")
        except Exception as save_err:
            logger.exception("partial-save (error) failed: %s", save_err)

    finally:
        # Cleanup browser highlights
        await _cleanup_agent_highlights(bu_browser)

    return result


def _discover_ws_url() -> str:
    """Discover CDP WebSocket URL.

    In a production setup this would query the Chrome DevTools Protocol
    endpoint. Stub returns a placeholder.
    """
    # Try LBU_WS_URL env var first, then fall through to discovery
    import os
    ws_url = os.environ.get("LBU_WS_URL", "")
    if ws_url:
        return ws_url
    logger.warning("No LBU_WS_URL set and no daemon.chrome module — using placeholder")
    return "ws://localhost:9222/devtools/browser"


def _create_llm():
    """Create a browser-use LLM instance from environment configuration.

    Respects ``LBU_LLM_PROVIDER``, ``LBU_LLM_MODEL``, ``LBU_LLM_API_KEY``,
    and ``LBU_LLM_BASE_URL`` environment variables.

    Falls back to a default OpenAI GPT-4o configuration.
    """
    import os

    provider = os.environ.get("LBU_LLM_PROVIDER", "openai").lower()
    model = os.environ.get("LBU_LLM_MODEL", "gpt-4o")
    api_key = os.environ.get("LBU_LLM_API_KEY", "")
    base_url = os.environ.get("LBU_LLM_BASE_URL", "")

    if provider == "openai":
        from browser_use.llm import LLM

        kwargs: dict = {"model": model, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return LLM(**kwargs)
    elif provider == "anthropic":
        from browser_use.llm import LLM

        kwargs = {"model": model, "api_key": api_key, "provider": "anthropic"}
        if base_url:
            kwargs["base_url"] = base_url
        return LLM(**kwargs)
    else:
        from browser_use.llm import LLM

        return LLM(model=model, api_key=api_key)


def _write_agent_history(agent, step_dir: Path, partial: bool = False) -> None:
    """Write agent execution history to a JSON file in the step directory.

    Args:
        agent: The browser-use Agent instance.
        step_dir: Directory to write the history file into.
        partial: If True, writes to ``agent_history_partial.json``.
    """
    import json as _json

    filename = "agent_history_partial.json" if partial else "agent_history.json"
    history_path = step_dir / filename

    total_steps = 0
    is_done = False
    model_actions = []
    try:
        if hasattr(agent, "history"):
            model_actions = agent.history.model_actions() or []
            total_steps = len(model_actions)
            is_done = agent.history.is_done()
    except Exception as e:
        logger.exception("Failed to get agent history: %s", e)

    summary = ""
    try:
        if hasattr(agent, "history"):
            summary = str(agent.history)[:2000]
    except Exception as e:
        logger.exception("Failed to get agent history summary: %s", e)

    data = {
        "summary": summary,
        "is_done": is_done,
        "total_steps": total_steps,
        "model_actions": len(model_actions),
    }
    with open(history_path, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)

    logger.debug("wrote agent history to %s (%d actions)", history_path, total_steps)


def _get_latest_saved_version(pipeline_name: str) -> str | None:
    """Get the latest saved version for a pipeline.

    Args:
        pipeline_name: Name of the pipeline.

    Returns:
        Version string or None.
    """
    try:
        from workspace.manager import WorkspaceManager

        wm = WorkspaceManager(pipeline_name)
        versions_dir = wm.versions_dir
        latest_file = versions_dir / "LATEST"
        if latest_file.exists():
            return latest_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.debug("Could not get latest version for '%s': %s", pipeline_name, e)
    return None


def _load_workspace_helpers(tools, pipeline_name: str) -> None:
    """Load workspace helper functions and register them as browser-use tools.

    Looks for ``helpers.py`` in the workspace root and registers all
    callable functions (except those starting with ``_`` or ``_PH-``)
    as browser-use actions.

    Args:
        tools: A ``browser_use.Tools`` instance.
        pipeline_name: Pipeline name for workspace path resolution.
    """
    from workspace.manager import WorkspaceManager

    wm = WorkspaceManager(pipeline_name)
    helpers_path = wm.root / "helpers.py"
    if not helpers_path.exists():
        return

    try:
        module_name = f"__workspace_helpers_{pipeline_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, str(helpers_path))
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        from tools.registry import ToolRegistry

        registry_names = {t.name for t in ToolRegistry.list_all() if t.name}

        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if not callable(obj):
                continue
            if name in registry_names:
                logger.debug("workspace helper '%s' skipped (conflicts with ToolRegistry)", name)
                continue
            if name.startswith("_PH-"):
                logger.debug(
                    "workspace helper '%s' skipped (_PH- prefix reserved for lifecycle tools)",
                    name,
                )
                continue

            try:
                sig = inspect.signature(obj)
                param_defs: list[str] = []
                for pname, param in sig.parameters.items():
                    if param.default is inspect.Parameter.empty:
                        param_defs.append(pname)
                    else:
                        param_defs.append(f"{pname}={repr(param.default)}")
            except (ValueError, TypeError):
                param_defs = ["browser"]

            doc = obj.__doc__ or f"Workspace helper: {name}"
            _action = _build_action_for_callable(obj, param_defs, doc)
            tools.registry.action(name)(_action)
            logger.debug("workspace helper loaded: %s", name)
    except Exception as e:
        logger.warning("Failed to load workspace helpers for '%s': %s", pipeline_name, e)


async def _cleanup_agent_highlights(agent_browser: object | None) -> None:
    """Remove browser-use Agent highlight elements from the page.

    Args:
        agent_browser: A ``browser_use.Browser`` instance (or similar).
    """
    try:
        if agent_browser and hasattr(agent_browser, "_cdp_client"):
            await agent_browser._cdp_client.send.Runtime.evaluate(
                params={
                    "expression": (
                        "document.querySelectorAll('.browser-use-highlight')"
                        ".forEach(el => el.remove())"
                    ),
                    "returnByValue": True,
                }
            )
    except Exception as e:
        logger.exception("Failed to clean up agent highlights: %s", e)


def _extract_learned_ops(agent, model_actions: list) -> list[dict]:
    """Extract learned operations from agent model actions.

    This is a stub — a full implementation would call the compiler module
    to convert model actions to pipeline operation format.

    Args:
        agent: The browser-use Agent instance.
        model_actions: List of model action dicts from agent history.

    Returns:
        List of operation dicts in pipeline format.
    """
    # Stub conversion — each model action becomes a basic browser op record
    ops: list[dict] = []
    for action in model_actions:
        action_data = action if isinstance(action, dict) else {}
        op_type = _map_action_type(action_data.get("action", ""))
        op = {"type": op_type}
        if "url" in action_data:
            op["value"] = action_data["url"]
        if "selector" in action_data:
            op["selector"] = action_data["selector"]
        if "text" in action_data:
            op["value"] = action_data["text"]
        ops.append(op)
    return ops


def _map_action_type(action_type: str) -> str:
    """Map browser-use action types to pipeline browser op types."""
    mapping = {
        "navigate": "goto",
        "click": "click",
        "input_text": "fill",
        "fill": "fill",
        "select_option": "click",
        "scroll": "wait",
        "wait": "wait",
        "extract_content": "get_html",
        "done": "snapshot",
    }
    return mapping.get(action_type, action_type)


def _save_partial_ops(
    agent: object,
    pipeline_name: str,
    version_tag: str = "partial",
) -> None:
    """Save partial agent execution ops as an intermediate version.

    Args:
        agent: The browser-use Agent instance.
        pipeline_name: Pipeline name.
        version_tag: Version tag for the partial save (e.g. 'partial', 'error').
    """
    from workspace.manager import WorkspaceManager

    try:
        if not hasattr(agent, "history"):
            return
        model_actions = agent.history.model_actions()  # type: ignore[union-attr]
        if not model_actions:
            return

        ops = _extract_learned_ops(agent, model_actions)
        if not ops:
            return

        lines = ["browser:"]
        for op in ops:
            op_type = op.get("type", "")
            parts = [f"    - {op_type}:"]
            for k, v in op.items():
                if k == "type":
                    continue
                parts.append(f"        {k}: {v}")
            lines.append("\n".join(parts))

        text = "\n".join(lines)

        wm = WorkspaceManager(pipeline_name)
        partial_dir = wm.root / "partial"
        partial_dir.mkdir(parents=True, exist_ok=True)
        (partial_dir / f"{version_tag}.agent.md").write_text(text, encoding="utf-8")
        logger.info(
            "partial-save: %d ops saved for pipeline '%s' (%s)",
            len(ops),
            pipeline_name,
            version_tag,
        )
    except Exception as e:
        logger.warning("partial-save failed: %s", e)


# ── Chat mode entry ──────────────────────────────────────────────────


async def start_chat_agent(
    *,
    user_message: str,
    cdp_helpers: object,
    pipeline_name: str = "",
    tools_dir: Path | None = None,
    messages: list[dict] | None = None,
    llm_call=None,
    budget: object | None = None,
) -> dict:
    """Start a chat-mode conversation_loop with the given user message.

    This is the chat mode entry point — wraps run_conversation_loop
    with default configuration suitable for interactive chat.

    Args:
        user_message: The user's text input.
        cdp_helpers: CDPHelpers instance for browser operations.
        pipeline_name: Pipeline name for goal_run context.
        tools_dir: Directory containing tool modules.
        messages: Pre-existing conversation messages (for resume).
        llm_call: Async callable(messages, tools) -> LLMResponse.
        budget: Pre-existing IterationBudget (for resume).

    Returns:
        Dict with response, status, messages, budget.
    """
    from engine._harness.conversation_loop import run_conversation_loop
    from engine._harness.tools import get_all_tools
    from prompts._loader import load_prompt

    if messages is None:
        messages = []

    messages.append({"role": "user", "content": user_message})

    system_prompt = load_prompt("chat/system")

    if llm_call is None:
        llm_call = _create_chat_llm_call()

    result = await run_conversation_loop(
        llm_call=llm_call,
        system_prompt=system_prompt,
        messages=messages,
        tools=get_all_tools(),
        cdp_helpers=cdp_helpers,
        tools_dir=tools_dir,
        pipeline_name=pipeline_name,
        budget=budget,
    )

    return {
        "response": result.final_response,
        "status": "completed" if not result.interrupted else "cancelled",
        "messages": result.messages,
        "budget": result.budget.to_dict(),
        "turn_count": result.turn_count,
        "duration_ms": result.duration_ms,
    }


def _create_chat_llm_call():
    """Create a callable for LLM API calls compatible with conversation_loop.

    Returns an async function that takes (messages, tools) and returns
    an object with .content and .tool_calls attributes.
    """
    from utils.browser import create_llm
    from browser_use.llm.messages import UserMessage, SystemMessage, AssistantMessage

    llm = create_llm()

    async def _call(messages: list[dict], tools: list[dict]) -> object:
        converted: list = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AssistantMessage(content=content))
            else:
                converted.append(UserMessage(content=content))

        kwargs = {"messages": converted}
        if tools:
            kwargs["tools"] = tools
        response = llm.invoke(**kwargs)
        return response

    return _call
