"""ToolContext — unified browser/data SDK for generated _PH- tools.

Replaces the old ToolCDPHelpers (backend/utils/tool_cdp.py) with a
comprehensive API that wraps PlaywrightBridge browser ops, file I/O data
ops, a CDP escape hatch, domain whitelisting, and a circuit breaker.

Usage in generated tools::

    async def my_tool(ctx: ToolContext, params: dict) -> dict:
        await ctx.wait(1.0)
        title = await ctx.evaluate("document.title")
        await ctx.save_json({"title": title}, "result.json")
        return {"ok": True}
"""

from __future__ import annotations

import asyncio
import csv
import inspect
import json
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cdp.playwright_bridge import PlaywrightBridge

logger = logging.getLogger(__name__)


def build_tool_kwargs(
    func,
    cdp_helpers: object | None,
    input_files: dict[str, str],
    output_dir: str,
    params: dict[str, Any],
    allowed_domains: list[str] | None = None,
) -> dict:
    """Build kwargs dict for a tool function based on its signature.

    Inspects the function's parameters and injects:
    - ``ctx``: ToolContext (if the function accepts it and cdp_helpers is available)
    - ``cdp_helpers``: fallback for legacy tools (if no ``ctx`` param)
    - ``input_files`` / ``output_dir``: if explicitly in the signature
    - ``params``: as a single dict if the function has a ``params`` param,
      otherwise spread as individual kwargs

    Returns a dict ready for ``func(**kwargs)``.
    """
    sig = inspect.signature(func)
    param_names = set(sig.parameters.keys())

    kwargs: dict = {}
    if "ctx" in param_names and cdp_helpers is not None:
        bridge = getattr(cdp_helpers, "bridge", cdp_helpers)
        kwargs["ctx"] = ToolContext(
            bridge=bridge,
            input_files=input_files,
            output_dir=output_dir,
            params={k: v for k, v in params.items() if k not in ("input_files", "output_dir")},
            allowed_domains=allowed_domains,
        )
    elif "cdp_helpers" in param_names and cdp_helpers is not None:
        kwargs["cdp_helpers"] = cdp_helpers

    if "input_files" in param_names:
        kwargs["input_files"] = input_files
    if "output_dir" in param_names:
        kwargs["output_dir"] = output_dir
    if "params" in param_names:
        kwargs["params"] = dict(params)
    else:
        kwargs.update(params)

    return kwargs


