"""Executor — three step executors for browser, tool, and goal step types.

Each executor returns a result dict in a consistent file-contract format:
{status, duration_ms, ops/agent_result, error, ...}
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
from functools import partial
from pathlib import Path

from utils.logging import get_logger

from engine._lifecycle.compensation import CompensationRegistry

logger = get_logger(__name__)

ERROR_CODES: dict[str, str] = {
    "SYNTAX_ERROR": "Tool code compile/syntax failure",
    "RUNTIME_ERROR": "Tool execution runtime exception",
    "TIMEOUT_ERROR": "Tool execution timeout",
    "OUTPUT_ERROR": "Output file missing or empty",
    "INPUT_ERROR": "Input file not found or unreadable",
    "BROWSER_ERROR": "Browser operation failed",
    "BROWSER_UNAVAILABLE": "Browser not available",
    "GUARDIAN_ERROR": "Guardian validation failed",
    "PATH_ERROR": "Path security check failed",
    "LLM_ERROR": "LLM tool code generation failed",
}

SENSITIVE_KEYS: frozenset = frozenset({
    "text", "value", "credential", "password", "secret", "token", "key", "api_key",
})

_SENSITIVE_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9_])("
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    r")(\s*[:=]\s*)"
    r"([^\s,\'\"\]}\)]+)",
)

_CREDENTIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})"), "sk-***"),
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}"), r"\1***"),
    (re.compile(r"(-----BEGIN\s.*?KEY-----)"), "***KEY BLOCK***"),
]

DEFAULT_OP_TIMEOUT = 30


# ── Masking / sanitizing ──


def mask_sensitive_patterns(text: str) -> str:
    """Mask sensitive key=value patterns and credential strings in text.

    Args:
        text: Input string that may contain sensitive data.

    Returns:
        Masked string with sensitive values replaced by ``***``.
    """

    def _replacer(m: re.Match) -> str:
        key = m.group(1).lower()
        sep = m.group(2)
        value = m.group(3)
        if key in SENSITIVE_KEYS and len(value) > 2:
            return f"{m.group(1)}{sep}***"
        return m.group(0)

    result = _SENSITIVE_PATTERN.sub(_replacer, text)
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_result(data, sensitive_keys: frozenset = SENSITIVE_KEYS):
    """Recursively sanitize sensitive values in a nested data structure.

    Args:
        data: The data to sanitize (dict, list, str, or other).
        sensitive_keys: Set of lowercase keys whose values should be masked.

    Returns:
        Sanitized copy of the data.
    """
    from params.manager import ParamRef

    if isinstance(data, ParamRef):
        return str(data)
    if isinstance(data, dict):
        return {
            k: "***" if (isinstance(k, str) and k.lower() in sensitive_keys)
            else sanitize_result(v, sensitive_keys)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [sanitize_result(item, sensitive_keys) for item in data]
    if isinstance(data, str):
        return mask_sensitive_patterns(data)
    return data


# ── Browser step executor ──


async def execute_browser_step(
    step: dict,
    cdp_helpers: object,
    step_dir: Path,
    run_dir: Path,
) -> dict:
    """Execute a browser step: run ops via CDP, write step.json + artifacts.

    Args:
        step: Step definition dict containing ``browser_ops`` list.
        cdp_helpers: CDPHelpers instance for browser operations.
        step_dir: Directory for step artifacts.
        run_dir: Run directory (unused here, kept for API consistency).

    Returns:
        Result dict with status, ops, duration_ms, error, compensation_history.
    """
    ops = step.get("browser_ops", [])
    registry = CompensationRegistry()
    result: dict = {
        "step": step.get("name", ""),
        "type": "browser",
        "status": "completed",
        "duration_ms": 0,
        "ops": [],
        "params": step.get("params", {}),
        "final_url": "",
        "error": {"code": None, "message": None, "stack": None},
    }

    start = time.time()
    for op in ops:
        op_start = time.time()
        op_type = op.get("type", "")
        value = op.get("value", "")
        op_record: dict = {"type": op_type, "ok": True, "duration_ms": 0}
        op_params = {k: v for k, v in op.items() if k != "type"}
        registry.register_op(op_type, op_params)

        try:
            async with asyncio.timeout(DEFAULT_OP_TIMEOUT):
                if op_type == "goto" and value:
                    op_record["url"] = value
                    await cdp_helpers.goto_url(value)  # type: ignore[union-attr]
                    result["final_url"] = value

                elif op_type == "click":
                    selector = value or op.get("selector", "")
                    if not selector:
                        raise ValueError("click op missing selector")
                    op_record["selector"] = selector
                    await cdp_helpers.click_selector(selector)  # type: ignore[union-attr]

                elif op_type == "fill":
                    selector = op.get("selector", "")
                    text = value
                    op_record["selector"] = selector
                    op_record["text"] = text
                    await cdp_helpers.fill_input(selector, text)  # type: ignore[union-attr]

                elif op_type == "wait":
                    await asyncio.sleep(float(value) if value else 1.0)

                elif op_type == "snapshot":
                    ts = int(time.time())
                    png_path = step_dir / f"screenshot_{ts}.png"
                    snapshot = await cdp_helpers.capture_snapshot()  # type: ignore[union-attr]
                    png_data = snapshot.get("screenshot_base64", "")
                    if png_data:
                        import base64
                        png_path.write_bytes(base64.b64decode(png_data))
                    html_data = snapshot.get("html", "")
                    if html_data:
                        html_path = step_dir / "page.html"
                        html_path.write_text(html_data, encoding="utf-8")

                elif op_type == "get_html":
                    html = await cdp_helpers.get_page_html()  # type: ignore[union-attr]
                    html_path = step_dir / "page.html"
                    html_path.write_text(html, encoding="utf-8")

                elif op_type == "wait_for_network":
                    await cdp_helpers.wait_for_network_idle()  # type: ignore[union-attr]

                elif op_type == "eval":
                    code_str = op.get("code", op.get("js", op.get("value", "")))
                    check_raw = op.get("check")
                    fail_msg = op.get("fail_message", "")
                    op_record["code"] = code_str[:200]
                    eval_result = await cdp_helpers.js(code_str)  # type: ignore[union-attr]
                    op_record["result"] = eval_result
                    if check_raw is not None:
                        expected = (
                            True if check_raw == "true"
                            else False if check_raw == "false"
                            else check_raw
                        )
                        if eval_result != expected:
                            msg = fail_msg or f"Check failed: eval expected {expected!r}, got {eval_result!r}"
                            raise ValueError(msg)

        except TimeoutError:
            op_record["ok"] = False
            op_record["error"] = f"Operation timeout ({DEFAULT_OP_TIMEOUT}s)"
            result["status"] = "failed"
            result["error"] = {
                "code": "TIMEOUT_ERROR",
                "message": f"{op_type} operation timed out",
                "stack": None,
            }
            result["ops"].append(op_record)
            result["duration_ms"] = int((time.time() - start) * 1000)
            result["compensation_history"] = registry.to_list()
            result["suggest_rollback"] = registry.suggest_rollback(len(registry._ops) - 1)
            return result

        except Exception as e:
            op_record["ok"] = False
            op_record["error"] = str(e)
            result["status"] = "failed"
            result["error"] = {
                "code": "BROWSER_ERROR",
                "message": str(e),
                "stack": traceback.format_exc(),
            }
            result["ops"].append(op_record)
            result["duration_ms"] = int((time.time() - start) * 1000)
            result["compensation_history"] = registry.to_list()
            result["suggest_rollback"] = registry.suggest_rollback(len(registry._ops) - 1)
            return result

        op_record["duration_ms"] = int((time.time() - op_start) * 1000)
        result["ops"].append(op_record)

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


# ── Tool step executor ──


async def execute_tool_step(
    step: dict,
    tools_dir: Path,
    step_dir: Path,
    run_dir: Path,
    cdp_helpers: object | None = None,
) -> dict:
    """Execute a tool step: import the tool module, call its function, validate output.

    Args:
        step: Step definition dict with ``tool_name``, ``input``, ``output``, ``params``.
        tools_dir: Directory containing tool Python files.
        step_dir: Directory for step artifacts.
        run_dir: Run directory for input file resolution.
        cdp_helpers: Optional CDPHelpers instance for browser-enabled tools.

    Returns:
        Result dict with status, input_files, output_files, duration_ms, error.
    """
    import importlib.util
    import sys

    tool_name = step.get("tool_name", "")
    input_ref = step.get("input", {})
    output_files = step.get("output", [])
    params = step.get("params", {})

    result: dict = {
        "step": step.get("name", ""),
        "type": "tool",
        "tool": tool_name,
        "status": "completed",
        "duration_ms": 0,
        "input_files": {},
        "output_files": [],
        "params": params,
        "error": {"code": None, "message": None, "stack": None},
    }

    start = time.time()

    if not tool_name:
        result["status"] = "failed"
        result["error"] = {"code": "INPUT_ERROR", "message": "tool_name is required", "stack": None}
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    tool_path = tools_dir / f"{tool_name}.py"
    if not tool_path.exists():
        result["status"] = "failed"
        result["error"] = {
            "code": "INPUT_ERROR",
            "message": f"Tool file not found: {tool_path}",
            "stack": None,
        }
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    # Dynamic import of the tool module
    try:
        module_name = f"tools_{tool_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
        if spec is None or spec.loader is None:
            result["status"] = "failed"
            result["error"] = {
                "code": "SYNTAX_ERROR",
                "message": f"Cannot load module: {tool_path}",
                "stack": None,
            }
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        result["status"] = "failed"
        result["error"] = {
            "code": "SYNTAX_ERROR",
            "message": str(e),
            "stack": traceback.format_exc(),
        }
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    # Locate the main function (same name as tool)
    tool_func = getattr(module, tool_name, None)
    if not tool_func:
        result["status"] = "failed"
        result["error"] = {
            "code": "SYNTAX_ERROR",
            "message": f"Function '{tool_name}' not found in {tool_path}",
            "stack": None,
        }
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    # Check CAPABILITIES → inject ToolCDPHelpers if 'browser'
    capabilities = getattr(module, "CAPABILITIES", [])
    tool_cdp_instance = None

    if capabilities:
        for cap in capabilities:
            if cap == "browser":
                if cdp_helpers is None:
                    result["status"] = "failed"
                    result["error"] = {
                        "code": "BROWSER_UNAVAILABLE",
                        "message": f"Tool '{tool_name}' requires browser capability but cdp_helpers is unavailable",
                        "stack": None,
                    }
                    result["duration_ms"] = int((time.time() - start) * 1000)
                    return result
                from utils.tool_cdp import ToolCDPHelpers
                tool_cdp_instance = ToolCDPHelpers(cdp_helpers)
            else:
                logger.warning("Tool '%s' declares unknown capability: %s", tool_name, cap)

    # Resolve input files
    input_files = _resolve_input_files(input_ref, run_dir)
    result["input_files"] = input_files

    # Call the tool function
    try:
        kwargs: dict = {"input_files": input_files, "output_dir": str(step_dir), **params}
        if tool_cdp_instance is not None:
            kwargs["cdp_helpers"] = tool_cdp_instance
        if asyncio.iscoroutinefunction(tool_func):
            await tool_func(**kwargs)
        else:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, partial(tool_func, **kwargs))
    except TimeoutError:
        result["status"] = "failed"
        result["error"] = {
            "code": "TIMEOUT_ERROR",
            "message": "Tool execution timed out",
            "stack": None,
        }
    except Exception as e:
        is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()
        result["status"] = "failed"
        result["error"] = {
            "code": "TIMEOUT_ERROR" if is_timeout else "RUNTIME_ERROR",
            "message": str(e),
            "stack": traceback.format_exc(),
        }
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    # Validate output files exist
    missing = _check_outputs(output_files, step_dir)
    if missing:
        result["status"] = "failed"
        result["error"] = {
            "code": "OUTPUT_ERROR",
            "message": f"Output files missing: {missing}",
            "stack": None,
        }
    else:
        result["output_files"] = [str(step_dir / f) for f in output_files]

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


# ── Goal step executor ──


async def execute_goal_step(
    step_def: dict,
    cdp_helpers: object | None,
    step_dir: Path,
    run_dir: Path,
    tools_dir: Path,
    pipeline_name: str,
    frontmatter: dict | None = None,
    agent_md_path: Path | None = None,
) -> dict:
    """Execute a goal step: call browser-use Agent, write learned_ops.json + agent_history.json.

    Args:
        step_def: Step definition dict with ``goal_description`` or ``description``.
        cdp_helpers: CDPHelpers instance.
        step_dir: Step artifact directory.
        run_dir: Run directory (unused here, for API consistency).
        tools_dir: Directory containing tool modules.
        pipeline_name: Pipeline name.
        frontmatter: Optional pipeline frontmatter.
        agent_md_path: Optional path to agent.md for learned op write-back.

    Returns:
        Result dict with status, agent_result, goal_description, duration_ms, error.
    """
    import json as _json

    goal_description = step_def.get("goal_description", "")
    if not goal_description:
        goal_description = step_def.get("description", "")

    source_text = ""
    if agent_md_path and agent_md_path.exists():
        try:
            source_text = agent_md_path.read_text(encoding="utf-8")
        except Exception:
            pass

    system_prompt = step_def.get("system_prompt", "")

    result: dict = {
        "step": step_def.get("name", ""),
        "type": "goal",
        "status": "completed",
        "duration_ms": 0,
        "goal_description": goal_description,
        "agent_result": {},
        "output_files": [],
        "error": {"code": None, "message": None, "stack": None},
    }

    start = time.time()
    try:
        from engine.agent import run_goal_step

        agent_result = await run_goal_step(
            step_def=step_def,
            cdp_helpers=cdp_helpers,
            step_dir=step_dir,
            pipeline_name=pipeline_name,
            frontmatter=frontmatter,
            source_text=source_text,
            tools_dir=tools_dir,
            agent_md_path=agent_md_path,
            system_prompt=system_prompt,
        )
        result["agent_result"] = agent_result

        # Write learned_ops.json if present
        learned_ops = agent_result.get("learned_ops", [])
        if learned_ops:
            learned_path = step_dir / "learned_ops.json"
            with open(learned_path, "w", encoding="utf-8") as f:
                _json.dump(learned_ops, f, ensure_ascii=False, indent=2)
            result.setdefault("output_files", []).append(str(learned_path))

        # Check agent status
        agent_status = agent_result.get("status", "")
        if agent_status not in ("success",):
            result["status"] = "failed"
            err_info = agent_result.get("error_message", "")
            err_code = agent_result.get("error_code", "RUNTIME_ERROR")
            result["error"] = {
                "code": err_code,
                "message": err_info or f"Agent finished with status: {agent_status}",
                "stack": None,
            }

    except TimeoutError:
        result["status"] = "failed"
        result["error"] = {
            "code": "TIMEOUT_ERROR",
            "message": "Agent execution timed out",
            "stack": None,
        }
    except Exception as e:
        is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()
        result["status"] = "failed"
        result["error"] = {
            "code": "TIMEOUT_ERROR" if is_timeout else "RUNTIME_ERROR",
            "message": str(e),
            "stack": traceback.format_exc(),
        }

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


# ── Result writing ──


def write_step_json(step_dir: Path, result: dict) -> None:
    """Atomically write the step result to ``step.json`` via ``.tmp`` rename.

    Args:
        step_dir: Step artifact directory.
        result: Result dict to serialize.
    """
    import shutil

    tmp_path = step_dir / "step.json.tmp"
    real_path = step_dir / "step.json"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    shutil.move(str(tmp_path), str(real_path))


# ── Input / output helpers ──


def _resolve_input_files(input_ref: str | dict, run_dir: Path) -> dict[str, str]:
    """Resolve input file references to absolute paths.

    Supports:
    - String refs like ``"step_name.file_name"``
    - Dict refs like ``{"key": "step_name.file_name"}``
    - Absolute ``/path`` refs (blocked — raises ValueError)
    - ``data/`` prefix refs resolved relative to the workspace root

    Args:
        input_ref: Input file reference.
        run_dir: Run directory used for resolving step-relative paths.

    Returns:
        Dict of input key → absolute file path.

    Raises:
        ValueError: If an absolute path or ``..`` traversal is detected.
    """
    if isinstance(input_ref, str):
        key = _default_input_key(input_ref)
        return {key: str(_resolve_path(input_ref, run_dir))}
    if isinstance(input_ref, dict):
        return {k: str(_resolve_path(v, run_dir)) for k, v in input_ref.items()}
    return {}


def _resolve_path(ref: str, run_dir: Path) -> Path:
    """Resolve a single file reference to an absolute path.

    Args:
        ref: File reference string.
        run_dir: Run directory.

    Returns:
        Resolved Path.

    Raises:
        ValueError: If path starts with ``/`` (absolute) or contains ``..``.
    """
    if ref.startswith("/"):
        logger.error("Absolute path ref rejected: %s — would bypass workspace isolation", ref)
        raise ValueError(f"Absolute path reference rejected (violates workspace isolation): {ref}")

    if ".." in ref.split("/"):
        raise ValueError(f"Path traversal rejected: {ref}")

    # data/ prefix → workspace root
    if ref.startswith("data/"):
        # Resolve relative to workspace root (run_dir/../../data/)
        return run_dir.parents[2] / ref

    # step_key.file_name → run_dir/step_key/file_name
    parts = ref.split(".", 1)
    step_key = parts[0]
    file_name = parts[1] if len(parts) > 1 else ""
    resolved = run_dir / step_key / file_name
    if not resolved.exists():
        logger.warning("Input path not found: %s", resolved)
    return resolved


def _default_input_key(ref: str) -> str:
    """Generate a default input key for a string reference.

    ``"step_name.file_name"`` → ``"step_name"``
    ``"some_file.txt"`` → ``"input"``
    """
    parts = ref.split(".", 1)
    return parts[0] if len(parts) > 1 else "input"


def _check_outputs(output_files: list[str], step_dir: Path) -> list[str]:
    """Check that all declared output files exist in the step directory.

    Args:
        output_files: List of file names (relative to step_dir).
        step_dir: Step artifact directory.

    Returns:
        List of missing file names (empty = all present).
    """
    missing: list[str] = []
    for f in output_files:
        if isinstance(f, str):
            if not (step_dir / f).exists():
                missing.append(f)
    return missing
