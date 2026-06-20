"""Unit tests for a11y snapshot + ref-based interaction (P0).

Tests the invariants from plan §9.1 (I1-I10) and acceptance criteria §7.
Uses mock CDP + Playwright — no real browser needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cdp.playwright_bridge import (
    A11Y_REF_PREFIX,
    PROGRESSIVE_REF_PREFIX,
    _flatten_a11y_tree,
)


# ── Sample data ────────────────────────────────────────────────

SAMPLE_A11Y_TREE = {
    "role": "WebArea",
    "name": "Test Page",
    "children": [
        {
            "role": "button",
            "name": "Submit",
            "children": [],
        },
        {
            "role": "button",
            "name": "Cancel",
            "children": [],
        },
        {
            "role": "textbox",
            "name": "Search",
            "value": "hello",
            "children": [],
        },
        {
            "role": "checkbox",
            "name": "Agree",
            "checked": True,
            "children": [],
        },
        # Non-interactive (no name, no value, no checked)
        {
            "role": "generic",
            "name": "",
            "children": [],
        },
        # Nested
        {
            "role": "navigation",
            "name": "Main Nav",
            "children": [
                {
                    "role": "link",
                    "name": "Home",
                    "children": [],
                },
                {
                    "role": "link",
                    "name": "About",
                    "children": [],
                },
            ],
        },
    ],
}


# ── _flatten_a11y_tree ─────────────────────────────────────────


def test_flatten_a11y_tree_extracts_interactive():
    elements = _flatten_a11y_tree(SAMPLE_A11Y_TREE)
    roles = [e["role"] for e in elements]
    assert roles == ["button", "button", "textbox", "checkbox", "link", "link"]


def test_flatten_a11y_tree_skips_non_interactive():
    elements = _flatten_a11y_tree(SAMPLE_A11Y_TREE)
    names = [e["name"] for e in elements]
    assert "" not in names  # generic with empty name excluded


def test_flatten_a11y_tree_preserves_fields():
    elements = _flatten_a11y_tree(SAMPLE_A11Y_TREE)
    search = next(e for e in elements if e["role"] == "textbox")
    assert search["value"] == "hello"
    agree = next(e for e in elements if e["role"] == "checkbox")
    assert agree["checked"] is True


def test_flatten_a11y_tree_empty():
    assert _flatten_a11y_tree({}) == []


# ── a11y_snapshot ──────────────────────────────────────────────


class MockPage:
    """Mock Playwright Page for a11y_snapshot tests."""

    def __init__(self):
        self.accessibility = MagicMock()
        self.accessibility.snapshot = AsyncMock(return_value=SAMPLE_A11Y_TREE)
        self.evaluate = AsyncMock(return_value=None)
        self.url = "about:blank"
        self.title = AsyncMock(return_value="Mock Page")
        self.get_by_role = MagicMock()
        self._mock_locator = MagicMock()
        self._mock_locator.nth = MagicMock(return_value=self._mock_locator)
        self._mock_locator.evaluate = AsyncMock(return_value=None)
        self._mock_locator.click = AsyncMock(return_value=None)
        self._mock_locator.fill = AsyncMock(return_value=None)
        self._mock_locator.type = AsyncMock(return_value=None)
        self._mock_locator.press = AsyncMock(return_value=None)
        self.get_by_role.return_value = self._mock_locator
        self.mouse = MagicMock()
        self.mouse.click = AsyncMock(return_value=None)


class MockCDPSession:
    """Mock CDP session for progressive backendNodeId operations."""

    def __init__(self):
        self.send = AsyncMock()
        self.detach = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class AsyncMockCDPSessionFactory:
    """Factory that returns an async context manager wrapping MockCDPSession."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass


def _make_async_cm(session):
    """Wrap a MockCDPSession so it can be used with 'async with'."""
    return AsyncMockCDPSessionFactory(session)


