"""PipelineStore — unified pipeline YAML document read/write/validate/CRUD abstraction.

All pipeline.yaml I/O MUST go through this class to ensure consistent format
conversion, default stripping, and validation. No direct yaml.safe_load or
yaml.dump calls on pipeline files outside this module.

Format boundary:
  - load:    YAML format ({goto: "url"})  →  internal format ({type: "goto", value: "url"})
  - save:    internal format → YAML format
  - PipelineYaml.browser_ops always holds internal format in memory.
  - add_step/update_step accept YAML-format browser_ops and auto-convert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from yak_browser_use.compiler.schema import PipelineYaml, StepYaml
from yak_browser_use.utils.helpers import sanitize_pipeline_name
from yak_browser_use.utils.logging import get_logger
from yak_browser_use.workspace.manager import WORKSPACES_ROOT

logger = get_logger(__name__)


@dataclass
class PipelineMeta:
    name: str
    description: str
    step_count: int


_META_KEYS = frozenset({"retry", "optional"})


class PipelineStore:
    """Unified pipeline YAML document abstraction."""

    def __init__(self, workspaces_root: Path | None = None) -> None:
        self._workspaces_root = workspaces_root or WORKSPACES_ROOT

    # ── helpers ──

    @staticmethod
    def _resolve_pipeline_path(workspaces_root: Path, pipeline_name: str) -> Path:
        safe_name = sanitize_pipeline_name(pipeline_name)
        return workspaces_root / safe_name / "pipeline.yaml"

    # ── 2.2 _strip_defaults ──

    @staticmethod
    def _strip_defaults(obj):
        """Recursively remove None, "", [], {} values."""
        if isinstance(obj, dict):
            return {
                k: PipelineStore._strip_defaults(v)
                for k, v in obj.items()
                if v is not None and v != "" and v != [] and v != {}
            }
        if isinstance(obj, list):
            return [PipelineStore._strip_defaults(v) for v in obj]
        return obj

    # ── 2.3 _from_yaml_ops ──

    @staticmethod
    def _from_yaml_ops(ops: list[dict]) -> list[dict]:
        """Convert YAML format [{goto: "url"}] → internal format [{type: "goto", value: "url"}]."""
        result: list[dict] = []
        for op in ops:
            if "type" in op:
                result.append({k: v for k, v in op.items()})
                continue
            for key, val in op.items():
                if key == "type":
                    continue
                if isinstance(val, dict):
                    entry = {"type": key, **val}
                else:
                    entry = {"type": key, "value": val}
                for k, v in op.items():
                    if k != key and k != "type":
                        entry[k] = v
                result.append(entry)
                break
            else:
                result.append({})
        return result

    # ── 2.4 _to_yaml_ops ──

    @staticmethod
    def _to_yaml_ops(ops: list[dict]) -> list[dict]:
        """Convert internal format [{type: "goto", value: "url"}] → YAML format [{goto: "url"}]."""
        result: list[dict] = []
        for op in ops:
            op_type = op.get("type", "")
            style = {k: v for k, v in op.items() if k in _META_KEYS}
            rest = {k: v for k, v in op.items() if k != "type" and k not in _META_KEYS}
            if len(rest) == 1 and "value" in rest:
                entry = {op_type: rest["value"]}
            elif rest:
                entry = {op_type: rest}
            else:
                entry = {op_type: op.get("value", "")}
            entry.update(style)
            result.append(entry)
        return result

    # ── 2.5 ops_to_yaml (public) ──

    @staticmethod
    def ops_to_yaml(ops: list[dict]) -> list[dict]:
        """Public tool: internal format → YAML format (for write_pipeline_learned, pipeline_compile)."""
        return PipelineStore._to_yaml_ops(ops)

    # ── 2.6 load ──

    def load(self, pipeline_name: str) -> PipelineYaml:
        """Read pipeline.yaml, convert browser_ops from YAML format to internal format."""
        path = self._resolve_pipeline_path(self._workspaces_root, pipeline_name)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline '{pipeline_name}' not found at {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Pipeline '{pipeline_name}' is not a valid YAML mapping")
        self._convert_steps_from_yaml(raw)
        return PipelineYaml.model_validate(raw)

    @staticmethod
    def _convert_steps_from_yaml(raw: dict) -> None:
        """Mutate raw steps in-place: convert browser_ops from YAML to internal format."""
        steps = raw.get("steps")
        if not isinstance(steps, list):
            return
        for step in steps:
            if not isinstance(step, dict):
                continue
            ops = step.get("browser_ops")
            if isinstance(ops, list):
                step["browser_ops"] = PipelineStore._from_yaml_ops(ops)

    # ── 2.7 save ──

    def save(self, pipeline_name: str, doc: PipelineYaml) -> str:
        """Serialize PipelineYaml to YAML format and write to file. Returns the YAML string."""
        yaml_text = self.to_yaml(doc)
        safe_name = sanitize_pipeline_name(pipeline_name)
        path = self._workspaces_root / safe_name / "pipeline.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_text, encoding="utf-8")
        return yaml_text

    # ── 2.8 validate ──

    @staticmethod
    def validate(yaml_text: str) -> PipelineYaml:
        """Parse YAML text, convert browser_ops to internal format, validate against PipelineYaml."""
        raw = yaml.safe_load(yaml_text)
        if not isinstance(raw, dict):
            raise ValueError("YAML content is not a mapping")
        PipelineStore._convert_steps_from_yaml(raw)
        return PipelineYaml.model_validate(raw)

    # ── 2.9 from_yaml ──

    @staticmethod
    def from_yaml(yaml_text: str) -> PipelineYaml:
        """Same as validate — parse YAML text and return validated PipelineYaml with internal format."""
        return PipelineStore.validate(yaml_text)

    # ── 2.10 to_yaml ──

    @staticmethod
    def to_yaml(doc: PipelineYaml) -> str:
        """Serialize PipelineYaml to YAML string (internal format → YAML format, strip defaults)."""
        data = doc.model_dump()
        PipelineStore._convert_steps_to_yaml(data)
        stripped = PipelineStore._strip_defaults(data)
        return yaml.dump(stripped, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _convert_steps_to_yaml(data: dict) -> None:
        """Mutate data in-place: convert browser_ops from internal to YAML format."""
        steps = data.get("steps")
        if not isinstance(steps, list):
            return
        for step in steps:
            if not isinstance(step, dict):
                continue
            ops = step.get("browser_ops")
            if isinstance(ops, list):
                step["browser_ops"] = PipelineStore._to_yaml_ops(ops)

    # ── 2.11 load_meta ──

    def load_meta(self, pipeline_name: str) -> PipelineMeta:
        """Lightweight read — name/description/step_count only, no Pydantic validation."""
        path = self._resolve_pipeline_path(self._workspaces_root, pipeline_name)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline '{pipeline_name}' not found at {path}")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.warning("load_meta: failed to parse %s", path, exc_info=True)
            return PipelineMeta(name=pipeline_name, description="(parse error)", step_count=0)
        if not isinstance(raw, dict):
            return PipelineMeta(name=pipeline_name, description="(parse error)", step_count=0)
        desc = raw.get("description", "")
        steps = raw.get("steps", [])
        step_count = len(steps) if isinstance(steps, list) else 0
        return PipelineMeta(name=raw.get("name", pipeline_name), description=desc, step_count=step_count)

    # ── 2.12 update_step ──

    _DEEP_PATH_RE = re.compile(r"([\w-]+)\[(\d+)\]\.(.+)")

    def update_step(self, doc: PipelineYaml, name: str, updates: dict) -> PipelineYaml:
        """Update a step's fields. `updates["browser_ops"]` accepts YAML format, auto-converted.
        
        Supports deep-path keys like ``"browser_ops[2].text"`` for field-level updates.
        When value is a list or dict, it replaces the target entirely.
        """
        target_idx = None
        for i, s in enumerate(doc.steps):
            if s.name == name:
                target_idx = i
                break
        if target_idx is None:
            raise ValueError(f"Step '{name}' not found")

        step_dict = doc.steps[target_idx].model_dump()

        deep_keys: dict[str, tuple[str, int, str]] = {}
        normal_keys: dict[str, object] = {}

        for key, val in updates.items():
            m = self._DEEP_PATH_RE.match(key)
            if m:
                deep_keys[key] = (m.group(1), int(m.group(2)), m.group(3))
            else:
                normal_keys[key] = val

        for list_key, index, field in deep_keys.values():
            target_list = step_dict.get(list_key)
            if not isinstance(target_list, list):
                raise ValueError(f"'{list_key}' is not a list, cannot apply deep path")
            if index < 0 or index >= len(target_list):
                raise ValueError(f"Index {index} out of range for '{list_key}' (size {len(target_list)})")
            if isinstance(target_list[index], dict):
                target_list[index][field] = updates.get(f"{list_key}[{index}].{field}")
            else:
                raise ValueError(f"Element at '{list_key}[{index}]' is not a dict")

        if "browser_ops" in normal_keys:
            ops = normal_keys["browser_ops"]
            step_dict["browser_ops"] = self._from_yaml_ops(ops) if isinstance(ops, list) else ops
        if "tool_name" in normal_keys:
            step_dict["tool_name"] = normal_keys["tool_name"]
        if "goal_description" in normal_keys:
            step_dict["goal_description"] = normal_keys["goal_description"]
        if "params" in normal_keys:
            step_dict["params"] = normal_keys["params"]
        if "description" in normal_keys:
            step_dict["description"] = normal_keys["description"]
        if "depends_on" in normal_keys:
            step_dict["depends_on"] = normal_keys["depends_on"]
        if "check" in normal_keys:
            step_dict["check"] = normal_keys["check"]

        type_fields = [k for k in ("browser_ops", "tool_name", "goal_description") if k in normal_keys]
        if len(type_fields) == 1:
            for other in ("browser_ops", "tool_name", "goal_description"):
                if other not in normal_keys:
                    step_dict[other] = None

        new_step = StepYaml.model_validate(step_dict)
        doc.steps[target_idx] = new_step
        PipelineYaml.model_validate(doc.model_dump())
        return doc

    # ── 2.13 add_step ──

    def add_step(self, doc: PipelineYaml, step: StepYaml, after: str | None = None) -> PipelineYaml:
        """Add a step. `step.browser_ops` accepts YAML format, auto-converted to internal."""
        if step.browser_ops is not None:
            step.browser_ops = self._from_yaml_ops(step.browser_ops)

        for s in doc.steps:
            if s.name == step.name:
                raise ValueError(f"Step '{step.name}' already exists")

        if after is not None:
            insert_idx = None
            for i, s in enumerate(doc.steps):
                if s.name == after:
                    insert_idx = i + 1
                    break
            if insert_idx is None:
                raise ValueError(f"Anchor step '{after}' not found")
            doc.steps.insert(insert_idx, step)
        else:
            doc.steps.append(step)

        PipelineYaml.model_validate(doc.model_dump())
        return doc

    # ── 2.14 remove_step ──

    def remove_step(self, doc: PipelineYaml, name: str) -> PipelineYaml:
        """Remove a step and clean depends_on references in remaining steps."""
        target_idx = None
        for i, s in enumerate(doc.steps):
            if s.name == name:
                target_idx = i
                break
        if target_idx is None:
            raise ValueError(f"Step '{name}' not found")

        doc.steps.pop(target_idx)

        for s in doc.steps:
            if name in s.depends_on:
                s.depends_on = [d for d in s.depends_on if d != name]

        PipelineYaml.model_validate(doc.model_dump())
        return doc
