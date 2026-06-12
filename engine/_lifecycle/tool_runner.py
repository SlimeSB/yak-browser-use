"""ToolRunner — manages _PH- tool lifecycle, LLM generation, validation, and rename."""
from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
import traceback
from pathlib import Path

from engine._lifecycle.guardian import Guardian
from utils.logging import get_logger

logger = get_logger(__name__)

_PH_PREFIX = "_PH-"
DEFAULT_MAX_RETRIES = 3


class ToolRunner:
    """Manages per-pipeline tool execution, _PH- lifecycle, and guardian integration.

    The _PH- lifecycle:
    1. Generate tool code via LLM (``generate_ph_tool``)
    2. Execute and validate (``load_and_call`` + guardian)
    3. Atomic rename ``_PH-foo.py`` → ``foo.py`` (``atomic_rename_ph``)
    """

    def __init__(
        self,
        tools_dir: Path,
        pipeline_name: str,
        guardian: Guardian | None = None,
    ) -> None:
        self.tools_dir = tools_dir
        self.pipeline_name = pipeline_name
        self.guardian = guardian or Guardian()

    def tool_exists(self, tool_name: str) -> bool:
        """Check if a tool file exists in the tools directory."""
        return (self.tools_dir / f"{tool_name}.py").exists()

    def is_ph_tool(self, tool_name: str) -> bool:
        """Check if a tool name has the _PH- prefix."""
        return tool_name.startswith(_PH_PREFIX)

    def strip_ph_prefix(self, ph_name: str) -> str:
        """Remove the _PH- prefix from a tool name."""
        return ph_name[len(_PH_PREFIX):] if ph_name.startswith(_PH_PREFIX) else ph_name

    async def load_and_call(
        self,
        tool_name: str,
        input_files: dict[str, str],
        output_dir: str,
        cdp_helpers: object | None = None,
        func_name: str | None = None,
        **params: object,
    ) -> dict:
        """Load a tool module and call its main function.

        Args:
            tool_name: Name of the tool (without .py).
            input_files: Dict of input file key → path.
            output_dir: Output directory path.
            cdp_helpers: Optional CDP helpers for browser-enabled tools.
            func_name: Function name to call (defaults to tool_name).
            **params: Additional keyword arguments forwarded to the tool function.

        Returns:
            Dict with ``ok`` (bool) and optional ``error``, ``error_code``, ``stack``.
        """
        tool_path = self.tools_dir / f"{tool_name}.py"
        if not tool_path.exists():
            return {"ok": False, "error": f"Tool file not found: {tool_path}"}

        func_name = func_name or tool_name

        logger.debug(
            "tool_runner: loading tool %s from %s (func=%s)",
            tool_name, tool_path, func_name,
        )
        module_name = f"pipeline_tool_{self.pipeline_name}_{tool_name}"
        self._clear_module_cache(module_name)

        try:
            spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
            if spec is None or spec.loader is None:
                return {
                    "ok": False,
                    "error_code": "SYNTAX_ERROR",
                    "error": f"Cannot load module: {tool_path}",
                    "stack": None,
                }
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning("tool_runner: %s syntax error: %s", tool_name, e)
            return {
                "ok": False,
                "error_code": "SYNTAX_ERROR",
                "error": str(e),
                "stack": traceback.format_exc(),
            }

        func = getattr(module, func_name, None)
        if not func:
            return {
                "ok": False,
                "error_code": "SYNTAX_ERROR",
                "error": f"Function {func_name} not found in {tool_path}",
            }

        logger.debug(
            "tool_runner: executing %s (func=%s), input_files=%s, output_dir=%s",
            tool_name, func_name, list(input_files.keys()), output_dir,
        )
        try:
            kwargs: dict = {"input_files": input_files, "output_dir": output_dir, **params}
            if cdp_helpers is not None:
                kwargs["cdp_helpers"] = cdp_helpers

            if asyncio.iscoroutinefunction(func):
                await func(**kwargs)
            else:
                func(**kwargs)
        except Exception as e:
            logger.warning("tool_runner: %s runtime error: %s", tool_name, e)
            is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()
            return {
                "ok": False,
                "error_code": "TIMEOUT_ERROR" if is_timeout else "RUNTIME_ERROR",
                "error": str(e),
                "stack": traceback.format_exc(),
            }

        logger.debug("tool_runner: %s completed ok", tool_name)
        return {"ok": True}

    def generate_ph_tool(
        self,
        ph_name: str,
        step_def: dict,
        input_files: dict[str, str],
        llm_call_fn: object | None = None,
    ) -> dict:
        """Generate a _PH- tool via LLM.

        Args:
            ph_name: Tool name with _PH- prefix.
            step_def: Step definition dict.
            input_files: Dict of input file key → path (for upstream samples).
            llm_call_fn: Callable that takes a prompt string and returns code.

        Returns:
            Dict with ``ok`` (bool) and optional ``error``, ``code``, ``tool_path``.
        """
        if llm_call_fn is None:
            return {"ok": False, "error_code": "LLM_ERROR", "error": "LLM call function not configured"}

        real_name = self.strip_ph_prefix(ph_name)
        upstream_sample = _sniff_input_file(input_files)

        prompt = _build_generation_prompt(ph_name, real_name, step_def, upstream_sample)
        logger.debug(
            "tool_runner: LLM prompt for %s (step: %s):\n%s",
            ph_name, step_def.get("name", ""), prompt[:500],
        )

        llm_result = llm_call_fn(prompt) if callable(llm_call_fn) else None
        if not llm_result or not isinstance(llm_result, str):
            return {"ok": False, "error_code": "LLM_ERROR", "error": "LLM returned empty or invalid result"}

        logger.debug(
            "tool_runner: LLM raw result for %s: %s chars",
            ph_name, len(llm_result),
        )
        code = _extract_code(llm_result)
        logger.debug(
            "tool_runner: extracted code for %s: %s chars",
            ph_name, len(code),
        )

        tool_path = self.tools_dir / f"{ph_name}.py"
        # Backup old file if exists
        if tool_path.exists():
            backup_path = tool_path.with_suffix(".py.bak")
            shutil.copy2(str(tool_path), str(backup_path))
            logger.info("tool_runner: backed up old %s → %s", tool_path.name, backup_path.name)

        tool_path.write_text(code, encoding="utf-8")
        self._clear_module_cache(f"pipeline_tool_{self.pipeline_name}_{ph_name}")
        logger.info("tool_runner: generated %s", tool_path)

        return {"ok": True, "code": code, "tool_path": tool_path}

    def atomic_rename_ph(self, ph_name: str, agent_md_path: Path | None) -> dict:
        """Atomically rename _PH-tool → normal tool and update agent.md references.

        Args:
            ph_name: Tool name with _PH- prefix (e.g. ``_PH-my_tool``).
            agent_md_path: Optional path to agent.md to update references.

        Returns:
            Dict with ``ok`` (bool) and optional ``error``, ``old``, ``new``.
        """
        real_name = self.strip_ph_prefix(ph_name)

        ph_path = self.tools_dir / f"{ph_name}.py"
        real_path = self.tools_dir / f"{real_name}.py"

        if not ph_path.exists():
            return {"ok": False, "error": f"{ph_path} not found"}

        shutil.move(str(ph_path), str(real_path))

        if agent_md_path and agent_md_path.exists():
            tmp_path = agent_md_path.with_suffix(agent_md_path.suffix + ".tmp")
            content = agent_md_path.read_text(encoding="utf-8")
            content = content.replace(ph_name, real_name)
            tmp_path.write_text(content, encoding="utf-8")
            shutil.move(str(tmp_path), str(agent_md_path))

        logger.info("tool_runner: renamed %s → %s", ph_name, real_name)
        return {"ok": True, "old": ph_name, "new": real_name}

    async def run_ph_lifecycle(
        self,
        ph_name: str,
        step_def: dict,
        input_files: dict[str, str],
        output_dir: str,
        llm_call_fn: object | None = None,
        agent_md_path: Path | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        cdp_helpers: object | None = None,
    ) -> dict:
        """Full _PH- lifecycle: generate → execute → validate → rename.

        Args:
            ph_name: Tool name with _PH- prefix.
            step_def: Step definition dict.
            input_files: Dict of input file key → path.
            output_dir: Output directory path.
            llm_call_fn: Callable for LLM code generation.
            agent_md_path: Optional path to agent.md for reference updates.
            max_retries: Maximum retry attempts (default: 3).
            cdp_helpers: Optional CDP helpers for browser-enabled tools.

        Returns:
            Dict with ``status``, optional ``error``, ``upgraded``, ``ph_failed``.
        """
        for attempt in range(1, max_retries + 1):
            logger.debug(
                "tool_runner: lifecycle attempt %d/%d for %s",
                attempt, max_retries, ph_name,
            )
            if attempt > 1:
                logger.info(
                    "tool_runner: retry %d/%d for %s",
                    attempt, max_retries, ph_name,
                )

            gen_result = self.generate_ph_tool(ph_name, step_def, input_files, llm_call_fn)
            if not gen_result.get("ok"):
                if attempt >= max_retries:
                    return {
                        "status": "failed",
                        "error": {
                            "code": "LLM_ERROR",
                            "message": gen_result.get("error", "LLM generation failed"),
                        },
                        "ph_failed": True,
                    }
                continue

            exec_result = await self.load_and_call(
                ph_name,
                input_files,
                output_dir,
                cdp_helpers=cdp_helpers,
                func_name=self.strip_ph_prefix(ph_name),
                **step_def.get("params", {}),
            )
            if not exec_result.get("ok"):
                error_code = exec_result.get("error_code", "RUNTIME_ERROR")
                logger.debug(
                    "tool_runner: attempt %d/%d for %s failed with %s",
                    attempt, max_retries, ph_name, error_code,
                )
                if attempt >= max_retries:
                    return {
                        "status": "failed",
                        "error": {
                            "code": exec_result.get("error_code", "RUNTIME_ERROR"),
                            "message": exec_result.get("error", ""),
                        },
                        "ph_failed": True,
                    }
                continue

            guard_result = self.guardian.validate_output(output_dir, step_def.get("output", []))
            logger.debug(
                "tool_runner: guardian result for %s: %s",
                ph_name, guard_result,
            )
            if not step_def.get("output"):
                logger.debug(
                    "tool_runner: step %s has no output declarations, validation skipped",
                    ph_name,
                )

            if guard_result.get("ok"):
                rename_result = self.atomic_rename_ph(ph_name, agent_md_path)
                if rename_result.get("ok"):
                    return {
                        "status": "completed",
                        "upgraded": True,
                        "upgraded_name": rename_result.get("new"),
                    }
                return {
                    "status": "completed",
                    "error": {
                        "code": "RENAME_ERROR",
                        "message": rename_result.get("error", ""),
                    },
                }

            if attempt >= max_retries:
                return {
                    "status": "failed",
                    "error": {
                        "code": "GUARDIAN_ERROR",
                        "message": guard_result.get("detail", "Guardian validation failed"),
                    },
                    "ph_failed": True,
                }

        return {
            "status": "failed",
            "error": {"code": "LLM_ERROR", "message": "Maximum retries reached"},
            "ph_failed": True,
        }

    @staticmethod
    def _clear_module_cache(module_name: str) -> None:
        """Remove a module from sys.modules cache if present."""
        if module_name in sys.modules:
            del sys.modules[module_name]