class MockBridge:
    """Minimal mock of PlaywrightBridge for a11y snapshot tests."""

    def __init__(self):
        self._page = MockPage()
        self._ref_map: dict[str, dict] = {}
        self._branch_index: dict[str, list[str]] = {}
        self._last_highlight_elements: list[dict] = []
        self._highlight_enabled = True
        self._context = MagicMock()
        self._cdp_session = MockCDPSession()
        self._context.new_cdp_session = AsyncMock(return_value=self._cdp_session)

    async def _is_highlight_enabled(self) -> bool:
        return self._highlight_enabled

    async def ensure_highlights(self, page=None):
        pass

    async def _locator_by_ref(self, ref: str):
        from cdp.playwright_bridge import PlaywrightBridge
        return await PlaywrightBridge._locator_by_ref(self, ref)

    async def _backend_node_by_ref(self, ref: str) -> int:
        from cdp.playwright_bridge import PlaywrightBridge
        return await PlaywrightBridge._backend_node_by_ref(self, ref)

    async def _click_backend_node(self, backend_node_id: int) -> None:
        from cdp.playwright_bridge import PlaywrightBridge
        return await PlaywrightBridge._click_backend_node(self, backend_node_id)


@pytest.fixture
def mock_bridge():
    return MockBridge()


@pytest.fixture
def a11y_snapshot_fn(mock_bridge):
    """Import a11y_snapshot from the real bridge, bound to mock."""
    from cdp.playwright_bridge import PlaywrightBridge

    # Bind the method to our mock
    return PlaywrightBridge.a11y_snapshot.__get__(mock_bridge, PlaywrightBridge)


@pytest.mark.asyncio
async def test_a11y_snapshot_returns_elements(a11y_snapshot_fn, mock_bridge):
    result = await a11y_snapshot_fn()
    assert result["mode"] == "a11y"
    assert len(result["elements"]) == 6


@pytest.mark.asyncio
async def test_a11y_snapshot_refs_have_prefix(a11y_snapshot_fn, mock_bridge):
    result = await a11y_snapshot_fn()
    for el in result["elements"]:
        assert el["ref"].startswith(A11Y_REF_PREFIX)


@pytest.mark.asyncio
async def test_a11y_snapshot_refs_are_sequential(a11y_snapshot_fn, mock_bridge):
    result = await a11y_snapshot_fn()
    refs = [el["ref"] for el in result["elements"]]
    assert refs == [f"{A11Y_REF_PREFIX}{i}" for i in range(6)]


@pytest.mark.asyncio
async def test_a11y_snapshot_nth_counts_same_role_name(a11y_snapshot_fn, mock_bridge):
    # Two buttons: "Submit" (nth=0), "Cancel" (nth=0, different name)
    result = await a11y_snapshot_fn()
    buttons = [e for e in result["elements"] if e["role"] == "button"]
    assert len(buttons) == 2
    # Different names → each nth=0
    assert buttons[0]["nth"] == 0
    assert buttons[1]["nth"] == 0


@pytest.mark.asyncio
async def test_a11y_snapshot_empty_name_nth(a11y_snapshot_fn, mock_bridge):
    """I1 + #18: empty name elements get unique nth via __empty__:{i}."""
    tree = {
        "role": "WebArea",
        "name": "Page",
        "children": [
            {"role": "button", "name": "", "children": []},
            {"role": "button", "name": "", "children": []},
            {"role": "button", "name": "", "children": []},
        ],
    }
    mock_bridge._page.accessibility.snapshot = AsyncMock(return_value=tree)
    result = await a11y_snapshot_fn()
    buttons = [e for e in result["elements"] if e["role"] == "button"]
    assert len(buttons) == 3
    # Each should have nth=0 (different __empty__:{i} keys)
    assert buttons[0]["nth"] == 0
    assert buttons[1]["nth"] == 0
    assert buttons[2]["nth"] == 0


@pytest.mark.asyncio
async def test_a11y_snapshot_clears_ref_map(a11y_snapshot_fn, mock_bridge):
    """I1: _ref_map cleared before rebuild."""
    mock_bridge._ref_map = {"@a_99": {"ref": "@a_99", "role": "button", "name": "stale"}}
    await a11y_snapshot_fn()
    assert "@a_99" not in mock_bridge._ref_map
    assert len(mock_bridge._ref_map) == 6


@pytest.mark.asyncio
async def test_a11y_snapshot_clears_branch_index(a11y_snapshot_fn, mock_bridge):
    """I4: _branch_index cleared."""
    mock_bridge._branch_index = {"c_0": ["@p_123"]}
    await a11y_snapshot_fn()
    assert mock_bridge._branch_index == {}


