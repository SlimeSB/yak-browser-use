"""Tests for progressive snapshot mode — CollectState, build_llm_view, etc."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# helpers that don't need the class — just module-level functions
# ---------------------------------------------------------------------------

from cdp.playwright_bridge import (
    _node_attrs,
    _is_interactive_progressive,
    _build_selector_from_attrs_progressive,
    _build_selector_from_node_progressive,
    _classify_by_tag,
    CONTAINER_DEPTH_RANGE,
    DENSITY_THRESHOLD,
    SHALLOW_QUOTA,
    MAX_LLM_ELEMENTS,
    CollectState,
    build_llm_view,
    _folded_summary_from_container,
    PROGRESSIVE_REF_PREFIX,
)


# ===================================================================
# _node_attrs
# ===================================================================

def test_node_attrs_parses_flat_array():
    node = {"attributes": ["id", "main", "class", "foo bar", "role", "button"]}
    attrs = _node_attrs(node)
    assert attrs == {"id": "main", "class": "foo bar", "role": "button"}


def test_node_attrs_empty():
    node = {"attributes": []}
    assert _node_attrs(node) == {}

    node = {}
    assert _node_attrs(node) == {}


def test_node_attrs_odd_length():
    node = {"attributes": ["id"]}
    attrs = _node_attrs(node)
    assert attrs == {"id": ""}


# ===================================================================
# _is_interactive_progressive
# ===================================================================

@pytest.mark.parametrize("tag,attrs,expected", [
    ("button", {}, True),
    ("input", {}, True),
    ("input", {"type": "hidden"}, False),
    ("select", {}, True),
    ("textarea", {}, True),
    ("a", {"href": "https://example.com"}, True),
    ("a", {}, False),
    ("div", {"role": "button"}, True),
    ("div", {"role": "textbox"}, True),
    ("div", {"role": "link"}, True),
    ("div", {"onclick": "handler()"}, True),
    ("div", {"tabindex": "0"}, True),
    ("div", {"contenteditable": "true"}, True),
    ("div", {}, False),
    ("span", {}, False),
    ("li", {}, False),
])
def test_is_interactive_progressive(tag, attrs, expected):
    assert _is_interactive_progressive(tag, attrs) == expected


# ===================================================================
# _build_selector_from_attrs_progressive
# ===================================================================

def test_selector_id_priority():
    s = _build_selector_from_attrs_progressive("div", {"id": "main", "class": "foo"})
    assert s == "div#main"


def test_selector_data_testid():
    s = _build_selector_from_attrs_progressive("span", {"data-testid": "submit-btn"})
    assert s == 'span[data-testid="submit-btn"]'


def test_selector_class():
    s = _build_selector_from_attrs_progressive("div", {"class": "foo bar baz qux"})
    # max 3 classes
    assert s == "div.foo.bar.baz"


def test_selector_tag_only():
    s = _build_selector_from_attrs_progressive("section", {})
    assert s == "section"


def test_selector_from_node():
    node = {"nodeName": "div", "attributes": ["id", "main"]}
    assert _build_selector_from_node_progressive(node) == "div#main"


# ===================================================================
# _classify_by_tag
# ===================================================================

@pytest.mark.parametrize("tag,expected", [
    ("ul", "list"), ("ol", "list"),
    ("table", "table"),
    ("nav", "nav"),
    ("form", "form"),
    ("div", "container"),
    ("section", "container"),
])
def test_classify_by_tag(tag, expected):
    assert _classify_by_tag(tag) == expected


# ===================================================================
# CollectState walk
# ===================================================================

def _make_cdp_node(node_type: int = 1, node_name: str = "div",
                    backend_node_id: int = 1, children: list | None = None,
                    attributes: list | None = None) -> dict:
    node: dict = {
        "nodeType": node_type,
        "nodeName": node_name,
        "backendNodeId": backend_node_id,
        "children": children or [],
    }
    if attributes:
        node["attributes"] = attributes
    return node


def test_collect_state_captures_interactive():
    ref_map = {}
    state = CollectState(ref_map)
    root = _make_cdp_node(children=[
        _make_cdp_node(node_name="button", backend_node_id=1,
                       attributes=["data-testid", "btn1"]),
    ])
    state.walk(root)
    assert len(state.elements_all) == 1
    el = state.elements_all[0]
    assert el["tag"] == "button"
    assert el["ref"] == "@p_1"
    assert el["backendNodeId"] == "1"
    assert state._ref_map["@p_1"] == el


def test_collect_state_skips_non_interactive():
    ref_map = {}
    state = CollectState(ref_map)
    root = _make_cdp_node(children=[
        _make_cdp_node(node_name="div", backend_node_id=1),
        _make_cdp_node(node_name="span", backend_node_id=2),
    ])
    state.walk(root)
    assert len(state.elements_all) == 0


def test_collect_state_marks_whitelist():
    ref_map = {}
    state = CollectState(ref_map)
    root = _make_cdp_node(children=[
        _make_cdp_node(node_name="button", backend_node_id=1),
        _make_cdp_node(node_name="div", backend_node_id=2,
                       attributes=["role", "button"]),
        _make_cdp_node(node_name="div", backend_node_id=3,
                       attributes=["onclick", "fn()"]),
    ])
    state.walk(root)
    assert state.elements_all[0]["_whitelist"] is True   # button tag
    assert state.elements_all[1]["_whitelist"] is True   # role=button
    assert state.elements_all[2]["_whitelist"] is False  # onclick only


def test_collect_state_container_stats():
    ref_map = {}
    state = CollectState(ref_map)
    # CDP DOM: #document(depth=0) > html(1) > head(2) + body(2) > div(3) > buttons(4)
    # body at depth=2 is in range and is semantic → container
    root = _make_cdp_node(node_name="#document", backend_node_id=0, children=[
        _make_cdp_node(node_name="html", backend_node_id=98, children=[
            _make_cdp_node(node_name="body", backend_node_id=99, children=[
                _make_cdp_node(node_name="div", backend_node_id=100,
                               attributes=["class", "product-list"], children=[
                                   _make_cdp_node(node_name="button", backend_node_id=i)
                                   for i in range(1, 4)
                               ]),
            ]),
        ]),
    ])
    state.walk(root)
    stats = state.stats_map
    div_container = [s for s in stats.values() if s["tag"] == "div"]
    assert len(div_container) == 1
    # div aggregates all 3 buttons (ancestor inheritance)
    assert div_container[0]["total_descendants"] == 3
    # body at depth=2 also accumulates
    body_stats = [s for s in stats.values() if s["tag"] == "body"]
    assert len(body_stats) == 1
    assert body_stats[0]["total_descendants"] == 3


def test_collect_state_extracts_text():
    ref_map = {}
    state = CollectState(ref_map)
    btn = _make_cdp_node(node_name="button", backend_node_id=1,
                         attributes=["aria-label", "Add to cart"],
                         children=[
                             {"nodeType": 3, "nodeValue": "  Add to cart  "}
                         ])
    root = _make_cdp_node(children=[btn])
    state.walk(root)
    # aria-label takes priority over text node
    assert state.elements_all[0]["text"] == "Add to cart"


def test_collect_state_text_fallback_to_children():
    ref_map = {}
    state = CollectState(ref_map)
    btn = _make_cdp_node(node_name="button", backend_node_id=1,
                         children=[
                             {"nodeType": 3, "nodeValue": "Submit"},
                         ])
    root = _make_cdp_node(children=[btn])
    state.walk(root)
    assert state.elements_all[0]["text"] == "Submit"


def test_collect_state_skip_input_hidden():
    ref_map = {}
    state = CollectState(ref_map)
    hidden = _make_cdp_node(node_name="input", backend_node_id=1,
                            attributes=["type", "hidden"])
    root = _make_cdp_node(children=[hidden])
    state.walk(root)
    assert len(state.elements_all) == 0


def test_collect_state_empty_dom():
    ref_map = {}
    state = CollectState(ref_map)
    state.walk(_make_cdp_node())
    assert state.elements_all == []
    assert state.stats_map == {}


# ===================================================================
# build_llm_view
# ===================================================================

def _make_element(ref: str, tag: str = "div", role: str = "button",
                  container: str | None = None,
                  whitelist: bool = True, in_view: bool = False) -> dict:
    return {
        "ref": ref, "tag": tag, "backendNodeId": ref.replace("@p_", ""),
        "selector": tag, "text": ref, "role": role,
        "_containers": [container] if container else [], "_whitelist": whitelist, "_in_view": in_view,
    }


def _make_stats(ckey: str, tag: str = "div", role: str = "",
                depth: int = 2, total: int = 0, whitelist_count: int = 0) -> dict:
    return {
        "depth": depth, "tag": tag, "role": role, "selector": tag,
        "total_descendants": total, "whitelist_count": whitelist_count,
    }


def test_build_llm_view_no_elements():
    ref_map: dict = {}
    state = CollectState(ref_map)
    view, folded, bi = build_llm_view(state)
    assert view == []
    assert folded == []
    assert bi == {}


def test_build_llm_view_all_non_dense():
    ref_map: dict = {}
    state = CollectState(ref_map)
    # 3 elements in 2 containers, none dense
    c1 = "c_0"
    c2 = "c_1"
    state.stats_map = {
        c1: _make_stats(c1, total=2, whitelist_count=2),
        c2: _make_stats(c2, total=1, whitelist_count=1),
    }
    state._ref_map = ref_map
    state.elements_all = [
        _make_element("@p_1", container=c1),
        _make_element("@p_2", container=c1),
        _make_element("@p_3", container=c2),
    ]
    for el in state.elements_all:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    assert len(view) == 3
    assert folded == []
    assert c1 in bi
    assert c2 in bi
    assert bi[c1] == ["@p_1", "@p_2"]


def test_build_llm_view_dense_container_sampled():
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    total_elements = DENSITY_THRESHOLD + 21  # 71
    state.stats_map = {
        c1: _make_stats(c1, total=total_elements, whitelist_count=3),
    }
    # 3 whitelist + 18 non-whitelist = 71 total directly in container c1
    elements = []
    for i in range(3):
        el = _make_element(f"@p_{i}", container=c1, whitelist=True)
        elements.append(el)
    for i in range(3, total_elements):
        el = _make_element(f"@p_{i}", container=c1, whitelist=False)
        elements.append(el)

    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    assert len(folded) == 1
    assert folded[0]["total"] == total_elements
    assert folded[0]["sampled"] <= SHALLOW_QUOTA
    assert c1 in bi
    assert len(bi[c1]) == total_elements


def test_build_llm_view_whitelist_priority():
    """Critical whitelist elements first, then even sampling of rest."""
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    state.stats_map = {
        c1: _make_stats(c1, total=100, whitelist_count=5),
    }
    elements = []
    for i in range(5):
        elements.append(_make_element(f"@p_{i}", container=c1, whitelist=True))
    for i in range(5, 100):
        elements.append(_make_element(f"@p_{i}", container=c1, whitelist=False))
    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    whitelist_in_view = [e for e in view if e["_whitelist"]]
    assert len(whitelist_in_view) == 5
    assert folded[0]["sampled"] <= SHALLOW_QUOTA


def test_build_llm_view_dialog_exempt():
    """Dialog containers should not be folded, but MAX_LLM_ELEMENTS still applies."""
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    state.stats_map = {
        c1: _make_stats(c1, total=DENSITY_THRESHOLD + 50, whitelist_count=10,
                        tag="dialog", role="dialog"),
    }
    elements = []
    for i in range(DENSITY_THRESHOLD + 50):
        elements.append(_make_element(f"@p_{i}", container=c1))
    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    assert folded == []  # dialog is not folded
    # Dialog elements are full-included (unless capped by MAX_LLM_ELEMENTS)
    assert len(view) == min(DENSITY_THRESHOLD + 50, MAX_LLM_ELEMENTS)
    assert c1 in bi


def test_build_llm_view_max_llm_elements_cap():
    ref_map: dict = {}
    state = CollectState(ref_map)
    elements = []
    for i in range(MAX_LLM_ELEMENTS * 2):
        el = _make_element(f"@p_{i}", container=None, whitelist=(i < 10))
        elements.append(el)
    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    assert len(view) <= MAX_LLM_ELEMENTS
    # All 10 whitelist should be in view
    whitelist_in_view = [e for e in view if e["_whitelist"]]
    assert len(whitelist_in_view) == 10
    # Elements not in view should have _in_view = False
    not_in_view = [e for e in state.elements_all if not e["_in_view"]]
    kept_refs = {e["ref"] for e in view}
    for e in not_in_view:
        assert e["ref"] not in kept_refs


def test_build_llm_view_shallow_quota_hard_cap():
    """SHALLOW_QUOTA=30 must be an absolute ceiling, even with many whitelist items."""
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    state.stats_map = {
        c1: _make_stats(c1, total=200, whitelist_count=100),
    }
    elements = []
    for i in range(200):
        elements.append(_make_element(f"@p_{i}", container=c1,
                                       whitelist=(i < 100)))
    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    assert folded[0]["sampled"] <= SHALLOW_QUOTA
    sampled_in_view = [e for e in view if c1 in e.get("_containers", [])]
    assert len(sampled_in_view) <= SHALLOW_QUOTA


def test_build_llm_view_folded_sampled_sync():
    """After MAX_LLM_ELEMENTS trim, folded[].sampled must reflect actual count."""
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    state.stats_map = {
        c1: _make_stats(c1, total=MAX_LLM_ELEMENTS + 30, whitelist_count=0),
    }
    elements = []
    for i in range(MAX_LLM_ELEMENTS + 30):
        elements.append(_make_element(f"@p_{i}", container=c1, whitelist=False))
    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    actual_in_container = sum(1 for e in view if c1 in e.get("_containers", []))
    assert folded[0]["sampled"] == actual_in_container
    assert actual_in_container <= SHALLOW_QUOTA  # dense + sampled


def test_build_llm_view_density_ratio():
    """Container with significantly more elements than mean should be flagged dense."""
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1, c2, c3 = "c_0", "c_1", "c_2"
    state.stats_map = {
        c1: _make_stats(c1, total=3, whitelist_count=3),
        c2: _make_stats(c2, total=5, whitelist_count=5),
        c3: _make_stats(c3, total=120, whitelist_count=10),
    }
    elements = []
    for i in range(3):
        elements.append(_make_element(f"@p_a{i}", container=c1))
    for i in range(5):
        elements.append(_make_element(f"@p_b{i}", container=c2))
    for i in range(120):
        elements.append(_make_element(f"@p_c{i}", container=c3))
    state.elements_all = elements
    for el in elements:
        ref_map[el["ref"]] = el

    view, folded, bi = build_llm_view(state)
    # c3 should be dense (120 >> mean of ~43, ratio = 2.8 < 3.0 threshold though)
    # Actually 120 / ((3+5+120)/3) = 120 / 42.67 = 2.81 < 3.0, but c3 also exceeds DENSITY_THRESHOLD=50
    assert len(folded) == 1
    assert folded[0]["key"] == c3


def test__folded_summary_from_container():
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    state.stats_map = {c1: _make_stats(c1, tag="div", total=42)}
    el = _make_element("@p_7", container=c1)
    el["text"] = "iPhone 15 Pro Max"
    state.elements_all = [el]

    summary = _folded_summary_from_container(state, c1)
    assert "iPhone 15" in summary
    assert "42" in summary


def test__folded_summary_fallback_to_tag():
    ref_map: dict = {}
    state = CollectState(ref_map)
    c1 = "c_0"
    state.stats_map = {c1: _make_stats(c1, tag="ul", total=10)}
    state.elements_all = []

    summary = _folded_summary_from_container(state, c1)
    assert "ul" in summary
    assert "10" in summary


# ===================================================================
# Progressive mode ref prefix
# ===================================================================

def test_progressive_ref_prefix():
    assert PROGRESSIVE_REF_PREFIX == "@p_"
    # refs should be @p_<backendNodeId>
    bid = 456
    assert f"@p_{bid}" == f"@{PROGRESSIVE_REF_PREFIX[1:]}{bid}"
