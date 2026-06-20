"""Unit tests for _param_resolver.py — resolve_params function."""

import pytest
from engine._param_resolver import resolve_params


class TestResolveParams:
    """Core resolve_params behaviour."""

    def test_no_templates_returns_deep_copy(self):
        params = {"a": 1, "b": "hello"}
        resolved, errors = resolve_params(params, {})
        assert resolved == params
        assert resolved is not params
        assert errors == []

    def test_simple_template_replacement(self):
        store = {"step_a": {"data": {"text": "hello world"}}}
        params = {"content": "${step_a.data.text}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == "hello world"
        assert errors == []

    def test_template_in_dict_value(self):
        store = {"s1": {"data": {"path": "/tmp/out.csv"}}}
        params = {"file": {"path": "${s1.data.path}"}}
        resolved, errors = resolve_params(params, store)
        assert resolved["file"]["path"] == "/tmp/out.csv"
        assert errors == []

    def test_template_in_list(self):
        store = {"a": {"data": {"x": "1"}}, "b": {"data": {"y": "2"}}}
        params = {"items": ["${a.data.x}", "${b.data.y}"]}
        resolved, errors = resolve_params(params, store)
        assert resolved["items"] == ["1", "2"]
        assert errors == []

    def test_source_key_replacement(self):
        store = {"extracted": {"ok": True, "data": {"rows": [1, 2, 3]}}}
        params = {"content": {"_source_key": "extracted"}}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == {"rows": [1, 2, 3]}
        assert errors == []

    def test_source_key_not_found(self):
        params = {"content": {"_source_key": "missing"}}
        resolved, errors = resolve_params(params, {})
        assert resolved["content"] == "__RESOLVE_FAILED__:missing.data"
        assert "missing.data" in errors

    def test_path_not_found(self):
        params = {"x": "${bad.path}"}
        resolved, errors = resolve_params(params, {})
        assert resolved["x"] == "__RESOLVE_FAILED__:bad.path"
        assert "bad.path" in errors

    def test_partial_failure_other_paths_ok(self):
        store = {"a": {"data": {"ok": "yes"}}}
        params = {"good": "${a.data.ok}", "bad": "${missing.x}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["good"] == "yes"
        assert resolved["bad"] == "__RESOLVE_FAILED__:missing.x"
        assert errors == ["missing.x"]

    def test_original_params_not_modified(self):
        store = {"s": {"data": {"v": 42}}}
        params = {"x": "${s.data.v}"}
        original = dict(params)
        resolve_params(params, store)
        assert params == original

    def test_empty_shared_store(self):
        params = {"x": "${a.b}"}
        resolved, errors = resolve_params(params, {})
        assert resolved["x"] == "__RESOLVE_FAILED__:a.b"
        assert errors == ["a.b"]

    def test_none_shared_store(self):
        params = {"x": "${a.b}"}
        resolved, errors = resolve_params(params, None)
        assert resolved["x"] == "__RESOLVE_FAILED__:a.b"
        assert errors == ["a.b"]

    def test_nested_5_levels(self):
        store = {"l1": {"data": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}}
        params = {"v": "${l1.data.l2.l3.l4.l5}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["v"] == "deep"
        assert errors == []

    def test_non_string_values_preserved(self):
        store = {"s": {"data": {"n": 42, "f": 3.14, "b": True, "null": None}}}
        params = {"n": "${s.data.n}", "f": "${s.data.f}", "b": "${s.data.b}", "null": "${s.data.null}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["n"] == 42
        assert resolved["f"] == 3.14
        assert resolved["b"] is True
        assert resolved["null"] is None
        assert errors == []

    def test_source_key_preserves_type(self):
        store = {"t": {"ok": True, "data": {"items": [1, 2, 3]}}}
        params = {"content": {"_source_key": "t"}}
        resolved, errors = resolve_params(params, store)
        assert isinstance(resolved["content"], dict)
        assert resolved["content"] == {"items": [1, 2, 3]}

    def test_source_key_list_value(self):
        store = {"t": {"ok": True, "data": [10, 20, 30]}}
        params = {"content": {"_source_key": "t"}}
        resolved, errors = resolve_params(params, store)
        assert isinstance(resolved["content"], list)
        assert resolved["content"] == [10, 20, 30]

    def test_source_key_str_value(self):
        store = {"t": {"ok": True, "data": "plain text"}}
        params = {"content": {"_source_key": "t"}}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == "plain text"

    def test_recursive_dict_resolution(self):
        store = {"a": {"data": {"x": "1"}}, "b": {"data": {"y": "2"}}}
        params = {"outer": {"inner": {"v1": "${a.data.x}", "v2": "${b.data.y}"}}}
        resolved, errors = resolve_params(params, store)
        assert resolved["outer"]["inner"]["v1"] == "1"
        assert resolved["outer"]["inner"]["v2"] == "2"

    def test_recursive_list_in_dict(self):
        store = {"a": {"data": {"x": "1"}}}
        params = {"items": [{"v": "${a.data.x}"}, {"v": "static"}]}
        resolved, errors = resolve_params(params, store)
        assert resolved["items"][0]["v"] == "1"
        assert resolved["items"][1]["v"] == "static"

    def test_nested_template_not_resolved(self):
        store = {"a": {"data": {"b": "c"}}}
        params = {"x": "${${a.data.b}.d}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["x"] == "${${a.data.b}.d}"

    def test_empty_string_no_template(self):
        params = {"x": ""}
        resolved, errors = resolve_params(params, {})
        assert resolved["x"] == ""
        assert errors == []

    def test_none_value_in_params(self):
        params = {"x": None, "y": "${a.b}"}
        resolved, errors = resolve_params(params, {})
        assert resolved["x"] is None
        assert resolved["y"] == "__RESOLVE_FAILED__:a.b"

    def test_multiple_source_keys(self):
        store = {
            "k1": {"ok": True, "data": "v1"},
            "k2": {"ok": True, "data": "v2"},
        }
        params = {"a": {"_source_key": "k1"}, "b": {"_source_key": "k2"}}
        resolved, errors = resolve_params(params, store)
        assert resolved["a"] == "v1"
        assert resolved["b"] == "v2"
        assert errors == []

    def test_source_key_nested_in_dict(self):
        store = {"t": {"ok": True, "data": {"rows": 5}}}
        params = {"outer": {"inner": {"_source_key": "t"}}}
        resolved, errors = resolve_params(params, store)
        assert resolved["outer"]["inner"] == {"rows": 5}

    def test_mixed_template_and_source_key(self):
        store = {
            "s1": {"ok": True, "data": "hello"},
            "s2": {"data": {"name": "world"}},
        }
        params = {"a": {"_source_key": "s1"}, "b": "${s2.data.name}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["a"] == "hello"
        assert resolved["b"] == "world"
        assert errors == []
