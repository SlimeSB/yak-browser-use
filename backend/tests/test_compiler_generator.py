"""Tests for compiler.generator — handler generation, action→ops mapping, write-back."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from yak_browser_use.compiler.models import StepDef
from yak_browser_use.compiler.generator import (
    _extract_python_code,
    _cache_generated_handler,
    compile_handler_code,
    extract_selectors,
    _model_action_to_op,
    model_actions_to_ops,
    generate_handler_prompt,
    write_pipeline_learned,
    _get_action_name,
    _get_action_params,
    _get_interacted_element,
    _get_bounds,
)


# ── _extract_python_code ──────────────────────────────────────


class TestExtractPythonCode:
    def test_with_fence(self):
        text = "Here's the code:\n```python\ndef handle():\n    pass\n```\nEnd"
        code = _extract_python_code(text)
        assert "def handle():" in code
        assert "pass" in code

    def test_fence_without_language(self):
        text = "```\ndef handle():\n    return 42\n```"
        code = _extract_python_code(text)
        assert "return 42" in code

    def test_already_clean_code(self):
        text = "async def handle():\n    return 'hello'"
        code = _extract_python_code(text)
        assert code == text

    def test_no_python_code(self):
        text = "Just a plain text response."
        assert _extract_python_code(text) == ""

    def test_with_def_main(self):
        text = "```python\ndef main():\n    print('hello')\n```"
        code = _extract_python_code(text)
        assert "main()" in code

    def test_multiple_fences_takes_first(self):
        text = "```python\nx = 1\n```\nmore\n```python\ny = 2\n```"
        code = _extract_python_code(text)
        assert "x = 1" in code
        assert "y = 2" not in code

    def test_empty_fence(self):
        text = "```python\n```"
        assert _extract_python_code(text) == ""


# ── compile_handler_code ──────────────────────────────────────


class TestCompileHandlerCode:
    def test_compile_handle_function(self):
        code = """
def handle(param1, param2=None):
    return {"result": param1}
"""
        fn = compile_handler_code(code)
        assert fn is not None
        assert callable(fn)
        assert fn("test", param2="x") == {"result": "test"}

    def test_compile_main_function(self):
        code = """
def main(input_files, output_dir):
    return {"ok": True}
"""
        fn = compile_handler_code(code)
        assert fn is not None
        assert callable(fn)
        assert fn({}, ".") == {"ok": True}

    def test_compile_run_function(self):
        code = """
def run(context):
    return context
"""
        fn = compile_handler_code(code)
        assert fn is not None
        assert fn(42) == 42

    def test_async_handle_function(self):
        code = """
async def handle(url):
    return {"url": url}
"""
        fn = compile_handler_code(code)
        assert fn is not None
        import asyncio
        result = asyncio.run(fn("https://x.com"))
        assert result == {"url": "https://x.com"}

    def test_syntax_error_in_code(self):
        code = "def handle():\n  bad syntax @@@\n"
        assert compile_handler_code(code) is None

    def test_no_recognized_entry_point(self):
        code = """
def helper():
    return 42
