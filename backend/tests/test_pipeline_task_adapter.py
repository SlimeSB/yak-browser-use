"""Tests for pipeline_task_adapter module."""

from engine._harness.pipeline_task_adapter import (
    StepInfo,
    TaskDescriptor,
    PipelineTaskAdapter,
)


def test_step_info_defaults():
    si = StepInfo(key="s1", name="Step 1", description="do something")
    assert si.key == "s1"
    assert si.status == "pending"


def test_task_descriptor_progress():
    td = TaskDescriptor(
        pipeline_name="test",
        goal="test goal",
        steps=[
            StepInfo(key="s1", name="S1", status="completed"),
            StepInfo(key="s2", name="S2", status="pending"),
        ],
    )
    assert td.total == 2
    assert td.completed == 1
    assert td.progress == "1/2"


def test_task_descriptor_format():
    td = TaskDescriptor(
        pipeline_name="test-pipeline",
        goal="test goal",
        steps=[
            StepInfo(key="s1", name="Step 1", description="do first", status="pending"),
            StepInfo(key="s2", name="Step 2", description="do second", status="pending"),
        ],
    )
    formatted = td.format()
    assert "test-pipeline" in formatted
    assert "test goal" in formatted
    assert "0/2" in formatted
    assert "[待完成] Step 1: do first" in formatted
    assert "[待完成] Step 2: do second" in formatted


def test_task_descriptor_to_dict():
    td = TaskDescriptor(
        pipeline_name="test",
        goal="goal",
        steps=[StepInfo(key="s1", name="S1")],
    )
    d = td.to_dict()
    assert d["pipeline_name"] == "test"
    assert d["goal"] == "goal"
    assert len(d["steps"]) == 1
    assert d["progress"] == "0/1"


def test_pipeline_task_adapter_basic():
    step_defs = [
        {"key": "s1", "name": "Navigate", "step_type": "browser", "browser_ops": []},
        {"key": "s2", "name": "Extract", "tool_name": "extract_table", "step_type": "tool"},
        {"key": "s3", "name": "Goal", "is_goal": True, "goal_description": "find best"},
    ]
    frontmatter = {"name": "my-pipeline", "goal": "complete task"}
    adapter = PipelineTaskAdapter(step_defs, frontmatter)
    td = adapter.build_descriptor()

    assert td.pipeline_name == "my-pipeline"
    assert td.goal == "complete task"
    assert td.total == 3
    assert td.steps[0].step_type == "browser"
    assert td.steps[1].step_type == "tool"
    assert td.steps[2].step_type == "goal"


def test_pipeline_task_adapter_no_frontmatter():
    step_defs = [{"key": "s1", "name": "Step 1"}]
    adapter = PipelineTaskAdapter(step_defs)
    td = adapter.build_descriptor()
    assert td.pipeline_name == "unnamed_pipeline"
    assert td.goal == ""


def test_task_descriptor_empty():
    td = TaskDescriptor(pipeline_name="empty")
    assert td.total == 0
    assert td.completed == 0
    assert td.progress == "0/0"
    formatted = td.format()
    assert "empty" in formatted
