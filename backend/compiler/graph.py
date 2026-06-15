"""
graph.py — Dependency graph builder for pipeline.yaml step pipelines.

Builds a DAG from step definitions, performs topological sort,
detects cycles, and validates file reference integrity.
"""
from __future__ import annotations

import fnmatch
from typing import Any

from compiler.models import StepDef
from utils.logging import get_logger

logger = get_logger(__name__)


def build_graph(steps: list[StepDef]) -> dict[str, Any]:
    """Build a DAG from pipeline.yaml step definitions.

    Returns a dict representation of the graph:
        {
            "nodes": [{"key": ..., "name": ..., "deps": [...]}, ...],
            "edges": [(from_key, to_key), ...],
            "start_node": key or None,
        }

    Edge inference rules:
    1. Explicit depends_on → edges from declared deps.
    2. No depends_on → sequential edge from previous step.
    3. First step with no deps becomes start node.
    """
    if not steps:
        return {"nodes": [], "edges": [], "start_node": None}

    nodes: list[dict] = []
    edges: list[tuple[str, str]] = []
    start_node: str | None = None

    name_to_key: dict[str, str] = {}
    for step in steps:
        name_to_key[step.name] = step.key

    for i, step in enumerate(steps):
        deps: list[str] = []
        if step.depends_on:
            for dep_name in step.depends_on:
                dep_key = name_to_key.get(dep_name, dep_name)
                deps.append(dep_key)
                edges.append((dep_key, step.key))
        elif i > 0:
            prev_key = steps[i - 1].key
            deps.append(prev_key)
            edges.append((prev_key, step.key))

        nodes.append({
            "key": step.key,
            "name": step.name,
            "deps": deps,
            "step_type": step.step_type,
            "browser_ops": step.browser_ops,
            "input_schema": step.input_schema,
            "output_schema": step.output_schema,
            "is_goal": step.is_goal,
        })

    if nodes:
        start_node = nodes[0]["key"]

    return {
        "nodes": nodes,
        "edges": edges,
        "start_node": start_node,
    }


def get_execution_order(graph: dict) -> list[str]:
    """Return topologically sorted execution order of step keys.

    Uses Kahn's algorithm. Raises ValueError if a cycle is detected.
    """
    nodes = {n["key"]: n for n in graph["nodes"]}
    edges = graph["edges"]

    in_degree: dict[str, int] = {key: 0 for key in nodes}
    adjacency: dict[str, list[str]] = {key: [] for key in nodes}

    for src, dst in edges:
        adjacency[src].append(dst)
        in_degree[dst] = in_degree.get(dst, 0) + 1

    queue = [key for key, deg in in_degree.items() if deg == 0]
    order: list[str] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in adjacency.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        remaining = set(nodes) - set(order)
        raise ValueError(f"Cycle detected: steps with circular dependencies: {remaining}")

    return order


def validate_file_refs(steps: list) -> list[str]:
    """Validate file references between steps.

    Checks that every '<step_key>.<file>' reference in input_schema
    points to a step that declares that file in its output_schema.
    Goal steps are skipped.

    Returns a list of error messages (empty if valid).
    Raises ValueError if issues are found.
    """
    step_map = {s.key: s for s in steps}

    BROWSER_KNOWN_OUTPUTS = {"step.json"}
    BROWSER_OPS_OUTPUTS = {
        "get_html": "page.html",
    }

    def _browser_outputs(step) -> set[str]:
        outputs = set(BROWSER_KNOWN_OUTPUTS)
        if hasattr(step, "browser_ops") and step.browser_ops:
            for op in step.browser_ops:
                op_type = op.get("type") if isinstance(op, dict) else getattr(op, "type", None)
                if op_type in BROWSER_OPS_OUTPUTS:
                    outputs.add(BROWSER_OPS_OUTPUTS[op_type])
        outputs.add("screenshot_*.png")
        return outputs

    missing: list[str] = []

    for step in steps:
        # Skip goal steps
        if getattr(step, "is_goal", False) or getattr(step, "step_type", "") == "goal":
            continue
        if not hasattr(step, "input_schema") or not step.input_schema:
            continue

        input_refs = step.input_schema
        if isinstance(input_refs, dict):
            refs = list(input_refs.values()) if any("." in str(v) for v in input_refs.values()) else []
        elif isinstance(input_refs, list):
            refs = input_refs
        elif isinstance(input_refs, str):
            refs = [input_refs]
        else:
            refs = []

        for ref in refs:
            ref_str = str(ref)
            if "." not in ref_str:
                continue

            parts = ref_str.rsplit(".", 1)
            if len(parts) != 2:
                continue

            ref_step_key, ref_file = parts

            if ref_step_key not in step_map:
                missing.append(
                    f"Step '{step.name}' references non-existent step "
                    f"'{ref_step_key}' (file: {ref_file})"
                )
                continue

            target = step_map[ref_step_key]

            declared_outputs: set[str] = set()
            if hasattr(target, "output_schema") and target.output_schema:
                if isinstance(target.output_schema, list):
                    declared_outputs = set(str(o) for o in target.output_schema)
                elif isinstance(target.output_schema, str):
                    declared_outputs = {target.output_schema}
                elif isinstance(target.output_schema, dict):
                    declared_outputs = set(str(v) for v in target.output_schema.values())

            if getattr(target, "is_goal", False) or getattr(target, "browser_ops", None):
                declared_outputs |= _browser_outputs(target)

            found = False
            for declared in declared_outputs:
                if declared == ref_file:
                    found = True
                    break
                if "*" in declared:
                    if fnmatch.fnmatch(ref_file, declared):
                        found = True
                        break

            if not found:
                missing.append(
                    f"Step '{step.name}' references file '{ref_file}', "
                    f"but step '{ref_step_key}' does not declare it in output"
                )

    if missing:
        msg = f"File reference validation failed ({len(missing)} issues):\n"
        for item in missing:
            msg += f"  - {item}\n"
        raise ValueError(msg)

    return missing