"""
        assert compile_handler_code(code) is None

    def test_empty_code(self):
        assert compile_handler_code("") is None


# ── extract_selectors ─────────────────────────────────────────


class MockElement:
    """Minimal mock for browser-use DOM element."""

    def __init__(self, attributes=None, ax_name="", x_path="", bounds=None):
        self.attributes = attributes or {}
        self.ax_name = ax_name
        self.x_path = x_path
        self.bounds = bounds


class TestExtractSelectors:
    def test_with_id(self):
        el = MockElement(attributes={"id": "submit-btn"})
        selectors = extract_selectors(el)
        assert "#submit-btn" in selectors

    def test_with_data_testid(self):
        el = MockElement(attributes={"data-testid": "login-button"})
        selectors = extract_selectors(el)
        assert "[data-testid='login-button']" in selectors

    def test_with_ax_name(self):
        el = MockElement(ax_name="Login Button")
        selectors = extract_selectors(el)
        assert "Login Button" in selectors

    def test_with_xpath(self):
        el = MockElement(x_path="//button[@id='submit']")
        selectors = extract_selectors(el)
        assert "//button[@id='submit']" in selectors

    def test_multiple_selectors(self):
        el = MockElement(
            attributes={"id": "btn", "data-testid": "submit"},
            ax_name="Submit",
            x_path="//button[@id='btn']",
        )
        selectors = extract_selectors(el)
        assert len(selectors) >= 3

    def test_none_element(self):
        assert extract_selectors(None) == []

    def test_no_attributes(self):
        el = MockElement()
        assert extract_selectors(el) == []


# ── _get_action_name / _get_action_params / _get_interacted_element / _get_bounds ──

class MockAction:
    def __init__(self, action_name="", params=None, interacted_element=None):
        self.action_name = action_name
        self.params = params or {}
        self.interacted_element = interacted_element


class TestGetActionName:
    def test_object_with_action_name(self):
        action = MockAction(action_name="click")
        assert _get_action_name(action) == "click"

    def test_dict_action(self):
        assert _get_action_name({"action_name": "navigate"}) == "navigate"

    def test_dict_with_type(self):
        assert _get_action_name({"type": "click"}) == "click"

    def test_empty_action(self):
        assert _get_action_name({}) == ""

    def test_no_name(self):
        assert _get_action_name(MockAction()) == ""


class TestGetActionParams:
    def test_object_with_params(self):
        action = MockAction(params={"url": "https://x.com"})
        assert _get_action_params(action) == {"url": "https://x.com"}

    def test_object_none_params(self):
        action = MockAction()
        action.params = None
        assert _get_action_params(action) == {}

    def test_dict_action(self):
        action = {"type": "click", "selector": "#btn", "interacted_element": None}
        params = _get_action_params(action)
        assert params == {"selector": "#btn"}

    def test_empty_action(self):
        assert _get_action_params({}) == {}


class TestGetInteractedElement:
    def test_object(self):
        el = MockElement(ax_name="test")
        action = MockAction(interacted_element=el)
        assert _get_interacted_element(action) is el

    def test_dict(self):
        el = {"tag": "button"}
        action = {"interacted_element": el}
        assert _get_interacted_element(action) == el

    def test_none(self):
        assert _get_interacted_element(MockAction()) is None


class MockBounds:
    def __init__(self, x=0, y=0, width=100, height=50):
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class TestGetBounds:
    def test_object_bounds(self):
        el = MockElement()
        el.bounds = MockBounds(x=10, y=20, width=200, height=100)
        bounds = _get_bounds(el)
        assert bounds == [10, 20, 200, 100]

    def test_tuple_bounds(self):
        el = MockElement()
        el.bounds = (5, 10, 50, 25)
        bounds = _get_bounds(el)
        assert bounds == [5, 10, 50, 25]

    def test_list_bounds(self):
        el = MockElement()
        el.bounds = [1, 2, 3, 4]
        bounds = _get_bounds(el)
        assert bounds == [1, 2, 3, 4]

    def test_none_bounds(self):
        assert _get_bounds(None) is None

    def test_no_bounds_attr(self):
        el = MockElement()  # no bounds set
        assert _get_bounds(el) is None


# ── _model_action_to_op ───────────────────────────────────────


class TestModelActionToOp:
    def test_navigate_action(self):
        action = MockAction(action_name="navigate", params={"url": "https://example.com"})
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "goto"
        assert op["value"] == "https://example.com"

    def test_click_action(self):
        el = MockElement(attributes={"id": "btn"}, x_path="//button[@id='btn']")
        action = MockAction(action_name="click", params={}, interacted_element=el)
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "click"
        assert "#btn" in op["selectors"]

    def test_input_action(self):
        el = MockElement(attributes={"id": "search-input"})
        action = MockAction(action_name="input", params={"text": "hello"}, interacted_element=el)
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "fill"
        assert op["value"] == "hello"

    def test_scroll_action(self):
        action = MockAction(action_name="scroll", params={"amount": 500})
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "js"
        assert "scrollBy" in op["code"]
        assert "500" in op["code"]

    def test_go_back_action(self):
        action = MockAction(action_name="go_back")
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "js"
        assert "history.back" in op["code"]

    def test_wait_action(self):
        action = MockAction(action_name="wait")
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "wait_for_network"

    def test_done_action_returns_none(self):
        action = MockAction(action_name="done")
        assert _model_action_to_op(action) is None

    def test_unknown_action_returns_none(self):
        action = MockAction(action_name="unknown_action")
        assert _model_action_to_op(action) is None

    def test_no_action_name(self):
        assert _model_action_to_op(MockAction()) is None

    def test_dict_action_navigate(self):
        action = {"action_name": "navigate", "url": "https://x.com", "interacted_element": None}
        op = _model_action_to_op(action)
        assert op is not None
        assert op["type"] == "goto"


# ── model_actions_to_ops ──────────────────────────────────────


class TestModelActionsToOps:
    def test_multiple_actions(self):
        el = MockElement(attributes={"id": "btn"})
        actions = [
            MockAction(action_name="navigate", params={"url": "https://x.com"}),
            MockAction(action_name="click", params={}, interacted_element=el),
            MockAction(action_name="done"),
        ]
        ops = model_actions_to_ops(actions)
        assert len(ops) == 2
        assert ops[0]["type"] == "goto"
        assert ops[1]["type"] == "click"

    def test_empty_actions(self):
        assert model_actions_to_ops([]) == []

    def test_all_done_returns_empty(self):
        actions = [MockAction(action_name="done"), MockAction(action_name="done")]
        assert model_actions_to_ops(actions) == []


# ── generate_handler_prompt ───────────────────────────────────


class TestGenerateHandlerPrompt:
    def test_generates_prompt(self):
        step_def = StepDef(
            key="s1", name="Extract data",
            description="Extract table from page",
            browser_ops=[{"type": "goto", "value": "https://x.com"}],
            input_schema={"url": "str"},
            output_schema={"result": "str"},
            depends_on=[],
        )
        prompt = generate_handler_prompt(step_def)
        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "Extract data" in prompt
        assert "s1" in prompt or "step_info" in prompt or "step_yaml" in prompt.lower()

    def test_prompt_contains_step_info(self):
        step_def = StepDef(key="s1", name="Test")
        prompt = generate_handler_prompt(step_def)
        # Should contain JSON-ish step definition
        assert "s1" in prompt or "step" in prompt.lower()


# ── write_pipeline_learned ────────────────────────────────────


class TestWritePipelineLearned:
    SAMPLE_YAML = """name: test_pipe