# ── module-level helpers ──


def _sniff_input_file(input_files: dict[str, str]) -> str:
    """Read samples from input files for LLM context.

    Args:
        input_files: Dict of key → file path.

    Returns:
        A formatted string with file contents for use in LLM prompts.
    """
    if not input_files:
        return "(no upstream input files)"

    parts: list[str] = []
    for key, path_str in input_files.items():
        path = Path(path_str)
        if not path.exists():
            parts.append(f"### {key}: (file not found: {path_str})")
            continue
        ext = path.suffix.lower()
        try:
            content = path.read_text(encoding="utf-8")
            if ext == ".html":
                sample = content[:2000]
                div_count = content.count("<div")
                table_count = content.count("<table")
                parts.append(
                    f"### {key} (HTML, {len(content)} chars, ~{div_count} div, ~{table_count} table)\n{sample}"
                )
            elif ext == ".csv":
                lines = content.split("\n")[:20]
                parts.append(f"### {key} (CSV, {len(lines)} lines sample)\n" + "\n".join(lines))
            elif ext == ".json":
                sample = content[:1000]
                parts.append(f"### {key} (JSON, {len(content)} chars)\n{sample}")
            else:
                sample = content[:500]
                parts.append(f"### {key} ({len(content)} chars)\n{sample}")
        except Exception as e:
            logger.debug("Cannot read input file %s: %s", key, e)
            parts.append(f"### {key}: (unreadable)")
    return "\n\n".join(parts)


