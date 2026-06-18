"""Integration tests for _inline_generate_and_execute."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.runner_preset import (
    _build_tool_shell,
    _extract_code_from_response,
    _inline_generate_and_execute,
)


# ── _extract_code_from_response ──


def test_extract_code_markdown_block():
    completion = """Here is the code:

```python
    result = await ctx.evaluate("document.title")
    return {"ok": True}
```

That should work."""
    code = _extract_code_from_response(completion)
    assert 'result = await ctx.evaluate("document.title")' in code
    assert "```" not in code


def test_extract_code_no_fence():
    completion = 'result = await ctx.evaluate("x")\nreturn {"ok": True}'
    code = _extract_code_from_response(completion)
    assert code == completion


def test_extract_code_empty():
    assert _extract_code_from_response("") == ""


# ── _build_tool_shell ──


def test_build_tool_shell():
    code = _build_tool_shell("my_func", '    """doc."""\n    return {"ok": True}')
    assert "async def my_func(ctx: ToolContext, params: dict) -> dict:" in code
    assert "from engine.ops import ToolContext" in code
    assert 'return {"ok": True}' in code


# ── _inline_generate_and_execute ──


class FakeLLMResponse:
    def __init__(self, completion: str):
        self.completion = completion
        self.content = completion
        self.tool_calls = None


@pytest.fixture
def tools_dir(tmp_path):
    d = tmp_path / "tools"
    d.mkdir()
    return d


@pytest.fixture
def step_dir(tmp_path):
    d = tmp_path / "step"
    d.mkdir()
    return d


@pytest.fixture
def prompt_template_path(tmp_path):
    prompts_dir = tmp_path / "prompts" / "tool_gen"
    prompts_dir.mkdir(parents=True)
    tmpl = prompts_dir / "generate.md"
    tmpl.write_text("""{func_name}

{page_state}

{task_description}
""", encoding="utf-8")
    return tmpl


@pytest.fixture
def mock_cdp():
    cdp = MagicMock()
    cdp.capture_snapshot_simplified = AsyncMock(return_value={"summary": "<div>test</div>"})
    cdp.js = AsyncMock(return_value="https://example.com")
    return cdp


@pytest.fixture
def mock_llm():
    return AsyncMock(return_value=FakeLLMResponse(
        '```python\n    """Test tool."""\n    return {"ok": True}\n```'
    ))


@pytest.mark.asyncio
async def test_inline_generate_success(
    tools_dir, step_dir, mock_cdp, mock_llm, prompt_template_path
):
    result = await _inline_generate_and_execute(
        tool_name="_PH-test-tool",
        pipeline_name="test_pipeline",
        tools_dir=tools_dir,
        cdp_helpers=mock_cdp,
        llm_call=mock_llm,
        step_dir=step_dir,
        prompt_template_path=prompt_template_path,
    )
    assert result["status"] == "completed"
    assert result["upgraded"] is True


@pytest.mark.asyncio
async def test_inline_generate_retry_on_safety_fail(
    tools_dir, step_dir, mock_cdp, prompt_template_path
):
    call_count = [0]

    async def mock_llm_call(messages, tools):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeLLMResponse("```python\nimport os\n```")
        else:
            return FakeLLMResponse('```python\n    """ok."""\n    return {"ok": True}\n```')

    result = await _inline_generate_and_execute(
        tool_name="_PH-test-tool",
        pipeline_name="test_pipeline",
        tools_dir=tools_dir,
        cdp_helpers=mock_cdp,
        llm_call=mock_llm_call,
        step_dir=step_dir,
        prompt_template_path=prompt_template_path,
    )
    assert result["status"] == "completed"
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_inline_generate_max_retries(
    tools_dir, step_dir, mock_cdp, prompt_template_path
):
    async def failing_llm(messages, tools):
        return FakeLLMResponse("```python\nimport os\n```")

    result = await _inline_generate_and_execute(
        tool_name="_PH-test-tool",
        pipeline_name="test_pipeline",
        tools_dir=tools_dir,
        cdp_helpers=mock_cdp,
        llm_call=failing_llm,
        step_dir=step_dir,
        prompt_template_path=prompt_template_path,
    )
    assert result["status"] == "failed"
    assert "3" in result["error"]["message"]


@pytest.mark.asyncio
async def test_inline_generate_function_name_convention(
    tools_dir, step_dir, mock_cdp, mock_llm, prompt_template_path
):
    result = await _inline_generate_and_execute(
        tool_name="_PH-crack-captcha",
        pipeline_name="test_pipeline",
        tools_dir=tools_dir,
        cdp_helpers=mock_cdp,
        llm_call=mock_llm,
        step_dir=step_dir,
        prompt_template_path=prompt_template_path,
    )
    assert result["status"] == "completed"
    assert result["upgraded_name"] == "crack-captcha"
