"""
parser.py — Parse agent.md files into structured step definitions.

Parses YAML frontmatter, markdown headings, and step blocks
(browser:, tool:, goal:) into StepDef dataclass instances.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from utils.logging import get_logger

logger = get_logger(__name__)


# ── Template resolution (inline, lightweight) ──

_TEMPLATE_PATTERN = re.compile(r"\{\{template:([a-zA-Z0-9_-]+)\}\}")
_PROMPTS_DIR: Path | None = None


def _get_prompts_dir() -> Path:
    global _PROMPTS_DIR
    if _PROMPTS_DIR is None:
        _PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
    return _PROMPTS_DIR


def _resolve_templates(text: str) -> str:
    """Replace {{template:xxx}} placeholders with prompt file content."""

    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        tmpl_path = _get_prompts_dir() / f"{name}.md"
        if tmpl_path.is_file():
            return tmpl_path.read_text(encoding="utf-8").strip()
        logger.warning("Template '%s' not found at %s", name, tmpl_path)
        return match.group(0)

    return _TEMPLATE_PATTERN.sub(_replacer, text)


# ── Data classes ──


@dataclass
class StepDef:
    """Represents a single parsed step from an agent.md file."""

    key: str
    name: str
    description: str = ""
    browser_ops: list[dict] = field(default_factory=list)
    input_schema: dict[str, str] = field(default_factory=dict)
    output_schema: dict[str, str] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    raw_content: str = ""
    system_prompt: str = ""
    step_type: str = ""
    is_goal: bool = False
    goal_description: str = ""
    tool_name: str = ""
    input_ref: dict | str = ""
    output_ref: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    def to_runtime_dict(self, handler: Callable | None = None) -> dict:
        """Convert to a runtime step dictionary for pipeline execution."""
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "step_type": self.step_type,
            "depends_on": self.depends_on,
            "handler": handler,
            "browser_ops": self.browser_ops,
            "is_goal": self.is_goal,
            "goal_description": self.goal_description,
            "tool_name": self.tool_name,
            "input": self.input_ref if self.input_ref else {},
            "output": self.output_ref if self.output_ref else [],
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "params": self.params,
            "system_prompt": self.system_prompt,
        }


@dataclass
class AgentMD:
    """Represents a complete parsed agent.md document."""

    name: str
    description: str = ""
    steps: list[StepDef] = field(default_factory=list)
    frontmatter: dict = field(default_factory=dict)


# ── Helper ──

VALID_STEP_TYPES = {"browser", "tool", "goal"}


def _finalize_step(step: StepDef, strict_mode: bool = False) -> None:
    """Infer and set step type, validate step_type legality."""
    if step.step_type:
        if step.step_type not in VALID_STEP_TYPES:
            msg = (
                f"Step '{step.name}' has invalid step_type '{step.step_type}'. "
                f"Must be one of: browser, tool, goal"
            )
            if strict_mode:
                raise ValueError(msg)
            logger.warning("%s. Falling back to inference.", msg)
            step.step_type = ""
        else:
            if step.step_type in ("tool", "goal"):
                step.browser_ops = []
            if step.step_type == "goal":
                step.is_goal = True
                if not step.goal_description:
                    step.goal_description = step.description
            else:
                step.is_goal = False
            return

    if step.tool_name:
        step.step_type = "tool"
        step.browser_ops = []
        step.is_goal = False
        return

    if step.browser_ops:
        step.step_type = "browser"
        step.is_goal = False
        return

    if step.description.strip():
        logger.warning(
            "Step '%s' has no explicit step_type tag. "
            "Treating as 'goal' for backward compatibility. "
            "Please add an explicit 'goal:', 'browser:', or 'tool:' tag.",
            step.name,
        )
        step.step_type = "goal"
        step.is_goal = True
        step.goal_description = step.description
        step.browser_ops = []
        return

    raise ValueError(
        f"Step '{step.name}' has no step_type and cannot be inferred. "
        f"Please add one of: browser:, tool:, goal:"
    )


# ── Main parser ──


def parse_agent_md(text: str, strict_mode: bool = False) -> AgentMD:
    """Parse agent.md text content into structured step definitions.

    Args:
        text: Full text content of an agent.md file.
        strict_mode: Raise on invalid step_type rather than warning.

    Returns:
        AgentMD containing parsed steps and frontmatter configuration.

    Raises:
        ValueError: When a step cannot be assigned a valid step_type.
    """
    # Pre-process {{template:xxx}} placeholders
    text = _resolve_templates(text)

    lines = text.strip().split("\n")
    logger.debug("Parsing agent.md with %d lines", len(lines))

    frontmatter: dict = {}
    name = ""
    description = ""
    steps: list[StepDef] = []
    current_step: StepDef | None = None
    current_section: str | None = None
    in_frontmatter = False
    fm_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # Frontmatter start
        if i == 0 and line.startswith("---"):
            in_frontmatter = True
            i += 1
            continue

        # Frontmatter end
        if in_frontmatter and line.startswith("---"):
            in_frontmatter = False
            if fm_lines:
                try:
                    frontmatter = yaml.safe_load("\n".join(fm_lines)) or {}
                except yaml.YAMLError as e:
                    logger.warning("Failed to parse frontmatter YAML: %s", e)
                    frontmatter = {}
            i += 1
            continue

        if in_frontmatter:
            fm_lines.append(line)
            i += 1
            continue

        # Title (level-1 heading)
        if line.startswith("# ") and not line.startswith("## "):
            name = line[2:].strip()
            i += 1
            continue

        # Blockquote description (before any step)
        if line.startswith("> ") and not current_step:
            desc_line = line[2:].strip()
            description = (description + " " + desc_line) if description else desc_line
            i += 1
            continue

        # Step heading
        if line.startswith("## "):
            if current_step:
                _finalize_step(current_step, strict_mode)
                steps.append(current_step)
            step_name = line[3:].strip()
            step_key = re.sub(r"[^\w\u4e00-\u9fff]+", "_", step_name).strip("_").lower()
            current_step = StepDef(key=step_key, name=step_name)
            current_section = None
            i += 1
            continue

        if current_step and line.startswith("> "):
            desc_line = line[2:].strip()
            current_step.description = (
                (current_step.description + " " + desc_line) if current_step.description else desc_line
            )
            i += 1
            continue

        # Accumulate non-keyword text as description
        if (
            current_step
            and not current_section
            and line.strip()
            and not re.match(r"^(browser|tool|depends_on|input|output|params|goal):", line)
        ):
            desc_line = line.strip()
            current_step.description = (
                (current_step.description + " " + desc_line) if current_step.description else desc_line
            )
            i += 1
            continue

        # depends_on
        if current_step and line.startswith("depends_on:"):
            raw = line.split(":", 1)[1].strip()
            deps = re.findall(r"['\"]?([^'\"\[\],]+)['\"]?", raw)
            current_step.depends_on = [d.strip() for d in deps if d.strip()]
            i += 1
            continue

        # tool: — MUST be checked before browser/input/output to allow
        # input:/output:/params: subsections inside tool steps.
        if current_step and line.startswith("tool:"):
            raw = line.split(":", 1)[1].strip()
            current_step.tool_name = raw
            current_step.step_type = "tool"
            current_section = "tool"
            i += 1
            continue

        # Tool sub-sections (input_map, output, params)
        # Place this BEFORE generic browser/input/output check so that
        # input:/output:/params: lines inside a tool step are handled here.
        if current_step and current_section in ("tool", "tool_input_map", "tool_params", "tool_output"):
            indented = line.strip()
            if indented.startswith("input:"):
                val = indented.split(":", 1)[1].strip()
                if not val:
                    current_section = "tool_input_map"
                else:
                    current_step.input_ref = val
                    current_section = "tool"
            elif indented.startswith("output:"):
                val = indented.split(":", 1)[1].strip()
                current_step.output_ref = [v.strip() for v in val.split(",") if v.strip()]
                current_section = "tool_output"
            elif indented.startswith("params:"):
                val = indented.split(":", 1)[1].strip()
                if not val:
                    current_section = "tool_params"
            elif current_section == "tool_input_map":
                if ":" in indented:
                    k, _, v = indented.partition(":")
                    if isinstance(current_step.input_ref, str):
                        current_step.input_ref = {}
                    current_step.input_ref[k.strip()] = v.strip()
            elif current_section == "tool_output":
                if ":" in indented:
                    k, _, v = indented.partition(":")
                    current_step.output_ref.append(v.strip())
            elif current_section == "tool_params":
                if ":" in indented:
                    k, _, v = indented.partition(":")
                    val_stripped = v.strip()
                    try:
                        val_stripped = int(val_stripped)
                    except ValueError:
                        try:
                            val_stripped = float(val_stripped)
                        except ValueError:
                            val_stripped = val_stripped.strip('"').strip("'")
                    current_step.params[k.strip()] = val_stripped
            i += 1
            continue

        # browser: / input: / output: section headers (generic, non-tool)
        if current_step and re.match(r"^(browser|input|output):", line):
            current_section = line.split(":")[0].strip()
            if current_section == "browser":
                current_step.step_type = "browser"
            i += 1
            continue

        # goal:
        if current_step and line.startswith("goal:"):
            raw = line.split(":", 1)[1].strip()
            if current_step.step_type and current_step.step_type != "goal":
                logger.warning(
                    "Step '%s' has both '%s:' and 'goal:' tags. 'goal:' overrides.",
                    current_step.name, current_step.step_type,
                )
            current_step.step_type = "goal"
            current_step.goal_description = raw
            current_step.description = raw
            current_section = "goal"
            i += 1
            continue

        # browser / input / output / goal body content
        if current_step and current_section in ("browser", "input", "output", "goal"):
            indented = line.strip()
            if current_section == "browser":
                op_match = re.match(r"-\s+(\w+):\s*(.*)", indented)
                if op_match:
                    op_type = op_match.group(1).strip()
                    op_value = op_match.group(2).strip().strip('"').strip("'")
                    current_step.browser_ops.append({"type": op_type, "value": op_value})
                elif current_step.browser_ops and ":" in indented:
                    k, _, v = indented.partition(":")
                    current_step.browser_ops[-1][k.strip()] = v.strip().strip('"').strip("'")
            elif current_section == "input":
                if ":" in indented:
                    k, _, v = indented.partition(":")
                    current_step.input_schema[k.strip()] = v.strip()
            elif current_section == "output":
                if ":" in indented:
                    k, _, v = indented.partition(":")
                    current_step.output_schema[k.strip()] = v.strip()
            elif current_section == "goal":
                if indented and not re.match(r"^(browser|tool|goal|depends_on|input|output|params):", indented):
                    current_step.description = (
                        (current_step.description + " " + indented).strip() if current_step.description else indented
                    )
                    current_step.goal_description = (
                        (current_step.goal_description + " " + indented).strip() if current_step.goal_description else indented
                    )
            i += 1
            continue

        current_section = None
        i += 1

    if current_step:
        _finalize_step(current_step, strict_mode)
        steps.append(current_step)

    if name:
        frontmatter.setdefault("name", name)

    logger.debug("Found %d steps", len(steps))

    return AgentMD(
        name=frontmatter.get("name", name),
        description=description,
        steps=steps,
        frontmatter=frontmatter,
    )


def parse_step_browser_ops(source_text: str, step_name: str, strict_mode: bool = False) -> list[dict]:
    """Extract browser ops for a specific step from agent.md source text."""
    parsed = parse_agent_md(source_text, strict_mode)
    step_key = re.sub(r"[^\w\u4e00-\u9fff]+", "_", step_name).strip("_").lower()

    for step in parsed.steps:
        if step.name == step_name or step.key == step_key:
            return step.browser_ops

    return []


def inject_params_to_frontmatter(agent_md_text: str, params: dict | None) -> str:
    """Inject a params block into the YAML frontmatter.

    If agent_md_text has a frontmatter (--- ... ---), inserts params: before
    the closing ---. Returns original text if no params or no frontmatter.
    """
    if not params:
        return agent_md_text
    lines = agent_md_text.split("\n")
    if not lines or lines[0].strip() != "---":
        return agent_md_text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            lines.insert(i, "params:")
            for k, v in params.items():
                lines.insert(i + 1, f"  {k}: {v}")
            break
    return "\n".join(lines)
