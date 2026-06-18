"""ToolRunner — manages tool execution, loading, and rename operations."""
from __future__ import annotations

import asyncio
import importlib.util
import re
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

import yaml

from engine._lifecycle.guardian import Guardian
from utils.logging import get_logger

logger = get_logger(__name__)

_PH_PREFIX = "_PH-"

_dynamic_tool_registry: dict[str, dict[str, Any]] = {}


def get_dynamic_tools(pipeline_name: str | None = None) -> list[dict[str, Any]]:
    """Return registered dynamic tool schemas, optionally filtered by pipeline."""
    if pipeline_name is None:
        return list(_dynamic_tool_registry.values())
    prefix = f"{pipeline_name}/"
    return [schema for key, schema in _dynamic_tool_registry.items() if key.startswith(prefix)]


def _parse_docstring_params(docstring: str) -> tuple[str, dict[str, Any], list[str]]:
    """Parse a docstring in ``Parameters in **params:`` format.

    Returns (description, properties_dict, required_list).
    """
    description = ""
    properties: dict[str, Any] = {}
    required: list[str] = []

    parts = docstring.split("Parameters in **params:", 1)
    description = parts[0].strip()

    if len(parts) < 2:
        return description, properties, required

    param_text = parts[1]
    param_pattern = re.compile(r"^\s*(\w+)\s*\(([\w\[\], |]+)\)\s*:\s*(.+)$", re.MULTILINE)
    type_map = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
    }

    for match in param_pattern.finditer(param_text):
        name = match.group(1)
        raw_type = match.group(2)
        desc = match.group(3).strip()
        json_type = type_map.get(raw_type, "string")
        prop: dict[str, Any] = {"type": json_type, "description": desc}
        if json_type == "array":
            prop["items"] = {"type": "string"}
        properties[name] = prop
        required.append(name)

    return description, properties, required


def register_tool_schema(pipeline_name: str, tool_name: str, tool_path: Path) -> dict[str, Any] | None:
    """Parse a tool file and register its OpenAI function schema.

    Returns the schema dict if successful, None otherwise.
    """
    import importlib.util
    import inspect
    import sys

    try:
        source = tool_path.read_text(encoding="utf-8")
    except Exception:
        logger.warning("register_tool_schema: cannot read %s", tool_path)
        return None

    module_name = f"_schema_scan_{pipeline_name}_{tool_name}"
    if module_name in sys.modules:
        del sys.modules[module_name]

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
        if spec is None or spec.loader is None:
            logger.warning("register_tool_schema: cannot load %s", tool_path)
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("register_tool_schema: import failed for %s", tool_path)
        return None

    func_name = None
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        sig = inspect.signature(obj)
        param_names = list(sig.parameters.keys())
        if param_names[:2] == ["ctx", "params"]:
            func_name = name
            break

    if func_name is None:
        logger.warning("register_tool_schema: no ctx/params function in %s", tool_path)
        return None

    doc_match = re.search(r'"""(.+?)"""', source, re.DOTALL)
    docstring = doc_match.group(1).strip() if doc_match else ""
    description, properties, required = _parse_docstring_params(docstring)

    if not description:
        description = f"Auto-generated tool: {func_name}"

    schema: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": func_name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }

    key = f"{pipeline_name}/{tool_name}"
    _dynamic_tool_registry[key] = schema
    logger.info("register_tool_schema: registered %s → %s", key, func_name)
    return schema