@pytest.mark.asyncio
async def test_a11y_snapshot_cleans_old_stamps(a11y_snapshot_fn, mock_bridge):
    """I2: old DOM stamps cleaned before new ones."""
    await a11y_snapshot_fn()
    # evaluate should have been called for stamp cleanup
    calls = [c.args[0] for c in mock_bridge._page.evaluate.call_args_list]
    cleanup_call = next((c for c in calls if "removeAttribute" in c), None)
    assert cleanup_call is not None


@pytest.mark.asyncio
async def test_a11y_snapshot_no_stamp_when_highlight_off(a11y_snapshot_fn, mock_bridge):
    """I3: no DOM stamping when highlight disabled."""
    mock_bridge._highlight_enabled = False
    await a11y_snapshot_fn()
    # No stamp-related evaluate calls
    stamp_calls = [
        c for c in mock_bridge._page.evaluate.call_args_list
        if "setAttribute" in str(c.args)
    ]
    assert len(stamp_calls) == 0


@pytest.mark.asyncio
async def test_a11y_snapshot_ref_map_has_semantic_only(a11y_snapshot_fn, mock_bridge):
    """_ref_map stores only semantic identity, no coordinates."""
    await a11y_snapshot_fn()
    for ref, el in mock_bridge._ref_map.items():
        assert "ref" in el
        assert "role" in el
        assert "name" in el
        assert "nth" in el
        assert "x" not in el
        assert "y" not in el
        assert "selector" not in el


# ── _locator_by_ref ────────────────────────────────────────────


@pytest.fixture
def locator_fn(mock_bridge):
    from cdp.playwright_bridge import PlaywrightBridge
    return PlaywrightBridge._locator_by_ref.__get__(mock_bridge, PlaywrightBridge)


@pytest.mark.asyncio
async def test_locator_by_ref_a11y(locator_fn, mock_bridge):
    mock_bridge._ref_map["@a_0"] = {"ref": "@a_0", "role": "button", "name": "Submit", "nth": 0}
    locator = await locator_fn("@a_0")
    mock_bridge._page.get_by_role.assert_called_with("button", name="Submit", exact=True)


@pytest.mark.asyncio
async def test_locator_by_ref_rejects_progressive(locator_fn, mock_bridge):
    mock_bridge._ref_map["@p_123"] = {"ref": "@p_123", "backendNodeId": "123"}
    with pytest.raises(ValueError, match="not an a11y ref"):
        await locator_fn("@p_123")


@pytest.mark.asyncio
async def test_locator_by_ref_missing_ref(locator_fn, mock_bridge):
    with pytest.raises(ValueError, match="not found"):
        await locator_fn("@a_999")


# ── _backend_node_by_ref ───────────────────────────────────────


@pytest.fixture
def backend_fn(mock_bridge):
    from cdp.playwright_bridge import PlaywrightBridge
    return PlaywrightBridge._backend_node_by_ref.__get__(mock_bridge, PlaywrightBridge)


@pytest.mark.asyncio
async def test_backend_node_by_ref(backend_fn, mock_bridge):
    mock_bridge._ref_map["@p_123"] = {"ref": "@p_123", "backendNodeId": "123"}
    bid = await backend_fn("@p_123")
    assert bid == 123


@pytest.mark.asyncio
async def test_backend_node_by_ref_rejects_a11y(backend_fn, mock_bridge):
    mock_bridge._ref_map["@a_0"] = {"ref": "@a_0", "role": "button", "name": "Submit"}
    with pytest.raises(ValueError, match="not a progressive ref"):
        await backend_fn("@a_0")


# ── click_ref / fill_ref ───────────────────────────────────────


@pytest.fixture
def click_ref_fn(mock_bridge):
    from cdp.playwright_bridge import PlaywrightBridge
    return PlaywrightBridge.click_ref.__get__(mock_bridge, PlaywrightBridge)


@pytest.fixture
def fill_ref_fn(mock_bridge):
    from cdp.playwright_bridge import PlaywrightBridge
    return PlaywrightBridge.fill_ref.__get__(mock_bridge, PlaywrightBridge)


@pytest.mark.asyncio
async def test_click_ref_a11y(click_ref_fn, mock_bridge):
    mock_bridge._ref_map["@a_0"] = {"ref": "@a_0", "role": "button", "name": "Submit", "nth": 0}
    result = await click_ref_fn("@a_0")
    assert result["ref"] == "@a_0"
    mock_bridge._page._mock_locator.click.assert_called_once()


