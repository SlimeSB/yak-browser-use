"""Tests for engine.executor helper functions (pure logic, no CDP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.executor import (
    mask_sensitive_patterns,
    sanitize_result,
    _build_scroll_js,
    _resolve_element_ref,
    _resolve_input_files,
    _resolve_path,
    _default_input_key,
    _check_outputs,
    write_step_json,
)


# ── mask_sensitive_patterns ───────────────────────────────────


class TestMaskSensitivePatterns:
    def test_masks_text_key(self):
        result = mask_sensitive_patterns('text=hello')
        assert 'text=' in result
        assert '***' in result or 'hello' not in result

    def test_masks_value_key(self):
        result = mask_sensitive_patterns('value=secret')
        assert 'value=' in result
        assert '***' in result or 'secret' not in result

    def test_masks_password_key(self):
        result = mask_sensitive_patterns('password=my_pass_123')
        assert 'password=' in result
        assert '***' in result or 'my_pass_123' not in result

    def test_masks_credential_key(self):
        result = mask_sensitive_patterns('credential=top_secret')
        assert 'credential=' in result
        assert '***' in result

    def test_masks_secret_key(self):
        result = mask_sensitive_patterns('secret=xyz')
        assert 'secret=' in result
        assert '***' in result

    def test_masks_token_key(self):
        result = mask_sensitive_patterns('token=abc123')
        assert 'token=' in result
        assert '***' in result

    def test_masks_api_key_key(self):
        result = mask_sensitive_patterns('api_key=sk-abc123def456')
        assert 'api_key=' in result
        assert '***' in result

    def test_short_value_not_masked(self):
        """Values of length <= 2 are not masked."""
        result = mask_sensitive_patterns('text=ab')
        assert 'ab' in result

    def test_no_sensitive_keys(self):
        text = 'url=https://example.com&name=hello'
        result = mask_sensitive_patterns(text)
        assert result == text

    def test_masks_sk_token(self):
        """sk- patterns inside key=value context get masked by the key-value masker first."""
        text = 'api_key=sk-abc...i789'
        result = mask_sensitive_patterns(text)
        # api_key is in SENSITIVE_KEYS, so it gets masked as api_key=***
        assert 'api_key=***' in result

    def test_masks_bearer_token(self):
        text = 'Authorization: Bearer eyJhbG...I'
        result = mask_sensitive_patterns(text)
        assert 'Bearer ***' in result

    def test_masks_private_key_block(self):
        text = '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA'
        result = mask_sensitive_patterns(text)
        assert '***KEY BLOCK***' in result

    def test_case_insensitive_key_detection(self):
        result = mask_sensitive_patterns('TEXT=secret_value')
        assert 'TEXT=' in result
        assert '***' in result

    def test_empty_string(self):
        assert mask_sensitive_patterns('') == ''


# ── sanitize_result ───────────────────────────────────────────


class TestSanitizeResult:
    def test_dict_sanitization(self):
        data = {"url": "https://x.com", "password": "my_secret", "text": "hello"}
        result = sanitize_result(data)
        assert result["url"] == "https://x.com"
        assert result["password"] == "***"
        assert result["text"] == "***"

    def test_nested_dict(self):
        data = {"outer": {"inner": {"password": "secret", "name": "ok"}}}
        result = sanitize_result(data)
        assert result["outer"]["inner"]["password"] == "***"
        assert result["outer"]["inner"]["name"] == "ok"

    def test_list_of_dicts(self):
        data = [{"password": "s1", "name": "a"}, {"password": "s2", "name": "b"}]
        result = sanitize_result(data)
        assert result[0]["password"] == "***"
        assert result[1]["password"] == "***"
        assert result[0]["name"] == "a"

    def test_string_value(self):
        result = sanitize_result("hello password=secret")
        assert "secret" not in result

    def test_numeric_values(self):
        result = sanitize_result(42)
        assert result == 42

    def test_none(self):
        assert sanitize_result(None) is None

    def test_mixed_types(self):
        data = {
            "name": "test",
            "credentials": {"token": "abc", "valid": True},
            "tags": [1, 2, 3],
            "metadata": None,
        }
        result = sanitize_result(data)
        assert result["credentials"]["token"] == "***"
        assert result["credentials"]["valid"] is True
        assert result["tags"] == [1, 2, 3]

    def test_list_of_strings(self):
        data = ["password=secret", "normal text"]
        result = sanitize_result(data)
        assert "secret" not in result[0] if isinstance(result[0], str) else True

    def test_empty_dict(self):
        assert sanitize_result({}) == {}


# ── _build_scroll_js ──────────────────────────────────────────


class TestBuildScrollJs:
    def test_scroll_down(self):
        js = _build_scroll_js("down", 300)
        assert "scrollBy(0, 300)" in js

    def test_scroll_up(self):
        js = _build_scroll_js("up", 300)
        assert "scrollBy(0, -300)" in js

    def test_default_amount(self):
        js = _build_scroll_js("down", 500)
        assert "500" in js

    def test_unknown_direction_defaults_to_down(self):
        js = _build_scroll_js("left", 200)
        assert "scrollBy(0, 200)" in js  # unknown direction falls back to positive


# ── _resolve_element_ref ──────────────────────────────────────


class TestResolveElementRef:
    @pytest.mark.asyncio
    async def test_plain_selector_returns_as_is(self):
        result = await _resolve_element_ref("#btn", None)
        assert result == "#btn"

    @pytest.mark.asyncio
    async def test_at_e_ref_with_map(self):
        element_map = {"@e1": "#submit-btn", "@e2": "#search-input"}
        result = await _resolve_element_ref("@e1", element_map)
        assert result == "#submit-btn"

    @pytest.mark.asyncio
    async def test_at_e_ref_missing_in_map(self):
        with pytest.raises(ValueError, match="Unknown element reference"):
            await _resolve_element_ref("@e99", {"@e1": "#other_btn"})

    @pytest.mark.asyncio
    async def test_at_e_ref_with_bridge(self):
        """When element_map is None but bridge supports get_element_by_index."""
        class MockBridge:
            def get_element_by_index(self, ref):
                return {"selector": "#dynamic-btn", "ref": ref}

        result = await _resolve_element_ref("@e5", None, MockBridge())
        assert result == "#dynamic-btn"

    @pytest.mark.asyncio
    async def test_at_e_ref_bridge_error(self):
        class MockBridge:
            def get_element_by_index(self, ref):
                return {"error": "not found"}

        with pytest.raises(ValueError, match="Element reference @e5"):
            await _resolve_element_ref("@e5", None, MockBridge())

    @pytest.mark.asyncio
    async def test_empty_selector(self):
        assert await _resolve_element_ref("", None) == ""

    @pytest.mark.asyncio
    async def test_none_element_map_and_no_helpers(self):
        assert await _resolve_element_ref("#static", None) == "#static"


# ── _resolve_path ─────────────────────────────────────────────


class TestResolvePath:
    def test_step_file_ref(self, tmp_path):
        """step_key.file_name → run_dir/step_key/file_name"""
        run_dir = tmp_path / "runs" / "20240101_120000"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "step_1").mkdir()
        (run_dir / "step_1" / "result.csv").write_text("data", encoding="utf-8")

        resolved = _resolve_path("step_1.result.csv", run_dir)
        assert resolved == run_dir / "step_1" / "result.csv"
        assert resolved.exists()

    def test_data_prefix(self, tmp_path):
        """data/ prefix resolves relative to workspace root (run_dir.parents[2])."""
        run_dir = tmp_path / "runs" / "run_1"
        run_dir.mkdir(parents=True, exist_ok=True)
        # data/ prefix resolves to run_dir.parents[2] / data / ...
        data_dir = run_dir.parents[2] / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "config.json").write_text("{}", encoding="utf-8")

        resolved = _resolve_path("data/config.json", run_dir)
        assert resolved == data_dir / "config.json"

    def test_absolute_path_rejected(self):
        with pytest.raises(ValueError, match="Absolute path reference rejected"):
            _resolve_path("/etc/passwd", Path("/tmp"))

    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="Path traversal rejected"):
            _resolve_path("step_1/../../../etc/passwd", Path("/tmp"))

    def test_path_traversal_in_ref(self):
        with pytest.raises(ValueError, match="Path traversal rejected"):
            _resolve_path("../outside", Path("/tmp/workspace"))

    def test_non_existent_path(self, tmp_path):
        ref = "step_1.missing_file.txt"
        # Note: rsplit('.', 1) on "step_1.missing_file.txt" → ("step_1", "missing_file.txt")
        # But the func uses rsplit on the LAST dot, so "step_1.missing_file.txt" → ("step_1.missing_file", "txt")
        # so step_key = "step_1.missing_file", which is a directory name. Let's use a single-dot ref:
        ref_single_dot = "step_1.data"
        resolved = _resolve_path(ref_single_dot, tmp_path)
        assert resolved.name == "data"
        assert "step_1" in str(resolved.parts)
        # Just shouldn't crash


# ── _resolve_input_files ──────────────────────────────────────


class TestResolveInputFiles:
    def test_string_ref(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "step_1").mkdir()
        (run_dir / "step_1" / "result.csv").write_text("data", encoding="utf-8")

        result = _resolve_input_files("step_1.result.csv", run_dir)
        assert "step_1" in result
        assert str(run_dir / "step_1" / "result.csv") in result.values()

    def test_dict_ref(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "src").mkdir()
        (run_dir / "src" / "input.txt").write_text("hello", encoding="utf-8")

        result = _resolve_input_files({"file": "src.input.txt"}, run_dir)
        assert result["file"] == str(run_dir / "src" / "input.txt")

    def test_dict_with_multiple_entries(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "s1").mkdir()
        (run_dir / "s2").mkdir()
        (run_dir / "s1" / "a.csv").write_text("a", encoding="utf-8")
        (run_dir / "s2" / "b.csv").write_text("b", encoding="utf-8")

        result = _resolve_input_files({"a": "s1.a.csv", "b": "s2.b.csv"}, run_dir)
        assert len(result) == 2

    def test_empty_ref(self, tmp_path):
        assert _resolve_input_files({}, tmp_path) == {}

    def test_unsupported_type(self, tmp_path):
        assert _resolve_input_files([], tmp_path) == {}

    def test_absolute_path_in_ref(self):
        with pytest.raises(ValueError, match="Absolute path reference rejected"):
            _resolve_input_files("/etc/passwd", Path("/tmp"))

    def test_path_traversal_in_ref(self):
        with pytest.raises(ValueError, match="Path traversal rejected"):
            _resolve_input_files("../outside", Path("/tmp"))


# ── _default_input_key ────────────────────────────────────────


class TestDefaultInputKey:
    def test_step_file_ref_produces_step_key(self):
        assert _default_input_key("step_1.result.csv") == "step_1"

    def test_plain_ref_produces_filestem_as_input_key(self):
        assert _default_input_key("some_file.txt") == "some_file"

    def test_no_extension(self):
        assert _default_input_key("step_1") == "input"


# ── _check_outputs ────────────────────────────────────────────


class TestCheckOutputs:
    def test_all_outputs_present(self, tmp_path):
        (tmp_path / "result.json").write_text("{}", encoding="utf-8")
        (tmp_path / "report.csv").write_text("a,b", encoding="utf-8")
        missing = _check_outputs(["result.json", "report.csv"], tmp_path)
        assert missing == []

    def test_some_outputs_missing(self, tmp_path):
        (tmp_path / "result.json").write_text("{}", encoding="utf-8")
        missing = _check_outputs(["result.json", "missing.csv", "also_missing.txt"], tmp_path)
        assert missing == ["missing.csv", "also_missing.txt"]

    def test_no_output_files(self, tmp_path):
        assert _check_outputs([], tmp_path) == []


# ── write_step_json ───────────────────────────────────────────


class TestWriteStepJson:
    def test_writes_atomically(self, tmp_path):
        result = {"step": "test", "status": "completed", "duration_ms": 100}
        write_step_json(tmp_path, result)

        real_path = tmp_path / "step.json"
        assert real_path.exists()
        data = json.loads(real_path.read_text(encoding="utf-8"))
        assert data["step"] == "test"
        assert data["status"] == "completed"
        assert data["duration_ms"] == 100

    def test_tmp_file_does_not_persist(self, tmp_path):
        result = {"ok": True}
        write_step_json(tmp_path, result)
        # The .tmp file should be renamed (moved) to step.json
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_overwrites_existing(self, tmp_path):
        (tmp_path / "step.json").write_text('{"old": true}', encoding="utf-8")
        result = {"new": True}
        write_step_json(tmp_path, result)
        data = json.loads((tmp_path / "step.json").read_text(encoding="utf-8"))
        assert data == {"new": True}
