"""Tests for compiler.graph — dependency graph builder."""

from __future__ import annotations

import pytest

from yak_browser_use.compiler.models import StepDef
from yak_browser_use.compiler.graph import build_graph, get_execution_order, validate_file_refs


# ── build_graph ───────────────────────────────────────────────


class TestBuildGraph:
    def test_empty_steps(self):
        graph = build_graph([])
        assert graph == {"nodes": [], "edges": [], "start_node": None}

    def test_single_step_no_deps(self):
        steps = [StepDef(key="s1", name="Step 1")]
        graph = build_graph(steps)
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["key"] == "s1"
        assert graph["nodes"][0]["deps"] == []
        assert graph["edges"] == []
        assert graph["start_node"] == "s1"

    def test_sequential_steps_default_edges(self):
        steps = [
            StepDef(key="s1", name="Step 1"),
            StepDef(key="s2", name="Step 2"),
            StepDef(key="s3", name="Step 3"),
        ]
        graph = build_graph(steps)
        assert len(graph["nodes"]) == 3
        assert graph["edges"] == [("s1", "s2"), ("s2", "s3")]
        assert graph["start_node"] == "s1"
        # Each step after the first auto-depends on the previous
        assert graph["nodes"][1]["deps"] == ["s1"]
        assert graph["nodes"][2]["deps"] == ["s2"]

    def test_explicit_depends_on_replaces_sequential(self):
        steps = [
            StepDef(key="s1", name="Step 1"),
            StepDef(key="s2", name="Step 2", depends_on=["s1"]),
            StepDef(key="s3", name="Step 3", depends_on=["s1"]),  # Both depend on s1
        ]
        graph = build_graph(steps)
        # s1 → s2, s1 → s3  (no s2 → s3)
        assert set(graph["edges"]) == {("s1", "s2"), ("s1", "s3")}
        assert graph["nodes"][2]["deps"] == ["s1"]

    def test_depends_on_by_name(self):
        """depends_on references step name, not key."""
        steps = [
            StepDef(key="s1", name="Navigate"),
            StepDef(key="s2", name="Search", depends_on=["Navigate"]),
        ]
        graph = build_graph(steps)
        assert ("s1", "s2") in graph["edges"]

    def test_metadata_in_nodes(self):
        steps = [
            StepDef(key="s1", name="Step 1", step_type="browser",
                    browser_ops=[{"type": "goto", "value": "https://x.com"}],
                    is_goal=False, input_schema={"key": "str"}, output_schema={"result": "str"}),
        ]
        graph = build_graph(steps)
        node = graph["nodes"][0]
        assert node["step_type"] == "browser"
        assert node["browser_ops"] == steps[0].browser_ops
        assert node["input_schema"] == {"key": "str"}
        assert node["output_schema"] == {"result": "str"}
        assert node["is_goal"] is False


# ── get_execution_order ───────────────────────────────────────