class ToolContext:
    """Controlled browser + data API for LLM-generated tool functions.

    Wraps PlaywrightBridge via composition (not inheritance) to expose a
    safe subset of browser operations, file I/O, and a CDP escape hatch.
    """

    DANGEROUS_MODULES: frozenset[str] = frozenset({
        "os",
        "subprocess",
        "sys",
        "shutil",
        "socket",
        "ctypes",
        "signal",
        "multiprocessing",
        "threading",
        "importlib",
        "builtins",
    })

    CDP_BLOCKED_COMMANDS: frozenset[str] = frozenset({
        "Runtime.evaluate",
        "Runtime.callFunctionOn",
        "Runtime.compileScript",
        "Runtime.runScript",
        "Page.navigate",
        "Page.navigateToHistoryEntry",
        "Browser.getVersion",
        "SystemInfo.getInfo",
        "SystemInfo.getProcessInfo",
    })

    def __init__(
        self,
        bridge: PlaywrightBridge,
        input_files: dict[str, str],
        output_dir: str,
        params: dict[str, Any],
        allowed_domains: list[str] | None = None,
    ) -> None:
        self._bridge = bridge
        self.input_files = input_files
        self.output_dir = output_dir
        self.params = params
        self._allowed_domains = allowed_domains or []
        self._fail_count = 0
        self._max_fails = 3

    # ------------------------------------------------------------------
    # Browser ops
    # ------------------------------------------------------------------

    async def wait(self, seconds: float) -> None:
        """Wait for *seconds* (direct ``asyncio.sleep``, not through bridge).

        Does NOT participate in the circuit breaker.
        """
        await asyncio.sleep(seconds)

    async def evaluate(self, js: str) -> Any:
        """Execute JavaScript in the page and return the result."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.evaluate(js)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def click(self, selector: str, click_count: int = 1) -> dict:
        """Click an element matching *selector*. ``click_count=2`` for double-click."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.click(selector, click_count=click_count)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def fill(self, selector: str, text: str) -> dict:
        """Type *text* into an input matching *selector*."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.fill(selector, text)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def snapshot(
        self,
        mode: str = "full",
        query: str = "",
        in_viewport: bool = False,
    ) -> dict:
        """Capture a page snapshot.

        *mode* values:
          - ``"full"`` (default) — complete DOM via ``capture_snapshot``
          - ``"simplified"`` — simplified snapshot via ``simplified_snapshot``
          - ``"interactive"`` — interactive elements via ``simplify_dom``
            (*query* and *in_viewport* only apply in this mode)
        """
        self._check_domain()
        self._check_failures()
        try:
            if mode == "interactive":
                result = await self._bridge.simplify_dom(query=query, in_viewport=in_viewport)
            elif mode == "simplified":
                result = await self._bridge.simplified_snapshot()
            else:
                result = await self._bridge.capture_snapshot()
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def screenshot(self) -> str:
        """Capture the current viewport as a base64-encoded PNG string."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.screenshot()
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def source(self) -> str:
        """Return the full serialized HTML of the current page."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.source()
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    # ------------------------------------------------------------------
    # CDP escape hatch
    # ------------------------------------------------------------------

    async def cdp(self, cmd: str, params: dict[str, Any] | None = None) -> dict:
        """Send a raw CDP command via a temporary CDP session.

        Uses ``bridge._context.new_cdp_session(bridge.page)`` to create a
        throw-away session, send the command, then immediately detach.
        Subject to domain whitelist, circuit breaker, and blocked-command
        constraints.
        """
        if cmd in self.CDP_BLOCKED_COMMANDS:
            raise RuntimeError(f"ToolContext: CDP command '{cmd}' is blocked for security reasons")

        self._check_domain()
        self._check_failures()

        page = self._bridge.page
        if page is None:
            raise RuntimeError("ToolContext: bridge.page is None, call bridge.start() first")

        try:
            cdp_session = await self._bridge._context.new_cdp_session(page)
            try:
                result = await cdp_session.send(cmd, params or {})
                self._fail_count = 0
                return result
            finally:
                await cdp_session.detach()
        except Exception:
            self._fail_count += 1
            raise

    # ------------------------------------------------------------------
    # Data ops
    # ------------------------------------------------------------------

    async def save_json(self, data: Any, name: str = "output.json") -> str:
        """Save *data* as a JSON file in ``output_dir``. Returns the file path."""
        out_path = Path(self.output_dir) / name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("save_json: %s (%d bytes)", out_path, out_path.stat().st_size)
        return str(out_path)

    async def load_json(self, name: str) -> Any:
        """Load a JSON file from ``input_files`` by key *name*."""
        path_str = self.input_files.get(name)
        if not path_str:
            raise FileNotFoundError(f"Input file '{name}' not found in input_files mapping")
        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def save_csv(self, records: list[dict], name: str = "output.csv") -> str:
        """Save a list of dicts as a CSV file in ``output_dir``. Returns the file path."""
        out_path = Path(self.output_dir) / name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not records:
            out_path.write_text("", encoding="utf-8")
            return str(out_path)

        fieldnames = list(dict.fromkeys(k for r in records for k in r.keys()))
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        logger.debug("save_csv: %s (%d rows)", out_path, len(records))
        return str(out_path)

    async def load_csv(self, name: str) -> list[dict]:
        """Load a CSV file from ``input_files`` by key *name*."""
        path_str = self.input_files.get(name)
        if not path_str:
            raise FileNotFoundError(f"Input file '{name}' not found in input_files mapping")
        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    async def load_all_records(self) -> list[dict]:
        """Load all input files (JSON or CSV) and return a flat list of records.

        Tries JSON first for each input key, falls back to CSV.
        Handles both list-of-dicts and dict-of-lists JSON formats.
        """
        all_records: list[dict] = []
        for key in self.input_files:
            try:
                records = await self.load_json(key)
                if isinstance(records, list):
                    all_records.extend(records)
                elif isinstance(records, dict):
                    for val in records.values():
                        if isinstance(val, list):
                            all_records.extend(val)
                            break
                    else:
                        all_records.append(records)
            except Exception:
                try:
                    records = await self.load_csv(key)
                    all_records.extend(records)
                except Exception:
                    pass
        return all_records

    async def save_bytes(self, data: bytes, name: str = "output.bin") -> str:
        """Save raw bytes to a file in ``output_dir``. Returns the file path."""
        out_path = Path(self.output_dir) / name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        logger.debug("save_bytes: %s (%d bytes)", out_path, len(data))
        return str(out_path)

    # ------------------------------------------------------------------
    # Safety internals
    # ------------------------------------------------------------------

    def _check_domain(self) -> None:
        """Raise if the current page domain is not in the allowed list."""
        if not self._allowed_domains:
            return

        page = self._bridge.page
        if page is None:
            return

        from urllib.parse import urlparse

        current_url = page.url
        hostname = urlparse(current_url).hostname or ""
        if hostname not in self._allowed_domains:
            raise RuntimeError(
                f"ToolContext: domain '{hostname}' not in allowed_domains {self._allowed_domains}"
            )

    def _check_failures(self) -> None:
        if self._fail_count >= self._max_fails:
            raise RuntimeError(f"ToolContext circuit breaker: {self._max_fails} consecutive failures")
