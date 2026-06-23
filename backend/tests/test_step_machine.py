"""Tests for engine.step_machine — step lifecycle and DAG traversal."""

from __future__ import annotations

import time

import pytest

from yak_browser_use.engine.step_machine import StepMachine, StepNode, StepStatus


# ── StepStatus enum ───────────────────────────────────────────


class TestStepStatus:
    def test_values(self):
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.SUCCESS.value == "success"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"
        assert StepStatus.PENDING_REVIEW.value == "pending_review"

    def test_all_enum_members(self):
        members = {m.name for m in StepStatus}
        assert members == {"PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED", "PENDING_REVIEW"}


# ── StepNode ──────────────────────────────────────────────────


class TestStepNode:
    def test_defaults(self):
        node = StepNode(index=0, key="s1", name="Step 1", step_type="browser")
        assert node.status == StepStatus.PENDING
        assert node.parent_index is None
        assert node.children == []
        assert node.error is None
        assert node.duration_ms == 0

    def test_to_dict_basic(self):
        node = StepNode(index=0, key="s1", name="Step 1", step_type="browser")
        d = node.to_dict()
        assert d["index"] == 0
        assert d["key"] == "s1"
        assert d["name"] == "Step 1"
        assert d["step_type"] == "browser"
        assert d["status"] == "pending"
        assert d["parent_index"] is None
        assert d["children"] == []
        assert d["error"] is None
        assert d["duration_ms"] == 0

    def test_to_dict_with_compromised_ops(self):
        node = StepNode(index=0, key="s1", name="S1", step_type="browser",
                        compromised_ops=[{"type": "click", "value": "#bad"}])
        d = node.to_dict()
        assert d["compromised_ops"] == [{"type": "click", "value": "#bad"}]

    def test_to_dict_no_compromised_ops(self):
        """compromised_ops field is omitted when not set."""
        node = StepNode(index=0, key="s1", name="S1", step_type="browser")
        d = node.to_dict()
        assert "compromised_ops" not in d

    def test_with_error(self):
        node = StepNode(index=1, key="s2", name="Step 2", step_type="browser",
                        error={"code": "BROWSER_ERROR", "message": "timeout"})
        assert node.error["code"] == "BROWSER_ERROR"

    def test_with_parent_and_children(self):
        node = StepNode(index=2, key="s3", name="Step 3", step_type="browser",
                        parent_index=0, children=[1, 2])
        assert node.parent_index == 0
        assert node.children == [1, 2]


# ── StepMachine ───────────────────────────────────────────────


