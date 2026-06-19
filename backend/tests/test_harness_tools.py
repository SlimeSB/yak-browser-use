"""Tests for tools registration module — via ToolRegistry."""

from tools.registry import registry, build_registry


def _ensure_registry():
    if not registry._tools:
        build_registry()


def _browser_tools():
    _ensure_registry()
    return [t for t in registry.get_schemas() if t["function"]["name"].startswith("browser_")]


def _pipeline_tools():
    _ensure_registry()
    return [t for t in registry.get_schemas() if t["function"]["name"].startswith("pipeline_")]


def test_browser_tools_count():
    assert len(_browser_tools()) == 20


def test_browser_tools_structure():
    for tool in _browser_tools():
        assert "type" in tool
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert fn["name"].startswith("browser_")
        assert "description" in fn
        assert "parameters" in fn


def test_goal_run_tool():
    _ensure_registry()
    goal_run = next((t for t in registry.get_schemas() if t["function"]["name"] == "goal_run"), None)
    assert goal_run is not None
    assert goal_run["function"]["name"] == "goal_run"
    assert "description" in goal_run["function"]["parameters"]["properties"]


def test_pipeline_tools_count():
    assert len(_pipeline_tools()) == 8


def test_pipeline_tools_names():
    names = [t["function"]["name"] for t in _pipeline_tools()]
    assert "pipeline_load" in names
    assert "pipeline_list" in names
    assert "pipeline_update_step" in names
    assert "pipeline_add_step" in names
    assert "pipeline_remove_step" in names
    assert "pipeline_create" in names


def test_get_all_tools_with_goal():
    from engine._harness.tools import get_all_tools

    tools = get_all_tools(include_goal_run=True)
    assert len(tools) == 40
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
    assert "browser_get_element_by_number" in names
    assert "edit_pipeline" not in names
    assert "todo" in names


def test_get_all_tools_without_goal():
    from engine._harness.tools import get_all_tools

    tools = get_all_tools(include_goal_run=False)
    assert len(tools) == 39
    names = [t["function"]["name"] for t in tools]
    assert "goal_run" not in names
    assert "edit_pipeline" not in names
    assert "pipeline_load" in names


def test_get_browser_tools():
    from engine._harness.tools import get_browser_tools

    tools = get_browser_tools()
    assert len(tools) == 20
    names = [t["function"]["name"] for t in tools]
    assert "browser_goto" in names
    assert "browser_click" in names
    assert "browser_fill" in names
    assert "browser_snapshot" in names
    assert "browser_scroll" in names
    assert "browser_source" in names
    assert "browser_eval" in names
    assert "browser_get_element_by_number" in names


def test_todo_tool_definition():
    from engine._harness.tools import get_all_tools

    tools = get_all_tools(include_goal_run=True)
    todo_tool = next((t for t in tools if t["function"]["name"] == "todo"), None)
    assert todo_tool is not None
    assert todo_tool["type"] == "function"
    fn = todo_tool["function"]
    assert "todos" in fn["parameters"]["properties"]
    assert "merge" in fn["parameters"]["properties"]
    assert fn["parameters"]["properties"]["merge"]["type"] == "boolean"
    assert fn["parameters"]["properties"]["todos"]["type"] == "array"
