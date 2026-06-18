"""ToolRunner — manages tool execution and loading."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import traceback
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


class ToolRunner:
    """Manages per-pipeline tool execution and loading."""

    def __init__(
        self,
        tools_dir: Path,
        pipeline_name: str,
    ) -> None:
        self.tools_dir = tools_dir
        self.pipeline_name = pipeline_name

    def tool_exists(self, tool_name: str) -> bool:
        """Check if a tool file exists in the tools directory."""
        return (self.tools_dir / f"{tool_name}.py").exists()

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
        from engine.ops import build_tool_kwargs

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
            kwargs = build_tool_kwargs(func, cdp_helpers=cdp_helpers)
            kwargs["input_files"] = input_files
            kwargs["output_dir"] = output_dir
            kwargs.update(params)

            if asyncio.iscoroutinefunction(func):
                ret = await func(**kwargs)
            else:
                ret = func(**kwargs)
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
        return {"ok": True, "result": ret}

    @staticmethod
    def _clear_module_cache(module_name: str) -> None:
        """Remove a module from sys.modules cache if present."""
        if module_name in sys.modules:
            del sys.modules[module_name]