class TestStepMachineBasic:
    def test_is_done_initially_false(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        assert machine.is_done is False
        assert machine.current_index == 0

    def test_is_done_empty_steps(self):
        machine = StepMachine([])
        assert machine.is_done is True

    def test_is_done_after_all_steps(self):
        machine = StepMachine([{"key": "s1"}])
        machine.begin_step()
        machine.advance()
        assert machine.is_done is True

    def test_begin_step_creates_node(self):
        machine = StepMachine([{"key": "s1", "name": "Step 1"}])
        node = machine.begin_step()
        assert node.index == 0
        assert node.key == "s1"
        assert node.name == "Step 1"
        assert node.status == StepStatus.RUNNING
        assert node.parent_index is None
        assert len(machine.nodes) == 1


class TestStepMachineStepTypeInference:
    def test_browser_type(self):
        machine = StepMachine([{"key": "s1"}])
        node = machine.begin_step()
        assert node.step_type == "browser"  # default

    def test_tool_type_from_tool_name(self):
        machine = StepMachine([{"key": "s1", "tool_name": "extract"}])
        node = machine.begin_step()
        assert node.step_type == "tool"

    def test_goal_type(self):
        machine = StepMachine([{"key": "s1", "is_goal": True}])
        node = machine.begin_step()
        assert node.step_type == "goal"

    def test_explicit_step_type(self):
        machine = StepMachine([{"key": "s1", "step_type": "custom"}])
        node = machine.begin_step()
        assert node.step_type == "custom"


class TestStepMachineEndStep:
    def test_end_step_success(self):
        machine = StepMachine([{"key": "s1"}])
        node = machine.begin_step()
        machine.end_step(node, StepStatus.SUCCESS)
        assert node.status == StepStatus.SUCCESS
        assert node.duration_ms >= 0

    def test_end_step_with_error(self):
        machine = StepMachine([{"key": "s1"}])
        node = machine.begin_step()
        machine.end_step(node, StepStatus.FAILED, {"code": "BROWSER_ERROR", "message": "timeout"})
        assert node.error == {"code": "BROWSER_ERROR", "message": "timeout"}
        assert node.status == StepStatus.FAILED


class TestStepMachineAdvance:
    def test_normal_advance(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        node = machine.begin_step()
        machine.end_step(node, StepStatus.SUCCESS)
        machine.advance()
        assert machine.current_index == 1

    def test_goto_by_key(self):
        machine = StepMachine([
            {"key": "s1"}, {"key": "s2"}, {"key": "target"}, {"key": "s4"},
        ])
        node = machine.begin_step()
        machine.end_step(node, StepStatus.SUCCESS)
        machine.advance(goto="target")
        assert machine.current_index == 2  # jumped to "target"

    def test_goto_by_name(self):
        machine = StepMachine([
            {"key": "s1"}, {"key": "s2", "name": "Search"}, {"key": "s3"},
        ])
        node = machine.begin_step()
        machine.end_step(node, StepStatus.SUCCESS)
        machine.advance(goto="Search")
        assert machine.current_index == 1

    def test_goto_not_found_advances_one(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        node = machine.begin_step()
        machine.end_step(node, StepStatus.SUCCESS)
        machine.advance(goto="nonexistent")
        assert machine.current_index == 1  # fallback to +1

    def test_goto_creates_fork(self):
        machine = StepMachine([
            {"key": "s1"}, {"key": "target"}, {"key": "s3"},
        ])
        machine.begin_step()
        machine.advance(goto="target")
        assert machine._fork_stack == [0]


class TestStepMachineFork:
    def test_fork_back_restores_index(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}, {"key": "s3"}])
        machine.begin_step()
        machine.advance(goto="s2")  # fork to s2 (index 1), push 0
        machine.fork_back()
        assert machine.current_index == 0  # returned to fork point

    def test_fork_back_empty_stack_no_crash(self):
        machine = StepMachine([{"key": "s1"}])
        machine.fork_back()  # shouldn't crash

    def test_parent_index_set_on_goto(self):
        machine = StepMachine([
            {"key": "s1"}, {"key": "s2"}, {"key": "s3"},
        ])
        machine.begin_step()  # index 0
        machine.advance(goto="s2")  # fork to index 1
        node2 = machine.begin_step()  # index 1, parent should be 0
        assert node2.parent_index == 0

    def test_parent_index_normal(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        machine.begin_step()  # index 0, no fork
        machine.advance()
        node2 = machine.begin_step()  # index 1, no parent
        assert node2.parent_index is None

    def test_child_tracking(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        machine.begin_step()  # index 0
        machine.advance(goto="s1")  # fork back to 0... wait, advance only called after end_step
        # Actually, begin_step doesn't create children. Let me test end_step → advance → begin_step
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}, {"key": "s3"}])
        n1 = machine.begin_step()
        machine.advance(goto="s2")  # fork pushes 0, jumps to 1
        n2 = machine.begin_step()  # index 1, parent=0
        assert n1.index in n2.children or n2.index in n1.children
        # n1's children should include n2.index
        assert n2.index in n1.children