def _build_generation_prompt(
    ph_name: str,
    real_name: str,
    step_def: dict,
    upstream_sample: str,
) -> str:
    """Build the LLM prompt for generating a _PH- tool.

    Args:
        ph_name: _PH- prefixed tool name.
        real_name: Unprefixed tool name.
        step_def: Step definition dict.
        upstream_sample: Sample content from upstream input files.

    Returns:
        Formatted prompt string.
    """
    output_files = step_def.get("output", [])
    params = step_def.get("params", {})
    desc = step_def.get("description", "")

    lines = [
        f"Generate a Python tool function named '{real_name}'.",
        "",
        f"Description: {desc}",
        "",
        f"The file will be saved as '{ph_name}.py' (the _PH- prefix will be stripped after validation).",
        "",
    ]
    if params:
        lines.append(f"Parameters: {params}")
    if output_files:
        lines.append(f"Required output files: {output_files}")
    if upstream_sample:
        lines.append("")
        lines.append("Upstream input file samples:")
        lines.append(upstream_sample)

    lines.append("")
    lines.append(
        "The function signature should be: "
        f"def {real_name}(input_files: dict[str, str], output_dir: str, **params) -> None"
    )
    lines.append("")
    lines.append("Return only the Python code, no explanation.")
    return "\n".join(lines)


def _extract_code(llm_output: str) -> str:
    """Extract Python code from LLM response.

    Handles responses with ```python ... ``` fences, plain ``` fences,
    or bare code.
    """
    if "```python" in llm_output:
        start = llm_output.index("```python") + 9
        end = llm_output.find("```", start)
        if end == -1:
            return llm_output[start:].strip()
        return llm_output[start:end].strip()
    if "```" in llm_output:
        start = llm_output.index("```") + 3
        end = llm_output.find("```", start)
        if end == -1:
            return llm_output[start:].strip()
        return llm_output[start:end].strip()
    return llm_output.strip()