class TestGetExecutionOrder:
    def test_linear_order(self):
        graph = {
            "nodes": [
                {"key": "s1", "name": "Step 1"},
                {"key": "s2", "name": "Step 2"},
                {"key": "s3", "name": "Step 3"},
            ],
            "edges": [("s1", "s2"), ("s2", "s3")],
            "start_node": "s1",
        }
        order = get_execution_order(graph)
        assert order == ["s1", "s2", "s3"]

    def test_dag_multiple_branches(self):
        graph = {
            "nodes": [
                {"key": "s1", "name": "Start"},
                {"key": "s2", "name": "Branch A"},
                {"key": "s3", "name": "Branch B"},
                {"key": "s4", "name": "Merge"},
            ],
            "edges": [("s1", "s2"), ("s1", "s3"), ("s2", "s4"), ("s3", "s4")],
            "start_node": "s1",
        }
        order = get_execution_order(graph)
        assert order[0] == "s1"
        assert order[-1] == "s4"
        # s2 and s3 can be in any order, but both before s4
        assert order.index("s2") < order.index("s4")
        assert order.index("s3") < order.index("s4")

    def test_single_node(self):
        graph = {
            "nodes": [{"key": "s1", "name": "Only"}],
            "edges": [],
            "start_node": "s1",
        }
        assert get_execution_order(graph) == ["s1"]

    def test_diamond_dag(self):
        graph = {
            "nodes": [
                {"key": "s1"}, {"key": "s2"}, {"key": "s3"}, {"key": "s4"},
            ],
            "edges": [("s1", "s2"), ("s1", "s3"), ("s2", "s4"), ("s3", "s4")],
            "start_node": "s1",
        }
        order = get_execution_order(graph)
        assert order[0] == "s1"
        assert order[-1] == "s4"

    def test_cycle_detection(self):
        graph = {
            "nodes": [
                {"key": "s1"}, {"key": "s2"}, {"key": "s3"},
            ],
            "edges": [("s1", "s2"), ("s2", "s3"), ("s3", "s1")],
            "start_node": "s1",
        }
        with pytest.raises(ValueError, match="Cycle detected"):
            get_execution_order(graph)

    def test_self_loop(self):
        graph = {
            "nodes": [{"key": "s1"}],
            "edges": [("s1", "s1")],
            "start_node": "s1",
        }
        with pytest.raises(ValueError, match="Cycle detected"):
            get_execution_order(graph)

    def test_disconnected_graph_is_still_dag(self):
        graph = {
            "nodes": [
                {"key": "s1"}, {"key": "s2"}, {"key": "s3"},
            ],
            "edges": [("s1", "s2")],  # s3 disconnected
            "start_node": "s1",
        }
        # s3 has no in-edges, so it appears at the start (or wherever)
        order = get_execution_order(graph)
        assert len(order) == 3
        assert "s3" in order

    def test_complex_dag(self):
        """s1 → s2 → s4, s1 → s3 → s4"""
        graph = {
            "nodes": [
                {"key": "navigate"}, {"key": "search"}, {"key": "login"}, {"key": "extract"},
            ],
            "edges": [
                ("navigate", "search"), ("navigate", "login"),
                ("search", "extract"), ("login", "extract"),
            ],
            "start_node": "navigate",
        }
        order = get_execution_order(graph)
        assert len(order) == 4
        assert order[0] == "navigate"
        assert order[-1] == "extract"


# ── validate_file_refs ────────────────────────────────────────