class ToolRunner:
    """Manages per-pipeline tool execution, loading, and rename operations.

    The _PH- lifecycle:
    1. Agent generates tool code via ph-tool-generation skill
    2. Execute and validate (``load_and_call`` + guardian)
    3. Rename ``_PH-foo.py`` → ``foo.py`` (``rename_ph_file`` + ``update_pipeline_refs``)
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
            cdp_helpers: Optional CDP helpers for creating ToolContext.
            func_name: Function name to call (defaults to tool_name).
            **params: Additional keyword arguments forwarded to the tool function.

        Returns:
            Dict with ``ok`` (bool) and optional ``error``, ``error_code``, ``stack``,
            and the tool function's return value under ``result``.
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
        except SyntaxError as e:
            logger.warning("tool_runner: %s syntax error: %s", tool_name, e)
            return {
                "ok": False,
                "error_code": "SYNTAX_ERROR",
                "error": str(e),
                "stack": traceback.format_exc(),
            }
        except Exception as e:
            logger.warning("tool_runner: %s import error: %s", tool_name, e)
            return {
                "ok": False,
                "error_code": "IMPORT_ERROR",
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
            from engine.ops import build_tool_kwargs

            kwargs = build_tool_kwargs(func, cdp_helpers, input_files, output_dir, dict(params))

            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)

            if isinstance(result, dict):
                return {"ok": True, "result": result}
            return {"ok": True}
        except Exception as e:
            logger.warning("tool_runner: %s runtime error: %s", tool_name, e)
            is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()
            return {
                "ok": False,
                "error_code": "TIMEOUT_ERROR" if is_timeout else "RUNTIME_ERROR",
                "error": str(e),
                "stack": traceback.format_exc(),
            }

    def rename_ph_file(self, ph_name: str) -> dict:
        """Rename _PH-tool file → normal tool file (file move only, no YAML update).

        Args:
            ph_name: Tool name with _PH- prefix (e.g. ``_PH-my_tool``).

        Returns:
            Dict with ``ok`` (bool) and optional ``error``, ``old``, ``new``.
        """
        real_name = self.strip_ph_prefix(ph_name)

        ph_path = self.tools_dir / f"{ph_name}.py"
        real_path = self.tools_dir / f"{real_name}.py"

        if not ph_path.exists():
            return {"ok": False, "error": f"{ph_path} not found"}

        shutil.move(str(ph_path), str(real_path))
        self._clear_module_cache(f"pipeline_tool_{self.pipeline_name}_{ph_name}")

        register_tool_schema(self.pipeline_name, real_name, real_path)

        logger.info("tool_runner: renamed %s → %s", ph_name, real_name)
        return {"ok": True, "old": ph_name, "new": real_name}

    def update_pipeline_refs(
        self, ph_name: str, real_name: str, pipeline_path: Path | None
    ) -> dict:
        """Update pipeline YAML references from _PH- name to real name.

        Args:
            ph_name: _PH- prefixed name to replace.
            real_name: Unprefixed replacement name.
            pipeline_path: Path to pipeline.yaml to update references.

        Returns:
            Dict with ``ok`` (bool) and optional ``error``.
        """
        if pipeline_path is None:
            return {"ok": False, "error": "No pipeline path"}

        if not pipeline_path.exists():
            return {"ok": False, "error": f"Pipeline not found: {pipeline_path}"}

        try:
            data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8"))
            data = _replace_ph_refs(data, ph_name, real_name)
            tmp_path = pipeline_path.with_suffix(pipeline_path.suffix + ".tmp")
            tmp_path.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )
            shutil.move(str(tmp_path), str(pipeline_path))
        except Exception as e:
            logger.warning("tool_runner: failed to update pipeline.yaml references: %s", e)
            return {"ok": False, "error": str(e)}

        logger.info("tool_runner: updated pipeline refs %s → %s", ph_name, real_name)
        return {"ok": True}

    @staticmethod
    def _clear_module_cache(module_name: str) -> None:
        """Remove a module from sys.modules cache if present."""
        if module_name in sys.modules:
            del sys.modules[module_name]


# ── module-level helpers ──


def _replace_ph_refs(data, ph_name: str, real_name: str):
    """Recursively replace placeholder name references in a YAML data structure.

    Only replaces in ``tool_name`` dict keys to avoid corrupting
    descriptions and comments.

    Args:
        data: Parsed YAML structure (dict, list, str, etc.).
        ph_name: _PH- prefixed name to replace.
        real_name: Unprefixed replacement name.

    Returns:
        The data structure with tool_name references updated.
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k == "tool_name" and isinstance(v, str):
                result[k] = v.replace(ph_name, real_name)
            else:
                result[k] = _replace_ph_refs(v, ph_name, real_name)
        return result
    if isinstance(data, list):
        return [_replace_ph_refs(item, ph_name, real_name) for item in data]
    return data