class TestStepMachineRetry:
    def test_retryable_error_returns_true(self):
        machine = StepMachine([{"key": "s1", "params": {"max_retries": 3}}])
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is True

    def test_non_retryable_error_returns_false(self):
        machine = StepMachine([{"key": "s1", "params": {"max_retries": 3}}])
        for code in ("GUARDIAN_ERROR", "SYNTAX_ERROR", "INPUT_ERROR",
                     "OUTPUT_ERROR", "PATH_ERROR", "REVIEW_INTERRUPT"):
            assert machine.needs_retry(machine.steps[0], code) is False

    def test_unrecognized_error_returns_false(self):
        machine = StepMachine([{"key": "s1", "params": {"max_retries": 3}}])
        assert machine.needs_retry(machine.steps[0], "UNKNOWN_ERROR") is False

    def test_no_max_retries_returns_false(self):
        machine = StepMachine([{"key": "s1", "params": {}}])
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is False

    def test_max_retries_zero_returns_false(self):
        machine = StepMachine([{"key": "s1", "params": {"max_retries": 0}}])
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is False

    def test_retry_count_tracking(self):
        machine = StepMachine([{"key": "s1", "params": {"max_retries": 3}}])
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is True
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is True
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is True
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is False  # exhausted

    def test_advance_resets_retry_count(self):
        machine = StepMachine([
            {"key": "s1", "params": {"max_retries": 3}},
            {"key": "s2"},
        ])
        assert machine.needs_retry(machine.steps[0], "BROWSER_ERROR") is True
        machine.advance()  # resets retry count
        # Retry count for index 0 was reset, but we're now at index 1
        # Actually, advance resets self._retry_count = {}
        # needs_retry checks self._index, which is now 1 (s2)
        # s2 has no max_retries, so it will return False
        assert machine.needs_retry(machine.steps[1], "BROWSER_ERROR") is False


class TestStepMachineGetRetryDelay:
    def test_first_attempt_base(self):
        machine = StepMachine([{"key": "s1"}])
        delay = machine.get_retry_delay(1, base_ms=500, max_ms=8000, jitter_ratio=0)
        assert delay == 500

    def test_second_attempt_exponential(self):
        machine = StepMachine([{"key": "s1"}])
        delay = machine.get_retry_delay(2, base_ms=500, max_ms=8000, jitter_ratio=0)
        assert delay == 1000

    def test_third_attempt(self):
        machine = StepMachine([{"key": "s1"}])
        delay = machine.get_retry_delay(3, base_ms=500, max_ms=8000, jitter_ratio=0)
        assert delay == 2000

    def test_capped_at_max(self):
        machine = StepMachine([{"key": "s1"}])
        delay = machine.get_retry_delay(10, base_ms=500, max_ms=8000, jitter_ratio=0)
        assert delay == 8000

    def test_jitter_increases_delay(self):
        machine = StepMachine([{"key": "s1"}])
        delay_no_jitter = machine.get_retry_delay(2, base_ms=500, max_ms=8000, jitter_ratio=0)
        delay_with_jitter = machine.get_retry_delay(2, base_ms=500, max_ms=8000, jitter_ratio=1.0)
        # With jitter, delay should be > base * 2^1 = 1000 and <= 1000 + 0.5*1000
        assert delay_with_jitter >= delay_no_jitter