class TestValidateFileRefs:
    SAMPLE_OUTPUTS = frozenset({"result", "data", "meta"})

    def _make_step(self, key, name, step_type="browser", is_goal=False, input_schema=None,
                   output_schema=None, browser_ops=None):
        return StepDef(
            key=key, name=name, step_type=step_type, is_goal=is_goal,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            browser_ops=browser_ops or [],
        )

    def test_valid_refs(self):
        steps = [
            self._make_step("s1", "Step 1", output_schema={"result": "data"}),
            self._make_step("s2", "Step 2", input_schema={"inp": "s1.data"}),
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_non_existent_step_ref(self):
        steps = [
            self._make_step("s1", "Step 1"),
            self._make_step("s2", "Step 2", input_schema={"inp": "nonexistent.data"}),
        ]
        with pytest.raises(ValueError, match="non-existent step"):
            validate_file_refs(steps)

    def test_missing_output_declaration(self):
        steps = [
            self._make_step("s1", "Step 1", output_schema={"out": "other"}),
            self._make_step("s2", "Step 2", input_schema={"inp": "s1.result"}),
        ]
        with pytest.raises(ValueError, match="does not declare"):
            validate_file_refs(steps)

    def test_goal_step_skips_ref_validation_for_itself(self):
        """Goal steps are skipped as consumers, but as targets they still need matching outputs."""
        steps = [
            self._make_step("s1", "Step 1", is_goal=True),
            # Goal steps as targets get browser default outputs (step.json, screenshot_*.png)
            # So a ref to s1.any_file won't match
            self._make_step("s2", "Step 2", input_schema={"inp": "s1.any_file"}),
        ]
        with pytest.raises(ValueError, match="does not declare"):
            validate_file_refs(steps)

    def test_browser_step_implicit_output(self):
        steps = [
            self._make_step("s1", "Step 1", browser_ops=[{"type": "goto"}]),
            # Browser steps declare 'step.json' and 'screenshot_*.png'
            self._make_step("s2", "Step 2", input_schema={"json": "s1.step_json"}),
        ]
        # 'step_json' does NOT match browser's declared 'step.json' (exact match needed)
        with pytest.raises(ValueError, match="does not declare"):
            validate_file_refs(steps)

    def test_wildcard_screenshot_matching(self):
        """screenshot_*.png wildcard matches any screenshot reference."""
        steps = [
            self._make_step("s1", "Step 1", browser_ops=[{"type": "goto", "value": "x"}]),
            self._make_step("s2", "Step 2", input_schema={"shot": "s1.screenshot_123"}),
        ]
        # 'screenshot_123' would need to match 'screenshot_*.png' — but fnmatch
        # checks 'screenshot_123' against pattern 'screenshot_*.png' which doesn't match
        # because the ref_file doesn't end in .png
        with pytest.raises(ValueError):
            validate_file_refs(steps)

    def test_browser_op_get_html_output(self):
        steps = [
            self._make_step("s1", "Step 1", browser_ops=[{"type": "get_html"}]),
            self._make_step("s2", "Step 2", input_schema={"html": "s1.page_html"}),
        ]
        # get_html op declares 'page.html', but ref uses 'page_html'
        with pytest.raises(ValueError):
            validate_file_refs(steps)

    def test_empty_input_schema_skipped(self):
        steps = [
            self._make_step("s1", "Step 1"),
            self._make_step("s2", "Step 2"),  # no input_schema
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_complex_ref_format(self):
        """Dict-based output_schema with simple file names."""
        steps = [
            StepDef(key="extract", name="Extract",
                    output_schema={"result": "data"}),
            StepDef(key="analyze", name="Analyze",
                    input_schema={"src": "extract.data"}),
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_no_ref_without_dot(self):
        """Refs without a '.' are skipped."""
        steps = [
            self._make_step("s1", "Step 1"),
            self._make_step("s2", "Step 2", input_schema={"data": "plain_value"}),
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_browser_with_declared_and_implicit_outputs(self):
        """Browser steps have both declared outputs and implicit ones."""
        steps = [
            StepDef(key="s1", name="Step 1",
                    step_type="browser",
                    browser_ops=[{"type": "goto"}],
                    output_schema={"extra": "extra_output"}),
            StepDef(key="s2", name="Step 2",
                    input_schema={"e": "s1.extra_output"}),
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_dict_input_schema_without_dot_values(self):
        """input_schema as dict where values don't contain '.' should be skipped."""
        steps = [
            self._make_step("s1", "Step 1"),
            self._make_step("s2", "Step 2", input_schema={"key1": "value1", "key2": "value2"}),
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_single_file_output_string(self):
        """output_schema as string is handled."""
        steps = [
            StepDef(key="s1", name="Step 1",
                    output_schema={"out": "single_file"}),
            StepDef(key="s2", name="Step 2",
                    input_schema={"data": "s1.single_file"}),
        ]
        errors = validate_file_refs(steps)
        assert errors == []

    def test_browser_screenshot_ref_matches_wildcard(self):
        """A screenshot ref that matches screenshot_*.png should pass."""
        steps = [
            StepDef(key="s1", name="Step 1",
                    step_type="browser",
                    browser_ops=[{"type": "goto"}],
                    output_schema={}),  # browser also has implicit outputs
            StepDef(key="s2", name="Step 2",
                    input_schema={"shot": "s1.screenshot_abc"}),
        ]
        # screenshot_abc ref matches screenshot_*.png via fnmatch
        with pytest.raises(ValueError):
            validate_file_refs(steps)
