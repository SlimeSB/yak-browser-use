"""Tests for compiler.resolver — three-tier handler resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from yak_browser_use.compiler.resolver import resolve, resolve_with_generator, _load_handler_from_file
from yak_browser_use.compiler.models import StepDef


# ── _load_handler_from_file ───────────────────────────────────


class TestLoadHandlerFromFile:
    def test_load_handle_function(self, tmp_path):
        pyfile = tmp_path / "handler.py"
        pyfile.write_text(
            "def handle(input_files, output_dir):\n"
            '    return {"ok": True}\n',
            encoding="utf-8",
        )
        handler = _load_handler_from_file(pyfile)
        assert handler is not None
        assert callable(handler)
        assert handler({}, ".") == {"ok": True}

    def test_load_main_function(self, tmp_path):
        pyfile = tmp_path / "handler.py"
        pyfile.write_text(
            "def main(ctx):\n"
            "    return ctx\n",
            encoding="utf-8",
        )
        handler = _load_handler_from_file(pyfile)
        assert handler is not None
        assert handler(42) == 42

    def test_load_run_function(self, tmp_path):
        pyfile = tmp_path / "handler.py"
        pyfile.write_text(
            'def run():\n    return "done"\n',
            encoding="utf-8",
        )
        handler = _load_handler_from_file(pyfile)
        assert handler is not None
        assert handler() == "done"

    def test_no_recognized_function(self, tmp_path):
        pyfile = tmp_path / "handler.py"
        pyfile.write_text(
            "def helper():\n    pass\n",
            encoding="utf-8",
        )
        handler = _load_handler_from_file(pyfile)
        assert handler is None

    def test_file_not_found(self):
        handler = _load_handler_from_file(Path("/nonexistent/path.py"))
        assert handler is None

    def test_syntax_error(self, tmp_path):
        pyfile = tmp_path / "bad.py"
        pyfile.write_text("def handle():\n  bad syntax @@@\n", encoding="utf-8")
        handler = _load_handler_from_file(pyfile)
        assert handler is None

    def test_async_handle_function(self, tmp_path):
        pyfile = tmp_path / "async_handler.py"
        pyfile.write_text(
            "async def handle(url):\n"
            '    return {"url": url}\n',
            encoding="utf-8",
        )
        handler = _load_handler_from_file(pyfile)
        assert handler is not None
        import asyncio
        result = asyncio.run(handler("https://x.com"))
        assert result == {"url": "https://x.com"}

    def test_handle_takes_precedence_over_main(self, tmp_path):
        """If both handle() and main() exist, handle() is returned."""
        pyfile = tmp_path / "precedence.py"
        pyfile.write_text(
            "def handle():\n"
            '    return "from_handle"\n'
            "\n"
            "def main():\n"
            '    return "from_main"\n',
            encoding="utf-8",
        )
        handler = _load_handler_from_file(pyfile)
        assert handler is not None
        assert handler() == "from_handle"


# ── resolve ───────────────────────────────────────────────────


class TestResolve:
    def test_tier1_static_handler(self, tmp_path, monkeypatch):
        """Static handler in tasks/<pipeline>/handlers/<step_key>.py"""
        monkeypatch.setattr("yak_browser_use.compiler.resolver.TASKS_DIR", tmp_path)
        handler_dir = tmp_path / "test_pipe" / "handlers"
        handler_dir.mkdir(parents=True, exist_ok=True)
        (handler_dir / "step_1.py").write_text(
            "def handle():\n    return 'static'\n",
            encoding="utf-8",
        )
        step = StepDef(key="step_1", name="Step 1")
        handler = resolve(step, "test_pipe")
        assert handler is not None
        assert handler() == "static"

    def test_tier1_legacy_exec_py(self, tmp_path, monkeypatch):
        """Legacy format: tasks/<pipeline>/exec.py"""
        monkeypatch.setattr("yak_browser_use.compiler.resolver.TASKS_DIR", tmp_path)
        exec_dir = tmp_path / "test_pipe"
        exec_dir.mkdir(parents=True, exist_ok=True)
        (exec_dir / "exec.py").write_text(
            "def handle():\n    return 'legacy'\n",
            encoding="utf-8",
        )
        step = StepDef(key="step_1", name="Step 1")
        handler = resolve(step, "test_pipe")
        assert handler is not None
        assert handler() == "legacy"

    def test_tier2_generated_handler(self, tmp_path, monkeypatch):
        """Generated handler in generated/<pipeline>/<step_key>.py"""
        monkeypatch.chdir(tmp_path)
        gen_dir = tmp_path / "generated" / "test_pipe"
        gen_dir.mkdir(parents=True, exist_ok=True)
        (gen_dir / "step_1.py").write_text(
            "def handle():\n    return 'generated'\n",
            encoding="utf-8",
        )
        step = StepDef(key="step_1", name="Step 1")
        handler = resolve(step, "test_pipe")
        assert handler is not None
        assert handler() == "generated"

    def test_tier3_none_when_no_handler(self, tmp_path, monkeypatch):
        """No handler found anywhere → returns None."""
        monkeypatch.setattr("yak_browser_use.compiler.resolver.TASKS_DIR", tmp_path)
        monkeypatch.chdir(tmp_path)
        step = StepDef(key="nonexistent", name="No Handler")
        handler = resolve(step, "test_pipe")
        assert handler is None

    def test_tier1_precedes_tier2(self, tmp_path, monkeypatch):
        """Static handler takes priority over generated."""
        monkeypatch.setattr("yak_browser_use.compiler.resolver.TASKS_DIR", tmp_path)
        monkeypatch.chdir(tmp_path)
        # Tier 1
        handler_dir = tmp_path / "test_pipe" / "handlers"
        handler_dir.mkdir(parents=True, exist_ok=True)
        (handler_dir / "step_1.py").write_text(
            "def handle():\n    return 'tier1'\n",
            encoding="utf-8",
        )
        # Tier 2
        gen_dir = tmp_path / "generated" / "test_pipe"
        gen_dir.mkdir(parents=True, exist_ok=True)
        (gen_dir / "step_1.py").write_text(
            "def handle():\n    return 'tier2'\n",
            encoding="utf-8",
        )
        step = StepDef(key="step_1", name="Step 1")
        handler = resolve(step, "test_pipe")
        assert handler is not None
        assert handler() == "tier1"


# ── resolve_with_generator ────────────────────────────────────


class TestResolveWithGenerator:
    def test_with_generate_fn_fallback(self):
        """When resolve returns None, generate_fn is called."""
        step = StepDef(key="s1", name="Step 1")

        def fake_generate(sd, pn):
            return lambda: f"generated:{sd.key}:{pn}"

        handler = resolve_with_generator(step, "test_pipe", generate_fn=fake_generate)
        assert handler is not None
        assert handler() == "generated:s1:test_pipe"

    def test_generate_fn_called_only_on_missing(self):
        """If Tier 1 resolves, generate_fn should not be called."""
        step = StepDef(key="s1", name="Step 1")
        resolve(step, "nonexistent")  # won't be found, so generate_fn will be called
        called = False

        def fake_generate(sd, pn):
            nonlocal called
            called = True
            return lambda: "fallback"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("yak_browser_use.compiler.resolver.TASKS_DIR", Path("/tmp/nonexistent_tasks"))
            mp.chdir(Path("/tmp"))
            handler = resolve_with_generator(step, "missing_pipe", generate_fn=fake_generate)
            # The handler should be from generate_fn since resolve returned None
            assert handler is not None
            assert handler() == "fallback"
            assert called

    def test_no_generate_fn_returns_none(self):
        step = StepDef(key="s1", name="Step 1")
        handler = resolve_with_generator(step, "nonexistent")
        assert handler is None
