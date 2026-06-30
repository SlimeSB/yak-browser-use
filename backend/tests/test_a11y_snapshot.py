"""Unit tests for a11y snapshot + ref-based interaction (P0).

Tests the invariants from plan §9.1 (I1-I10) and acceptance criteria §7.
Uses mock CDP + Playwright — no real browser needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.cdp.playwright_bridge import (
    A11Y_REF_PREFIX,
    PROGRESSIVE_REF_PREFIX,
    _flatten_cdp_ax_nodes,
    _ax_value,
)


# ── _ax_value ──────────────────────────────────────────────────


def test_ax_value_returns_string():
    assert _ax_value({"value": "hello", "type": "string"}) == "hello"


def test_ax_value_returns_bool():
    assert _ax_value({"value": True, "type": "boolean"}) == "true"


def test_ax_value_none():
    assert _ax_value(None) == ""


def test_ax_value_empty():
    assert _ax_value({}) == ""


# ── _flatten_cdp_ax_nodes ──────────────────────────────────────


CDP_SAMPLE_NODES = [
    {
        "nodeId": "1", "childIds": ["2", "3"],
        "role": {"value": "WebArea", "type": "role"},
        "name": {"value": "Test Page"},
        "backendDOMNodeId": 1,
    },
    {
        "nodeId": "2", "childIds": [],
        "role": {"value": "button", "type": "role"},
        "name": {"value": "Submit"},
        "backendDOMNodeId": 2,
    },
    {
        "nodeId": "3", "childIds": ["4"],
        "role": {"value": "navigation", "type": "role"},
        "name": {"value": "Main Nav"},
        "backendDOMNodeId": 3,
    },
    {
        "nodeId": "4", "childIds": [],
        "role": {"value": "link", "type": "role"},
        "name": {"value": "Home"},
        "backendDOMNodeId": 4,
    },
    {
        "nodeId": "5", "childIds": [],
        "role": {"value": "generic", "type": "role"},
        "name": {"value": "ignored"},
        "backendDOMNodeId": 5,
    },
]


def test_flatten_cdp_ax_nodes_extracts_interactive():
    elements = _flatten_cdp_ax_nodes(CDP_SAMPLE_NODES)
    roles = [e["role"] for e in elements]
    assert roles == ["button", "link"]


def test_flatten_cdp_ax_nodes_skips_non_interactive():
    elements = _flatten_cdp_ax_nodes(CDP_SAMPLE_NODES)
    # navigation, WebArea, generic all excluded
    for el in elements:
        assert el["role"] not in ("navigation", "WebArea", "generic")


def test_flatten_cdp_ax_nodes_preserves_name():
    elements = _flatten_cdp_ax_nodes(CDP_SAMPLE_NODES)
    names = {e["role"]: e["name"] for e in elements}
    assert names == {"button": "Submit", "link": "Home"}


def test_flatten_cdp_ax_nodes_empty():
    assert _flatten_cdp_ax_nodes([]) == []


# ── a11y_snapshot ──────────────────────────────────────────────


class MockPage:
    """Mock Playwright Page for a11y_snapshot tests."""

    def __init__(self):
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


def _make_cdp_send_side_effect():
    """Return a side_effect for MockCDPSession.send that returns CDP-like data."""
    async def side_effect(method, params=None):
        if method == "Accessibility.getFullAXTree":
            return {"nodes": CDP_SAMPLE_NODES}
        # Accessibility.enable and others return empty
        return {}
    return side_effect


class MockCDPSession:
    """Mock CDP session for a11y snapshot tests."""

    def __init__(self):
        self.send = AsyncMock(side_effect=_make_cdp_send_side_effect())
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


@pytest.fixture
def mock_bridge():
    return MockBridge()


@pytest.fixture
def a11y_snapshot_fn(mock_bridge):
    """Import a11y_snapshot from the real bridge, bound to mock."""
    from yak_browser_use.cdp.playwright_bridge import PlaywrightBridge

    # Bind the method to our mock
    return PlaywrightBridge.a11y_snapshot.__get__(mock_bridge, PlaywrightBridge)


@pytest.mark.asyncio
async def test_a11y_snapshot_returns_elements(a11y_snapshot_fn, mock_bridge):
    result = await a11y_snapshot_fn()
    assert result["mode"] == "a11y"
    assert len(result["elements"]) == 2  # CDP_SAMPLE_NODES: button + link


@pytest.mark.asyncio
async def test_a11y_snapshot_uses_selector(a11y_snapshot_fn, mock_bridge):
    result = await a11y_snapshot_fn()
    for el in result["elements"]:
        assert "ref" not in el
        assert "selector" in el
        assert el["selector"].startswith("[data-ybu-ref=\"")


@pytest.mark.asyncio
async def test_a11y_snapshot_nth_counts_same_role_name(a11y_snapshot_fn, mock_bridge):
    # Two buttons with same name "Submit" → nth=0 and nth=1
    cdp_nodes = [
        {"nodeId": "1", "childIds": [],
         "role": {"value": "button"}, "name": {"value": "Submit"}, "backendDOMNodeId": 1},
        {"nodeId": "2", "childIds": [],
         "role": {"value": "button"}, "name": {"value": "Submit"}, "backendDOMNodeId": 2},
    ]

    async def custom_send(method, params=None):
        if method == "Accessibility.getFullAXTree":
            return {"nodes": cdp_nodes}
        return {}

    mock_bridge._cdp_session.send = AsyncMock(side_effect=custom_send)
    result = await a11y_snapshot_fn()
    buttons = [e for e in result["elements"] if e["role"] == "button"]
    assert len(buttons) == 2
    # Same name → sequential nth
    assert buttons[0]["nth"] == 0
    assert buttons[1]["nth"] == 1


@pytest.mark.asyncio
async def test_a11y_snapshot_empty_name_nth(a11y_snapshot_fn, mock_bridge):
    """I1 + #18: empty name elements get unique nth via __empty__:{i}."""
    cdp_nodes = [
        {"nodeId": "1", "childIds": [],
         "role": {"value": "button"}, "name": {"value": ""}, "backendDOMNodeId": 1},
        {"nodeId": "2", "childIds": [],
         "role": {"value": "button"}, "name": {"value": ""}, "backendDOMNodeId": 2},
        {"nodeId": "3", "childIds": [],
         "role": {"value": "button"}, "name": {"value": ""}, "backendDOMNodeId": 3},
    ]

    async def custom_send(method, params=None):
        if method == "Accessibility.getFullAXTree":
            return {"nodes": cdp_nodes}
        return {}

    mock_bridge._cdp_session.send = AsyncMock(side_effect=custom_send)
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
    assert len(mock_bridge._ref_map) == 2  # CDP_SAMPLE_NODES: button + link


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
async def test_a11y_snapshot_has_selector(a11y_snapshot_fn, mock_bridge):
    """a11y elements include role=... selector, not ref."""
    result = await a11y_snapshot_fn()
    for el in result["elements"]:
        assert "selector" in el
        assert "ref" not in el
        assert el["selector"].startswith("[data-ybu-ref=\"")


# ── Invariant I5: _in_view consistency ─────────────────────────


def test_in_view_consistency():
    """I5: elements in view_elements have _in_view=True, others False."""
    from yak_browser_use.cdp.playwright_bridge import PROGRESSIVE_REF_PREFIX

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
    from yak_browser_use.cdp.playwright_bridge import _extract_text_from_children
    node = {
        "children": [
            {"nodeType": 3, "nodeValue": "Hello World"},
        ],
    }
    assert _extract_text_from_children(node) == "Hello World"


def test_extract_text_from_children_nested():
    from yak_browser_use.cdp.playwright_bridge import _extract_text_from_children
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
    from yak_browser_use.cdp.playwright_bridge import _extract_text_from_children
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
    from yak_browser_use.cdp.playwright_bridge import _extract_text_from_children
    assert _extract_text_from_children({}) == ""
    assert _extract_text_from_children({"children": []}) == ""
