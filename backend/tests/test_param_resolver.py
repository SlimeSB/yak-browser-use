"""Unit tests for _param_resolver.py — resolve_params function."""

import pytest
from engine._param_resolver import resolve_params


class TestResolveParams:
    """Core resolve_params behaviour."""

    # ── basic invariants ──────────────────────────────────────────────

    def test_no_templates_returns_deep_copy(self):
        params = {"a": 1, "b": "hello"}
        resolved, errors = resolve_params(params, {})
        assert resolved == params
        assert resolved is not params
        assert errors == []

    def test_original_params_not_modified(self):
        store = {"s": {"v": 42}}
        params = {"x": "${s.v}"}
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

    # ── {path} fullmatch — primary syntax ─────────────────────────────

    def test_path_basic(self):
        store = {"step_3": "hello world"}
        params = {"content": "{step_3}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == "hello world"
        assert errors == []

    def test_path_nested(self):
        store = {"step_3": {"rows": [1, 2, 3]}}
        params = {"content": "{step_3}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == {"rows": [1, 2, 3]}
        assert errors == []

    def test_path_dotted(self):
        store = {"step_3": {"result": "done"}}
        params = {"content": "{step_3.result}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == "done"
        assert errors == []

    def test_path_not_found(self):
        params = {"content": "{missing}"}
        resolved, errors = resolve_params(params, {})
        assert resolved["content"] == "__RESOLVE_FAILED__:missing"
        assert "missing" in errors

    def test_path_list_value(self):
        store = {"t": [10, 20, 30]}
        params = {"content": "{t}"}
        resolved, errors = resolve_params(params, store)
        assert isinstance(resolved["content"], list)
        assert resolved["content"] == [10, 20, 30]

    def test_path_str_value(self):
        store = {"t": "plain text"}
        params = {"content": "{t}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == "plain text"

    def test_path_none_value_returns_none(self):
        store = {"t": None}
        params = {"content": "{t}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] is None
        assert errors == []

    def test_path_nested_in_dict(self):
        store = {"t": {"rows": 5}}
        params = {"outer": {"inner": "{t}"}}
        resolved, errors = resolve_params(params, store)
        assert resolved["outer"]["inner"] == {"rows": 5}

    def test_multiple_path_refs(self):
        store = {"k1": "v1", "k2": "v2"}
        params = {"a": "{k1}", "b": "{k2}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["a"] == "v1"
        assert resolved["b"] == "v2"
        assert errors == []

    def test_path_fullmatch_only_not_partial(self):
        store = {"key": "value"}
        params = {"url": "https://x.com/{key}/view"}
        resolved, errors = resolve_params(params, store)
        assert resolved["url"] == "https://x.com/{key}/view"
        assert errors == []

    def test_path_not_matching_json_braces(self):
        params = {"x": '{"a": 1}'}
        resolved, errors = resolve_params(params, {})
        assert resolved["x"] == '{"a": 1}'
        assert errors == []

    # ── ${path} fullmatch — whole-string template ────────────────────

    def test_template_simple_fullmatch(self):
        store = {"step_a": {"text": "hello world"}}
        params = {"content": "${step_a.text}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["content"] == "hello world"
        assert errors == []

    def test_template_nested_5_levels(self):
        store = {"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}
        params = {"v": "${l1.l2.l3.l4.l5}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["v"] == "deep"
        assert errors == []

    def test_template_fullmatch_not_found(self):
        params = {"x": "${bad.path}"}
        resolved, errors = resolve_params(params, {})
        assert resolved["x"] == "__RESOLVE_FAILED__:bad.path"
        assert "bad.path" in errors

    def test_template_preserves_non_string_types(self):
        store = {"s": {"n": 42, "f": 3.14, "b": True, "null": None}}
        params = {
            "n": "${s.n}", "f": "${s.f}",
            "b": "${s.b}", "null": "${s.null}",
        }
        resolved, errors = resolve_params(params, store)
        assert resolved["n"] == 42
        assert resolved["f"] == 3.14
        assert resolved["b"] is True
        assert resolved["null"] is None
        assert errors == []

    def test_template_nested_not_resolved(self):
        store = {"a": {"b": "c"}}
        params = {"x": "${${a.b}.d}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["x"] == "${${a.b}.d}"

    # ── ${path} sub — partial template replacement ────────────────────

    def test_sub_basic(self):
        store = {"host": "example.com"}
        params = {"url": "https://${host}/api"}
        resolved, errors = resolve_params(params, store)
        assert resolved["url"] == "https://example.com/api"
        assert errors == []

    def test_sub_multiple_occurrences(self):
        store = {"a": "1"}
        params = {"x": "${a}${a}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["x"] == "11"
        assert errors == []

    def test_sub_not_found_keeps_placeholder(self):
        store = {"host": "example.com"}
        params = {"url": "https://${host}/${nonexistent}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["url"] == "https://example.com/${nonexistent}"
        assert errors == ["nonexistent"]

    def test_sub_non_string_type_error_keeps_placeholder(self):
        store = {"a": "ok", "b": {"nested": True}}
        params = {"x": "${a}${b}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["x"] == "ok${b}"
        assert errors == ["b"]

    def test_sub_partial_failure_other_paths_ok(self):
        store = {"a": "yes"}
        params = {"good": "prefix ${a}", "bad": "prefix ${missing.x}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["good"] == "prefix yes"
        assert resolved["bad"] == "prefix ${missing.x}"
        assert errors == ["missing.x"]

    def test_sub_list_value_error(self):
        store = {"a": [1, 2, 3]}
        params = {"x": "prefix ${a} suffix"}
        resolved, errors = resolve_params(params, store)
        assert resolved["x"] == "prefix ${a} suffix"
        assert errors == ["a"]

    # ── mixed {path} and ${path} ─────────────────────────────────────

    def test_mixed_path_and_template(self):
        store = {"s1": "hello", "s2": {"name": "world"}}
        params = {"a": "{s1}", "b": "${s2.name}"}
        resolved, errors = resolve_params(params, store)
        assert resolved["a"] == "hello"
        assert resolved["b"] == "world"
        assert errors == []

    def test_mixed_path_and_sub(self):
        store = {"k": "val", "host": "x.com"}
        params = {"a": "{k}", "b": "https://${host}/path"}
        resolved, errors = resolve_params(params, store)
        assert resolved["a"] == "val"
        assert resolved["b"] == "https://x.com/path"
        assert errors == []

    def test_dollar_template_in_string_not_fullmatch(self):
        store = {"k": "replaced"}
        params = {"a": "prefix ${k} suffix"}
        resolved, errors = resolve_params(params, store)
        assert resolved["a"] == "prefix replaced suffix"
        assert errors == []

    # ── recursive resolution ──────────────────────────────────────────

    def test_recursive_dict_resolution(self):
        store = {"a": "1", "b": "2"}
        params = {"outer": {"inner": {"v1": "{a}", "v2": "{b}"}}}
        resolved, errors = resolve_params(params, store)
        assert resolved["outer"]["inner"]["v1"] == "1"
        assert resolved["outer"]["inner"]["v2"] == "2"

    def test_recursive_list_in_dict(self):
        store = {"a": "1"}
        params = {"items": [{"v": "{a}"}, {"v": "static"}]}
        resolved, errors = resolve_params(params, store)
        assert resolved["items"][0]["v"] == "1"
        assert resolved["items"][1]["v"] == "static"

    def test_template_in_list(self):
        store = {"a": "1", "b": "2"}
        params = {"items": ["${a}", "${b}"]}
        resolved, errors = resolve_params(params, store)
        assert resolved["items"] == ["1", "2"]
        assert errors == []

    # ── back-compat: {path} replacing old _source_key ─────────────────

    def test_path_equivalent_to_old_source_key(self):
        bare_store = {"extracted": {"rows": [1, 2, 3]}}
        params = {"content": "{extracted}"}
        resolved, errors = resolve_params(params, bare_store)
        assert resolved["content"] == {"rows": [1, 2, 3]}
        assert errors == []

    def test_path_equivalent_to_old_source_key_nested(self):
        bare_store = {"t": {"rows": 5}}
        params = {"outer": {"inner": "{t}"}}
        resolved, errors = resolve_params(params, bare_store)
        assert resolved["outer"]["inner"] == {"rows": 5}

    def test_path_equivalent_to_old_source_key_str(self):
        bare_store = {"t": "plain text"}
        params = {"content": "{t}"}
        resolved, errors = resolve_params(params, bare_store)
        assert resolved["content"] == "plain text"

    def test_path_equivalent_to_old_source_key_list(self):
        bare_store = {"t": [10, 20, 30]}
        params = {"content": "{t}"}
        resolved, errors = resolve_params(params, bare_store)
        assert resolved["content"] == [10, 20, 30]

    def test_path_equivalent_to_old_source_key_not_found(self):
        params = {"content": "{missing}"}
        resolved, errors = resolve_params(params, {})
        assert resolved["content"] == "__RESOLVE_FAILED__:missing"
        assert "missing" in errors
