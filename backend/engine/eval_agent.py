"""EvalAgent — subagent for complex DOM operations and captcha solving.

Launched by the main LLM via the eval_agent tool. Runs its own
conversation loop with a restricted tool set (browser_eval, browser_snapshot,
browser_click, browser_fill, browser_wait, browser_source, browser_scroll).
"""

from __future__ import annotations

import re
from typing import Callable

from prompts._loader import load_prompt


class EvalAgent:
    """Subagent that iteratively evaluates JS in the browser to complete a task.

    Args:
        prompt_template: System prompt template with {purpose} and {snapshot}
            placeholders. Defaults to ``prompts/eval_agent/system.md``.
        js_functions: JS function library injected into the prompt.
            Defaults to ``prompts/eval_agent/js_lib.js``.
        max_attempts: Maximum eval attempts (default 3).
    """

    def __init__(
        self,
        prompt_template: str = "",
        js_functions: str = "",
        max_attempts: int = 3,
    ) -> None:
        self.prompt_template = prompt_template or load_prompt("eval_agent/system")
        self.js_functions = js_functions or _load_js_lib()
        self.max_attempts = max_attempts

    def build_system_prompt(self, purpose: str, snapshot: str) -> str:
        """Render the system prompt with injected variables (single-pass, safe)."""
        values = {
            "purpose": purpose,
            "snapshot": snapshot,
            "js_lib": self.js_functions,
            "max_attempts": str(self.max_attempts),
        }
        return re.sub(
            r"\{(\w+)\}",
            lambda m: values.get(m.group(1), m.group(0)),
            self.prompt_template,
        )

    def get_restricted_tools(self) -> list[dict]:
        """Return the restricted tool set for the eval agent."""
        from tools.registry import registry

        allowed = {
            "browser_eval",
            "browser_snapshot",
            "browser_click",
            "browser_fill",
            "browser_wait",
            "browser_source",
            "browser_scroll",
            "captcha",
        }
        return registry.filter(allowed)


def _load_js_lib() -> str:
    from pathlib import Path
    from prompts._loader import _PROMPTS_DIR

    js_path = _PROMPTS_DIR / "eval_agent" / "js_lib.js"
    if js_path.exists():
        return js_path.read_text(encoding="utf-8")
    return ""
