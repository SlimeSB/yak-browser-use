"""Tests for tools registration module — via ToolRegistry."""

from yak_browser_use.tools.registry import registry, build_registry


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
    assert len(_browser_tools()) >= 20


def test_browser_tools_structure():
    for tool in _browser_tools():
        assert "type" in tool
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert fn["name"].startswith("browser_")
        assert "description" in fn
        assert "parameters" in fn


def test_pipeline_tools_count():
    assert len(_pipeline_tools()) == 7


def test_pipeline_tools_names():
    names = [t["function"]["name"] for t in _pipeline_tools()]
    assert "pipeline_view" in names
    assert "pipeline_update_step" in names
    assert "pipeline_add_step" in names
    assert "pipeline_remove_step" in names
    assert "pipeline_create" in names


def test_todo_tool_definition():
    from yak_browser_use.engine._harness.tools import get_all_tools

    tools = get_all_tools()
    todo_tool = next((t for t in tools if t["function"]["name"] == "todo"), None)
    assert todo_tool is not None
    assert todo_tool["type"] == "function"
    fn = todo_tool["function"]
    assert "todos" in fn["parameters"]["properties"]
    assert "merge" in fn["parameters"]["properties"]
    assert fn["parameters"]["properties"]["merge"]["type"] == "boolean"
    assert fn["parameters"]["properties"]["todos"]["type"] == "array"