steps:
  - name: step_1
    browser_ops:
      - goto: https://old-url.com
  - name: step_2
    tool_name: extract
"""

    def test_update_existing_step(self):
        new_ops = [{"type": "goto", "value": "https://new-url.com"}]
        result = write_pipeline_learned(self.SAMPLE_YAML, "step_1", new_ops)
        assert "https://new-url.com" in result
        assert "https://old-url.com" not in result

    def test_step_not_found_returns_original(self):
        result = write_pipeline_learned(self.SAMPLE_YAML, "nonexistent", [{"type": "goto"}])
        assert result == self.SAMPLE_YAML

    def test_invalid_yaml_string(self):
        """A non-dict YAML value returns original."""
        result = write_pipeline_learned("plain string", "step_1", [])
        assert result == "plain string"

    def test_non_dict_root(self):
        result = write_pipeline_learned("[]", "step_1", [])
        assert result == "[]"

    def test_missing_steps_key(self):
        result = write_pipeline_learned("name: test\nother: data", "step_1", [])
        assert "name: test" in result

    def test_preserves_other_steps(self):
        new_ops = [{"type": "goto", "value": "https://new.com"}]
        result = write_pipeline_learned(self.SAMPLE_YAML, "step_1", new_ops)
        data = yaml.safe_load(result)
        assert len(data["steps"]) == 2  # still 2 steps
        assert data["steps"][1]["tool_name"] == "extract"  # step_2 preserved


# ── _cache_generated_handler ──────────────────────────────────


class TestCacheGeneratedHandler:
    def test_writes_handler_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _cache_generated_handler("test_pipe", "step_1", "def handle(): pass")
        cache_path = tmp_path / "generated" / "test_pipe" / "step_1.py"
        assert cache_path.exists()
        assert cache_path.read_text(encoding="utf-8") == "def handle(): pass"

    def test_creates_directories(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _cache_generated_handler("deep/nested/pipe", "s1", "code")
        assert (tmp_path / "generated" / "deep/nested/pipe" / "s1.py").exists()
