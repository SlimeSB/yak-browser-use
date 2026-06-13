"""Tests for tools registration module."""

from engine._harness.tools import (
    BROWSER_TOOLS,
    GOAL_RUN_TOOL,
    PIPELINE_TOOLS,
    get_all_tools,
    get_browser_tools,
)


def test_browser_tools_count():
    assert len(BROWSER_TOOLS) == 7


def test_browser_tools_structure():
    for tool in BROWSER_TOOLS:
        assert "type" in tool
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert fn["name"].startswith("browser_")
        assert "description" in fn
        assert "parameters" in fn


def test_goal_run_tool():
    assert GOAL_RUN_TOOL["function"]["name"] == "goal_run"
    assert "description" in GOAL_RUN_TOOL["function"]["parameters"]["properties"]


def test_pipeline_tools_count():
    assert len(PIPELINE_TOOLS) == 6


def test_pipeline_tools_names():
    names = [t["function"]["name"] for t in PIPELINE_TOOLS]
    assert "pipeline_load" in names
    assert "pipeline_list" in names
    assert "pipeline_update_step" in names
    assert "pipeline_add_step" in names
    assert "pipeline_remove_step" in names
    assert "pipeline_create" in names


def test_get_all_tools_with_goal():
    tools = get_all_tools(include_goal_run=True)
    assert len(tools) == 15
    names = [t["function"]["name"] for t in tools]
    assert "browser_goto" in names
    assert "goal_run" in names
    assert "pipeline_load" in names
    assert "pipeline_list" in names
    assert "pipeline_update_step" in names
    assert "pipeline_add_step" in names
    assert "pipeline_remove_step" in names
    assert "pipeline_create" in names
    assert "record_step" in names
    assert "edit_pipeline" not in names


def test_get_all_tools_without_goal():
    tools = get_all_tools(include_goal_run=False)
    assert len(tools) == 14
    names = [t["function"]["name"] for t in tools]
    assert "goal_run" not in names
    assert "edit_pipeline" not in names
    assert "pipeline_load" in names


def test_get_browser_tools():
    tools = get_browser_tools()
    assert len(tools) == 7
    names = [t["function"]["name"] for t in tools]
    assert "browser_goto" in names
    assert "browser_click" in names
    assert "browser_fill" in names
    assert "browser_snapshot" in names
    assert "browser_scroll" in names
    assert "browser_source" in names
    assert "browser_eval" in names