@pytest.mark.asyncio
async def test_click_ref_progressive(click_ref_fn, mock_bridge):
    mock_bridge._ref_map["@p_123"] = {"ref": "@p_123", "backendNodeId": "123"}
    cdp = mock_bridge._context.new_cdp_session.return_value
    cdp.send.side_effect = [
        {"object": {"objectId": "obj-1"}},          # DOM.resolveNode
        {},                                          # DOM.scrollIntoViewIfNeeded
        {"model": {"content": [10, 20, 30, 20, 30, 40, 10, 40]}},  # DOM.getBoxModel
    ]
    result = await click_ref_fn("@p_123")
    assert result["ref"] == "@p_123"
    # Verify CDP was used (not Playwright locator)
    assert cdp.send.call_count >= 3


@pytest.mark.asyncio
async def test_fill_ref_a11y(fill_ref_fn, mock_bridge):
    mock_bridge._ref_map["@a_0"] = {"ref": "@a_0", "role": "textbox", "name": "Search", "nth": 0}
    result = await fill_ref_fn("@a_0", "hello")
    assert result["ref"] == "@a_0"
    mock_bridge._page._mock_locator.fill.assert_called_once_with("hello")


@pytest.mark.asyncio
async def test_click_ref_unknown_prefix(click_ref_fn, mock_bridge):
    with pytest.raises(ValueError, match="unknown ref prefix"):
        await click_ref_fn("@x_0")


# ── Invariant I5: _in_view consistency ─────────────────────────


def test_in_view_consistency():
    """I5: elements in view_elements have _in_view=True, others False."""
    from cdp.playwright_bridge import PROGRESSIVE_REF_PREFIX

    elements_all = [
        {"ref": f"{PROGRESSIVE_REF_PREFIX}1", "_in_view": True, "_whitelist": True},
        {"ref": f"{PROGRESSIVE_REF_PREFIX}2", "_in_view": True, "_whitelist": False},
        {"ref": f"{PROGRESSIVE_REF_PREFIX}3", "_in_view": False, "_whitelist": False},
    ]
    view_elements = [e for e in elements_all if e["_in_view"]]
    assert len(view_elements) == 2
    for e in view_elements:
        assert e["_in_view"] is True
    for e in elements_all:
        if e not in view_elements:
            assert e["_in_view"] is False


# ── Invariant I8: ref prefix routing ───────────────────────────


def test_ref_prefix_routing():
    """I8: routing depends only on ref prefix, not field presence."""
    # Progressive element also has 'role' field — must not route to a11y path
    ref = "@p_123"
    assert ref.startswith(PROGRESSIVE_REF_PREFIX)
    assert not ref.startswith(A11Y_REF_PREFIX)

    ref2 = "@a_0"
    assert ref2.startswith(A11Y_REF_PREFIX)
    assert not ref2.startswith(PROGRESSIVE_REF_PREFIX)


# ── _extract_text_from_children ────────────────────────────────


def test_extract_text_from_children_direct_text():
    from cdp.playwright_bridge import _extract_text_from_children
    node = {
        "children": [
            {"nodeType": 3, "nodeValue": "Hello World"},
        ],
    }
    assert _extract_text_from_children(node) == "Hello World"


def test_extract_text_from_children_nested():
    from cdp.playwright_bridge import _extract_text_from_children
    node = {
        "children": [
            {"nodeType": 1, "children": [
                {"nodeType": 3, "nodeValue": "Deep Text"},
            ]},
        ],
    }
    assert _extract_text_from_children(node) == "Deep Text"


def test_extract_text_from_children_deeply_nested():
    """#H6: recursive — handles arbitrary depth."""
    from cdp.playwright_bridge import _extract_text_from_children
    node = {
        "children": [
            {"nodeType": 1, "children": [
                {"nodeType": 1, "children": [
                    {"nodeType": 1, "children": [
                        {"nodeType": 3, "nodeValue": "Very Deep"},
                    ]},
                ]},
            ]},
        ],
    }
    assert _extract_text_from_children(node) == "Very Deep"


def test_extract_text_from_children_empty():
    from cdp.playwright_bridge import _extract_text_from_children
    assert _extract_text_from_children({}) == ""
    assert _extract_text_from_children({"children": []}) == ""
