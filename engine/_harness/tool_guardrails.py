"""Tool call guardrails — detect tool-loop failures.

Chat mode uses relaxed thresholds: warn higher, hard_stop disabled.
Guardrails are a safety net, not a judge — Agent retains autonomy
to self-correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prompts._loader import load_prompt


@dataclass
class ToolCallGuardrailConfig:
    """Thresholds for guardrail warnings and blocks."""

    hard_stop_enabled: bool = False

    exact_failure_warn_after: int = 5
    same_tool_failure_warn_after: int = 6
    no_progress_warn_after: int = 3

    exact_failure_block_after: int = 10
    same_tool_failure_halt_after: int = 15
    no_progress_block_after: int = 8


def create_chat_guardrail_config() -> ToolCallGuardrailConfig:
    """Create the relaxed guardrail config for chat mode."""
    return ToolCallGuardrailConfig(
        hard_stop_enabled=False,
        exact_failure_warn_after=5,
        same_tool_failure_warn_after=6,
        no_progress_warn_after=3,
        exact_failure_block_after=10,
        same_tool_failure_halt_after=15,
        no_progress_block_after=8,
    )


@dataclass
class ToolCallGuardrailState:
    """Per-turn state tracking tool call patterns."""

    config: ToolCallGuardrailConfig = field(default_factory=ToolCallGuardrailConfig)

    _exact_failures: dict[str, int] = field(default_factory=dict)
    _tool_failures: dict[str, int] = field(default_factory=dict)
    _last_results: dict[str, str] = field(default_factory=dict)
    _no_progress_counts: dict[str, int] = field(default_factory=dict)

    def reset(self) -> None:
        """Reset all counters — called at start of each turn."""
        self._exact_failures.clear()
        self._tool_failures.clear()
        self._last_results.clear()
        self._no_progress_counts.clear()

    def before_call(self, tool_name: str, tool_args: dict) -> bool | str | None:
        """Check if the call should be blocked before execution.

        Returns:
            True if allowed, False if blocked, str if blocked with message.
        """
        exact_key = self._exact_key(tool_name, tool_args)
        exact_count = self._exact_failures.get(exact_key, 0)
        tool_count = self._tool_failures.get(tool_name, 0)
        no_prog_count = self._no_progress_counts.get(tool_name, 0)

        if self.config.hard_stop_enabled:
            if exact_count >= self.config.exact_failure_block_after:
                return load_prompt(
                    "guardrails/exact_failure",
                    tool_name=tool_name,
                    count=str(exact_count),
                )
            if tool_count >= self.config.same_tool_failure_halt_after:
                return load_prompt(
                    "guardrails/same_tool_failure",
                    tool_name=tool_name,
                    count=str(tool_count),
                )
            if no_prog_count >= self.config.no_progress_block_after:
                return load_prompt(
                    "guardrails/no_progress",
                    tool_name=tool_name,
                    count=str(no_prog_count),
                )

        return True

    def after_call(
        self, tool_name: str, tool_args: dict, ok: bool, result_str: str
    ) -> str | None:
        """Update state and return warning message (if threshold hit).

        Returns:
            None if no warning, str warning message if threshold exceeded.
        """
        exact_key = self._exact_key(tool_name, tool_args)

        if not ok:
            self._exact_failures[exact_key] = self._exact_failures.get(exact_key, 0) + 1
            self._tool_failures[tool_name] = self._tool_failures.get(tool_name, 0) + 1
        else:
            last_result = self._last_results.get(exact_key)
            if last_result is not None and result_str == last_result:
                self._no_progress_counts[tool_name] = \
                    self._no_progress_counts.get(tool_name, 0) + 1
            else:
                self._no_progress_counts[tool_name] = 0
            self._last_results[exact_key] = result_str

        exact_count = self._exact_failures.get(exact_key, 0)
        tool_count = self._tool_failures.get(tool_name, 0)
        no_prog_count = self._no_progress_counts.get(tool_name, 0)

        warning: str | None = None

        if exact_count >= self.config.exact_failure_warn_after:
            warning = load_prompt(
                "guardrails/exact_failure",
                tool_name=tool_name,
                count=str(exact_count),
            )
        elif tool_count >= self.config.same_tool_failure_warn_after:
            warning = load_prompt(
                "guardrails/same_tool_failure",
                tool_name=tool_name,
                count=str(tool_count),
            )
        elif no_prog_count >= self.config.no_progress_warn_after:
            warning = load_prompt(
                "guardrails/no_progress",
                tool_name=tool_name,
                count=str(no_prog_count),
            )

        return warning

    @staticmethod
    def _exact_key(tool_name: str, tool_args: dict) -> str:
        return f"{tool_name}:{_stable_repr(tool_args)}"


def _stable_repr(d: dict) -> str:
    """Stable string representation of dict for comparison."""
    return str(sorted(d.items()))