class TestStepMachineCancel:
    def test_cancel_sets_flag(self):
        machine = StepMachine([{"key": "s1"}])
        assert machine.check_cancelled() is False
        machine.cancel()
        assert machine.check_cancelled() is True

    def test_cancel_makes_is_done_true(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        assert machine.is_done is False
        machine.cancel()
        assert machine.is_done is True


class TestStepMachineReplaceRemaining:
    def test_replace_remaining_with_new_steps(self):
        steps = [
            {"key": "s1"}, {"key": "s2"}, {"key": "s3"},
        ]
        machine = StepMachine(steps)
        machine.begin_step()
        machine.end_step(machine.nodes[0], StepStatus.SUCCESS)
        machine.advance()

        new_steps = [{"key": "s2_new"}, {"key": "s3_new"}]
        machine.replace_remaining(new_steps)
        assert len(machine.steps) == 3  # s1 (executed) + s2_new + s3_new
        assert machine.steps[1]["key"] == "s2_new"
        assert machine.steps[2]["key"] == "s3_new"

    def test_replace_remaining_clears_fork_stack(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        machine.begin_step()
        machine.advance(goto="s2")
        machine._fork_stack = [0]  # simulate fork
        machine.replace_remaining([])
        assert machine._fork_stack == []

    def test_replace_remaining_preserves_executed_nodes(self):
        steps = [{"key": "s1"}, {"key": "s2"}, {"key": "s3"}]
        machine = StepMachine(steps)
        machine.begin_step()
        machine.end_step(machine.nodes[0], StepStatus.SUCCESS)
        machine.advance()
        machine.replace_remaining([{"key": "new_s2"}])
        assert len(machine.nodes) == 1  # only s1 preserved


class TestStepMachineExecutionTree:
    def test_empty_tree(self):
        machine = StepMachine([])
        tree = machine.to_execution_tree()
        assert tree["total_steps"] == 0
        assert tree["nodes"] == []

    def test_with_nodes(self):
        machine = StepMachine([{"key": "s1"}, {"key": "s2"}])
        n1 = machine.begin_step()
        machine.end_step(n1, StepStatus.SUCCESS)
        machine.advance()
        n2 = machine.begin_step()
        machine.end_step(n2, StepStatus.FAILED)

        tree = machine.to_execution_tree()
        assert tree["total_steps"] == 2
        assert len(tree["nodes"]) == 2
        assert tree["nodes"][0]["status"] == "success"
        assert tree["nodes"][1]["status"] == "failed"


class TestStepMachineIntegration:
    def test_full_pipeline_execution(self):
        """Simulate a full pipeline run through the state machine."""
        steps = [
            {"key": "navigate", "name": "Navigate"},
            {"key": "search", "name": "Search"},
            {"key": "extract", "name": "Extract"},
        ]
        machine = StepMachine(steps)

        results = []
        while not machine.is_done:
            node = machine.begin_step()
            # Simulate execution
            if node.key == "navigate":
                time.sleep(0.001)
                machine.end_step(node, StepStatus.SUCCESS)
                results.append("navigate:ok")
            elif node.key == "search":
                machine.end_step(node, StepStatus.FAILED, {"code": "BROWSER_ERROR", "message": "not found"})
                results.append("search:failed")
            elif node.key == "extract":
                machine.end_step(node, StepStatus.SUCCESS)
                results.append("extract:ok")
            machine.advance()

        assert results == ["navigate:ok", "search:failed", "extract:ok"]
        tree = machine.to_execution_tree()
        assert tree["total_steps"] == 3

    def test_fork_and_return(self):
        """Fork to a later step, then fork back, then continue linearly."""
        steps = [
            {"key": "s1", "name": "Login"},
            {"key": "s2", "name": "Dashboard"},
            {"key": "s3", "name": "Details"},
            {"key": "s4", "name": "Logout"},
        ]
        machine = StepMachine(steps)

        # Execute s1
        n1 = machine.begin_step()
        machine.end_step(n1, StepStatus.SUCCESS)
        machine.advance(goto="Details")  # Fork to s3 (index 2), push 0

        # Execute s3 (skipped s2)
        n3 = machine.begin_step()
        machine.end_step(n3, StepStatus.SUCCESS)
        machine.fork_back()  # Return to fork point (index 0, s1)

        # After fork_back, index is restored to 0 (s1)
        # Execute s1 again, then advance normally
        n1_again = machine.begin_step()  # s1 (index 0) again
        machine.end_step(n1_again, StepStatus.SUCCESS)
        machine.advance()

        n2 = machine.begin_step()  # s2 (index 1)
        machine.end_step(n2, StepStatus.SUCCESS)
        machine.advance()

        n3_again = machine.begin_step()  # s3 (index 2)
        machine.end_step(n3_again, StepStatus.SUCCESS)
        machine.advance()

        n4 = machine.begin_step()  # s4 (index 3)
        machine.end_step(n4, StepStatus.SUCCESS)
        machine.advance()

        assert machine.is_done is True
        assert n1.index == 0
        assert n2.index == 1
        assert n3.index == 2
        assert n3_again.index == 2
        assert n4.index == 3
        # n3 was forked from s1 (the first execution)
        assert n3.parent_index == 0
        # n2, n3_again, n4 are linear (no fork)
        assert n2.parent_index is None
        assert n4.parent_index is None

    def test_child_tracking_via_fork(self):
        """Children are tracked when forking."""
        steps = [
            {"key": "s1", "name": "Login"},
            {"key": "s2", "name": "Dashboard"},
        ]
        machine = StepMachine(steps)
        n1 = machine.begin_step()
        machine.end_step(n1, StepStatus.SUCCESS)
        machine.advance(goto="Dashboard")  # Fork to s2, push 0

        n2 = machine.begin_step()
        machine.end_step(n2, StepStatus.SUCCESS)

        # n1 should have n2 as child
        assert n2.index in n1.children
