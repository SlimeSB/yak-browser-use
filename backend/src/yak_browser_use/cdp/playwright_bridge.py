"""PlaywrightBridge — unified browser driver via playwright.chromium.connect_over_cdp().

Replaces CDPDaemon's raw WebSocket path. All browser operations (interaction,
navigation, snapshot, highlight, clipboard) go through Playwright's Page API,
which provides auto-wait, auto-scroll, and auto-retry.

Usage::

    bridge = PlaywrightBridge(cdp_url="http://127.0.0.1:9222")
    await bridge.start()
    await bridge.goto("https://example.com")
    await bridge.click("#btn")
    await bridge.stop()
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from yak_browser_use.workspace.manager import WORKSPACES_ROOT

logger = logging.getLogger(__name__)


class A11yNotAvailable(RuntimeError):
    """Raised when the browser environment does not support Accessibility Tree."""


# ---------------------------------------------------------------------------
# Interactive element detection heuristics
# ---------------------------------------------------------------------------


def _is_tentative(tag: str, attrs: dict[str, str]) -> bool:
    if tag in _ALWAYS_FULL_TAGS:
        return False
    if attrs.get("role", "").lower() in _ALWAYS_FULL_ROLES:
        return False
    if attrs.get("tabindex") is not None:
        return False
    if attrs.get("onclick"):
        return False
    cedit = attrs.get("contenteditable")
    if cedit is not None and cedit.lower() in ("true", ""):
        return False
    return True


def _build_selector_from_node(tag: str, attrs: dict[str, str]) -> str:
    node_id = attrs.get("id")
    if node_id:
        return f"#{node_id}"

    parts = [tag]
    cls = attrs.get("class", "")
    for c in cls.split():
        if c:
            parts.append(f".{c}")

    for attr_name in ("name", "type", "role", "aria-label", "href", "placeholder", "title", "target"):
        val = attrs.get(attr_name)
        if val and '"' not in val:
            parts.append(f'[{attr_name}="{val}"]')

    return "".join(parts)


# ---------------------------------------------------------------------------
# a11y snapshot — CDP Accessibility.getFullAXTree
# ---------------------------------------------------------------------------

A11Y_REF_PREFIX = "@a_"
PROGRESSIVE_REF_PREFIX = "@p_"

# Only these roles are considered "interactive" for a11y snapshot
_A11Y_INTERACTIVE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "switch", "tab",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option",
    "combobox", "listbox", "textbox", "searchbox", "slider",
    "spinbutton", "treeitem", "heading", "img", "listitem",
})


def _ax_value(value_obj: dict | None) -> str:
    """Extract the string value from a CDP AX ``{value, type}`` object."""
    if not value_obj:
        return ""
    v = value_obj.get("value")
    if isinstance(v, str):
        return v
    if isinstance(v, bool | int | float):
        return str(v).lower()
    return ""


def _flatten_cdp_ax_nodes(nodes: list[dict]) -> list[dict]:
    """Flatten CDP ``Accessibility.getFullAXTree`` nodes, keeping interactive elements only.

    CDP returns a flat array ``[{nodeId, childIds, backendDOMNodeId, role: {value, type},
    name: {value, type}, ...}]``.  This function filters by interactive role and normalises
    field names to match the downstream ``{role, name, value, description, checked, disabled}``
    format expected by ``a11y_snapshot``.
    """
    elements: list[dict] = []
    for node in nodes:
        role = _ax_value(node.get("role")).lower()
        if role not in _A11Y_INTERACTIVE_ROLES:
            continue
        elements.append({
            "role": role,
            "name": _ax_value(node.get("name")),
            "value": _ax_value(node.get("value")),
            "description": _ax_value(node.get("description")),
            "checked": _ax_value(node.get("checked")),
            "disabled": _ax_value(node.get("disabled")),
            "expanded": _ax_value(node.get("expanded")),
            "haspopup": _ax_value(node.get("haspopup")),
            "pressed": _ax_value(node.get("pressed")),
            "selected": _ax_value(node.get("selected")),
            "hidden": _ax_value(node.get("hidden")),
        })
    return elements


def _match(el: dict, q: str) -> bool:
    """Generic query matching: key name match (value truthy) then string value match."""
    q = q.lower()
    for k, v in el.items():
        if k.startswith("_"):
            continue
        if q in k.lower() and v:
            return True
        if isinstance(v, str) and q in v.lower():
            return True
    return False


def _extract_text_from_children(node: dict) -> str:
    """Recursively extract text from CDP DOM node's subtree (unlimited depth)."""
    parts = []
    for child in node.get("children", []):
        if child.get("nodeType") == 3:  # text node
            v = (child.get("nodeValue") or "").strip()
            if v:
                parts.append(v)
        elif child.get("nodeType") == 1:
            parts.append(_extract_text_from_children(child))
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# progressive snapshot — CDP DOM walk + density-adaptive disclosure
# ---------------------------------------------------------------------------

CONTAINER_DEPTH_RANGE = (2, 30)       # (min, max) depth guard
DENSITY_THRESHOLD = 50
DENSITY_RATIO = 3.0
SHALLOW_QUOTA = 30
BODY_QUOTA = 5
PAGE_LEVEL_DEPTH = 2
MAX_LLM_ELEMENTS = 200
DIALOG_ROLES = {"dialog", "alertdialog"}

# Semantic container tags — always create containers for these
_CONTAINER_TAGS = frozenset({
    "ul", "ol", "table", "nav", "section", "article",
    "header", "footer", "main", "aside", "form", "dl", "tbody",
    "body", "head",
})

# Class keywords that suggest a structural container
_CONTAINER_CLASS_PATTERNS = frozenset({
    "list", "card", "grid", "panel", "container", "wrapper",
    "group", "row", "col", "menu", "feed", "items", "content",
    "category", "module", "layout",
})

_ALWAYS_FULL_TAGS = {"button", "input", "select", "textarea", "a",
                     "details", "summary", "option", "optgroup", "label",
                     "datalist", "output", "fieldset", "video", "audio"}
_ALWAYS_FULL_ROLES = {"button", "link", "textbox", "combobox", "checkbox",
                       "radio", "switch", "menuitem", "option", "tab",
                       "menuitemcheckbox", "menuitemradio", "listbox",
                       "searchbox", "slider", "spinbutton", "treeitem"}

_NON_INTERACTIVE_TAGS = frozenset({
    "script", "style", "meta", "link", "br", "hr", "noscript",
    "head", "title", "base", "template",
    "html", "body",
})

_SKIP_CHILDREN_TAGS = frozenset({"svg", "canvas"})


def _looks_like_container(node: dict) -> bool:
    """Heuristic: does this node look like it contains collected descendants?

    Returns True if:
      - The tag is a semantic container (ul/ol/table/nav/section etc.), OR
      - The node has >= 2 element children (not text/comments), OR
      - The class attribute contains a container keyword (list/card/grid etc.)
    """
    tag = node.get("nodeName", "").lower()
    if tag in _CONTAINER_TAGS:
        return True

    element_children = 0
    for child in node.get("children", []):
        if child.get("nodeType") == 1:
            element_children += 1
    if element_children >= 2:
        return True

    attrs_list = node.get("attributes", [])
    for i in range(0, len(attrs_list), 2):
        if i + 1 < len(attrs_list) and attrs_list[i].lower() == "class":
            cls = attrs_list[i + 1].lower()
            for pattern in _CONTAINER_CLASS_PATTERNS:
                if pattern in cls:
                    return True
            break
    return False


def _is_interactive_progressive(tag: str, attrs: dict[str, str]) -> bool:
    """Blacklist-based: collect every element except non-interactive tags and input[type=hidden]."""
    if tag in _NON_INTERACTIVE_TAGS:
        return False
    if tag == "input" and attrs.get("type", "").lower() == "hidden":
        return False
    return True


def _node_attrs(node: dict) -> dict[str, str]:
    """Extract attributes dict from CDP DOM node's flat array [k1, v1, k2, v2, ...]."""
    attrs: dict[str, str] = {}
    raw = node.get("attributes", [])
    for i in range(0, len(raw), 2):
        key = raw[i].lower()
        attrs[key] = raw[i + 1] if i + 1 < len(raw) else ""
    return attrs


def _build_selector_from_node_progressive(node: dict) -> str:
    """Build CSS selector from a CDP DOM node (progressive mode)."""
    tag = node.get("nodeName", "").lower()
    attrs = _node_attrs(node)
    return _build_selector_from_attrs_progressive(tag, attrs)


def _build_selector_from_attrs_progressive(tag: str, attrs: dict[str, str], nth: int = 1) -> str:
    """Build CSS selector from tag + attrs. Add :nth-of-type for disambiguation.

    nth-of-type is only appended when nth > 1 (elements after the first of
    their type).  Singleton selectors (id, data-testid) are unique without it.
    """
    if attrs.get("id"):
        return f'{tag}#{attrs["id"]}'
    if attrs.get("data-testid"):
        return f'{tag}[data-testid="{attrs["data-testid"]}"]'
    sel = tag
    if attrs.get("class"):
        cls = ".".join(attrs["class"].split()[:3])
        sel = f"{tag}.{cls}"
    if nth > 1:
        sel = f"{sel}:nth-of-type({nth})"
    return sel


class CollectState:
    """Phase 1: full-depth CDP DOM walk, collecting every interactive element."""

    def __init__(self, ref_map: dict):
        self.elements_all: list[dict] = []
        self.stats_map: dict[str, dict] = {}
        self._ref_map = ref_map
        self._stack: list[str] = []
        self._counter = 0
        self._real_nth_counter: dict[str, int] = {}

    def walk(self, node: dict, depth: int = 0) -> None:
        ckey = None
        if (node.get("nodeType") == 1
                and CONTAINER_DEPTH_RANGE[0] <= depth <= CONTAINER_DEPTH_RANGE[1]
                and _looks_like_container(node)):
            ckey = f"c_{self._counter}"
            self._counter += 1
            self._stack.append(ckey)
            c_attrs = _node_attrs(node)
            self.stats_map[ckey] = {
                "depth": depth,
                "tag": node.get("nodeName", "").lower(),
                "role": c_attrs.get("role", ""),
                "selector": _build_selector_from_node_progressive(node),
                "total_descendants": 0,
                "whitelist_count": 0,
            }

        if node.get("nodeType") == 1:
            attrs = _node_attrs(node)
            tag = node["nodeName"].lower()
            if _is_interactive_progressive(tag, attrs):
                bid = str(node["backendNodeId"])
                ref = f"{PROGRESSIVE_REF_PREFIX}{bid}"
                text = (attrs.get("aria-label", "")
                        or attrs.get("title", "")
                        or attrs.get("value", "")
                        or attrs.get("placeholder", "")
                        or _extract_text_from_children(node))
                nth = self._real_nth_counter.get(tag, 1)
                prog_label_parts = [ckey.split("_", 1)[1] for ckey in self._stack] + [bid]
                prog_label = "-".join(prog_label_parts)
                el = {
                    "ref": ref, "tag": tag,
                    "backendNodeId": bid,
                    "selector": _build_selector_from_attrs_progressive(tag, attrs, nth),
                    "text": text,
                    "role": attrs.get("role", ""),
                    "_containers": list(self._stack),
                    "_prog_label": prog_label,
                    "prog_label": prog_label,
                    "_whitelist": (tag in _ALWAYS_FULL_TAGS or
                                   attrs.get("role", "").lower() in _ALWAYS_FULL_ROLES),
                    "_in_view": False,
                }
                # Interaction state attributes (conditional)
                if "disabled" in attrs:
                    el["disabled"] = True
                if "aria-disabled" in attrs:
                    el["aria_disabled"] = attrs["aria-disabled"]
                if "aria-expanded" in attrs:
                    el["aria_expanded"] = attrs["aria-expanded"]
                if "aria-haspopup" in attrs:
                    el["aria_haspopup"] = attrs["aria-haspopup"]
                if "aria-pressed" in attrs:
                    el["aria_pressed"] = attrs["aria-pressed"]
                if "aria-selected" in attrs:
                    el["aria_selected"] = attrs["aria-selected"]
                if "aria-checked" in attrs:
                    el["aria_checked"] = attrs["aria-checked"]
                if "aria-hidden" in attrs:
                    el["aria_hidden"] = attrs["aria-hidden"]
                if "hidden" in attrs:
                    el["hidden"] = True
                if "readonly" in attrs:
                    el["readonly"] = True
                if "required" in attrs:
                    el["required"] = True

                # Semantic attributes (conditional)
                if "type" in attrs:
                    el["type"] = attrs["type"]
                if "aria-label" in attrs:
                    el["aria_label"] = attrs["aria-label"]
                if "placeholder" in attrs:
                    el["placeholder"] = attrs["placeholder"]
                if "value" in attrs:
                    el["value"] = attrs["value"]
                if tag == "a" and attrs.get("href"):
                    el["href"] = attrs["href"]

                self.elements_all.append(el)
                self._ref_map[ref] = el
                # Increment ancestor containers (skip self when node is also a container)
                for ancestor_key in self._stack:
                    if ckey is not None and ancestor_key == ckey:
                        continue
                    s = self.stats_map[ancestor_key]
                    s["total_descendants"] += 1
                    if el["_whitelist"]:
                        s["whitelist_count"] += 1

        # nth-of-type is per-parent — save/restore counter at each level
        old_nth_counter = self._real_nth_counter
        self._real_nth_counter = {}
        current_tag = node.get("nodeName", "").lower() if node.get("nodeType") == 1 else ""
        if current_tag not in _SKIP_CHILDREN_TAGS:
            for child in node.get("children", []):
                if child.get("nodeType") == 1:
                    ct = child.get("nodeName", "").lower()
                    self._real_nth_counter[ct] = self._real_nth_counter.get(ct, 0) + 1
                self.walk(child, depth + 1)
        self._real_nth_counter = old_nth_counter

        if ckey and self._stack:
            self._stack.pop()


def _folded_summary_from_container(state: CollectState, ckey: str) -> str:
    """Generate a human-readable summary for a folded container.

    Collects up to 5 distinct text samples from elements inside this container
    so LLM can gauge whether to expand_branch.
    """
    stats = state.stats_map[ckey]
    snippet = stats.get("selector", "")
    if len(snippet) > 40:
        snippet = snippet[:37] + "..."

    seen: set[str] = set()
    samples: list[str] = []
    for el in state.elements_all:
        if ckey in el.get("_containers", []):
            text = el.get("text", "").strip()
            if text and text not in seen:
                seen.add(text)
                samples.append(text[:15])
                if len(samples) >= 5:
                    break

    joined = " · ".join(samples) if samples else stats["tag"]
    return f"{joined}  [{stats['total_descendants']} total]"


def build_llm_view(state: CollectState) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
    """Phase 2: density detection + shallow sampling → LLM-friendly view."""

    # 1. Identify dense containers (dialog exemption)
    dialog_keys = {ckey for ckey, s in state.stats_map.items()
                   if s["tag"] in DIALOG_ROLES or "dialog" in s.get("role", "")}
    valid_stats = {ckey: s for ckey, s in state.stats_map.items() if ckey not in dialog_keys}
    mean_desc = (
        sum(s["total_descendants"] for s in valid_stats.values())
        / max(1, len(valid_stats))
    )
    dense_containers: set[str] = set()
    for ckey, stats in state.stats_map.items():
        if stats["tag"] in DIALOG_ROLES or "dialog" in stats.get("role", ""):
            continue
        if (stats["total_descendants"] > DENSITY_THRESHOLD or
                (mean_desc > 0 and stats["total_descendants"] / mean_desc > DENSITY_RATIO)):
            dense_containers.add(ckey)

    # 2. Dense containers: shallow sampling
    view_refs: set[str] = set()
    folded: list[dict] = []
    branch_index: dict[str, list[str]] = {}

    for ckey in dense_containers:
        all_refs = [el["ref"] for el in state.elements_all
                    if ckey in el.get("_containers", [])]
        branch_index[ckey] = list(all_refs)

        critical = [r for r in all_refs if state._ref_map[r]["_whitelist"]]
        normal = [r for r in all_refs if r not in critical]

        quota = BODY_QUOTA if state.stats_map[ckey]["depth"] <= PAGE_LEVEL_DEPTH else SHALLOW_QUOTA

        picked = list(critical[:quota])
        remaining = quota - len(picked)
        if remaining > 0 and normal:
            step = max(1, len(normal) // remaining)
            for i in range(0, len(normal), step):
                if len(picked) >= quota:
                    break
                picked.append(normal[i])

        for r in picked:
            state._ref_map[r]["_in_view"] = True
            view_refs.add(r)

        folded.append({
            "key": ckey,
            "selector": state.stats_map[ckey]["selector"],
            "type": _classify_by_tag(state.stats_map[ckey]["tag"]),
            "total": state.stats_map[ckey]["total_descendants"],
            "sampled": len(picked),
            "_sampled_refs": set(picked),
            "expand_hint": f"[snapshot(expand_key='{ckey}') to browse all {state.stats_map[ckey]['total_descendants']} items]",
            "summary": _folded_summary_from_container(state, ckey),
        })

    # 3. Non-dense + containerless elements → full inclusion
    for el in state.elements_all:
        containers = el.get("_containers", [])
        in_any_dense = any(c in dense_containers for c in containers) if containers else False
        if not in_any_dense:
            el["_in_view"] = True
        if containers:
            ckey = containers[-1]  # nearest container
            if ckey not in dense_containers:
                if ckey not in branch_index:
                    branch_index[ckey] = []
                if el["ref"] not in branch_index[ckey]:
                    branch_index[ckey].append(el["ref"])

    # 4. MAX_LLM_ELEMENTS hard cap — equal quota per DOM region
    view_elements = [el for el in state.elements_all if el["_in_view"]]
    if len(view_elements) > MAX_LLM_ELEMENTS:
        # Split walk order into N equal bands so every major layout
        # section gets representation regardless of container detection.
        REGION_COUNT = 8
        groups: list[list[dict]] = [[] for _ in range(REGION_COUNT)]
        for i, e in enumerate(view_elements):
            groups[i * REGION_COUNT // len(view_elements)].append(e)

        # Whitlelist-first sort within each group
        for g in groups:
            g.sort(key=lambda e: (0 if e["_whitelist"] else 1, state.elements_all.index(e)))

        # Equal quota per group (remainder distributed to first N groups)
        per_group = MAX_LLM_ELEMENTS // REGION_COUNT
        extra = MAX_LLM_ELEMENTS - per_group * REGION_COUNT
        result = []
        for idx, g in enumerate(groups):
            quota = per_group + (1 if idx < extra else 0)
            result.extend(g[:quota])

        view_elements = result
        kept_refs = {e["ref"] for e in view_elements}
        for el in state.elements_all:
            if el["_in_view"] and el["ref"] not in kept_refs:
                el["_in_view"] = False
        for f in folded:
            f["sampled"] = sum(
                1 for ref in f.get("_sampled_refs", []) if ref in kept_refs
            )

    return view_elements, folded, branch_index


def _classify_by_tag(tag: str) -> str:
    """Classify a container by its tag for LLM context."""
    if tag in ("ul", "ol"):
        return "list"
    if tag in ("table",):
        return "table"
    if tag in ("nav",):
        return "nav"
    if tag in ("form",):
        return "form"
    return "container"


# ---------------------------------------------------------------------------
# highlight JS — injected into every new page so @eN badges are always visible
#
# 🚫 再写一套高亮系统死妈。
# 所有高亮数据走 window.__ybu_last_elements，由 _ybu_render() 渲染。
# helpers.py::add_dom_highlights 只推数据，不注 JS，不建容器，不绑事件。
#
# 滚动：RAF 节流 _ybu_onScroll → 先批量读 getBoundingClientRect
# 再批量写 transform。所有定位用 translate3d() + will-change，
# 保持在合成线程，不触发布局。
#
# MutationObserver：300ms 防抖，先 disconnect 再 render 再 observe，
# 避免自触发循环。调 _ybu_render()（轻量重绘），不调 _ybu_run()（拆容器重建）。
# ---------------------------------------------------------------------------

_HIGHLIGHT_BOOTSTRAP = """
(function() {
    if (window.__ybu_highlight_ready) return;
    window.__ybu_highlight_ready = true;

    function _ybu_run() {
        if (!document.body) return;
        var oldC = document.getElementById('ybu-highlights');
        if (oldC) {
            if (oldC._ybu_scrollFn) window.removeEventListener('scroll', oldC._ybu_scrollFn);
            if (oldC._ybu_resizeFn) window.removeEventListener('resize', oldC._ybu_resizeFn);
            if (oldC._ybu_mo) oldC._ybu_mo.disconnect();
            oldC.remove();
        }
        var outlined = document.querySelectorAll('[data-ybu-outlined]');
        for (var i = 0; i < outlined.length; i++) {
            outlined[i].style.outline = '';
            outlined[i].removeAttribute('data-ybu-outlined');
        }
        var container = document.createElement('div');
        container.id = 'ybu-highlights';
        container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2147483646;';
        document.body.appendChild(container);

        var scrollRAF = null;

        function _ybu_render() {
            if (!document.body) return;
            var els = window.__ybu_last_elements || [];
            // Clean old outlines
            var oldO = document.querySelectorAll('[data-ybu-outlined]');
            for (var i = 0; i < oldO.length; i++) {
                oldO[i].style.outline = '';
                oldO[i].removeAttribute('data-ybu-outlined');
            }
            container.innerHTML = '';
            var selIdx = {};
            var vw = window.innerWidth;
            var vh = window.innerHeight;
            for (var i = 0; i < els.length; i++) {
                var el = els[i];
                if (el.selector) {
                    try {
                        var si = selIdx[el.selector] || 0;
                        selIdx[el.selector] = si + 1;
                        var all = document.querySelectorAll(el.selector);
                        if (all.length > si) {
                            var target = all[si];
                            var rect = target.getBoundingClientRect();
                            // Skip hidden / zero-size / offscreen elements
                            if (rect.width === 0 || rect.height === 0) continue;
                            if (rect.left + rect.width < 0 || rect.top + rect.height < 0) continue;
                            if (rect.left > vw || rect.top > vh) continue;
                            target.style.outline = '2px dashed #3b82f6';
                            target.style.outlineOffset = '0px';
                            var lbl = el.prog_label || el.ref;
                            target.setAttribute('data-ybu-outlined', el.ref);
                            var badgeDiv = document.createElement('div');
                            badgeDiv.className = 'ybu-badge-sel';
                            badgeDiv.setAttribute('data-ybu-badge', el.ref);
                            badgeDiv.style.cssText = 'position:fixed;pointer-events:none;will-change:transform;';
                            badgeDiv.style.transform = 'translate3d(' + rect.left + 'px,' + Math.max(0, rect.top - 14) + 'px,0)';
                            var badge = document.createElement('span');
                            badge.textContent = lbl;
                            badge.style.cssText = 'background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;';
                            badgeDiv.appendChild(badge);
                            container.appendChild(badgeDiv);
                            continue;
                        }
                    } catch (e) {}
                }
                // Fallback: box + badge with stored original coords
                var sx = window.pageXOffset || document.documentElement.scrollLeft || 0;
                var sy = window.pageYOffset || document.documentElement.scrollTop || 0;
                var fx = el.x - sx;
                var fy = el.y - sy;
                // Skip fallback boxes outside viewport
                if (fx + (el.width || 0) < 0 || fy + (el.height || 0) < 0) continue;
                if (fx > vw || fy > vh) continue;
                if ((el.width || 0) === 0 && (el.height || 0) === 0) continue;
                var box = document.createElement('div');
                box.className = 'ybu-fb-box';
                box.setAttribute('data-ybu-fb', el.ref);
                box.setAttribute('data-ybu-ox', Math.round(el.x));
                box.setAttribute('data-ybu-oy', Math.round(el.y));
                box.style.cssText = 'position:fixed;width:' + el.width + 'px;height:' + el.height + 'px;border:2px dashed #3b82f6;border-radius:2px;pointer-events:none;will-change:transform;';
                box.style.transform = 'translate3d(' + fx + 'px,' + fy + 'px,0)';
                var lbl = el.prog_label || el.ref;
                var fb = document.createElement('span');
                fb.textContent = lbl;
                fb.style.cssText = 'position:absolute;top:-12px;left:-2px;background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;pointer-events:none;';
                box.appendChild(fb);
                container.appendChild(box);
            }
        }

        // 滚动时先 RAF 节流更新已有 badge 位置（transform，不触发重新布局），
        // 再防抖 300ms 后调 _ybu_render 让新滚入视野的元素出现。
        // 这样连续滚动时 badge 不闪烁，滚动停止 300ms 后刷新 viewport。
        var _scrollEndTimer = null;
        function _ybu_onScroll() {
            if (scrollRAF) return;
            scrollRAF = requestAnimationFrame(function() {
                scrollRAF = null;
                _ybu_update_positions();
            });
            if (_scrollEndTimer) clearTimeout(_scrollEndTimer);
            _scrollEndTimer = setTimeout(function() {
                _scrollEndTimer = null;
                _ybu_render();
            }, 300);
        }

        function _ybu_update_positions() {
            var sx = window.pageXOffset || document.documentElement.scrollLeft || 0;
            var sy = window.pageYOffset || document.documentElement.scrollTop || 0;
            // Batch READ — collect all layout rects
            var outlined = document.querySelectorAll('[data-ybu-outlined]');
            var rects = [];
            for (var i = 0; i < outlined.length; i++) {
                rects.push(outlined[i].getBoundingClientRect());
            }
            // Batch WRITE — transforms are composited, no layout
            for (var i = 0; i < outlined.length; i++) {
                var ref = outlined[i].getAttribute('data-ybu-outlined');
                var bd = container.querySelector('[data-ybu-badge="' + ref.replace(/"/g, '\\"') + '"]');
                if (bd) {
                    bd.style.transform = 'translate3d(' + rects[i].left + 'px,' + Math.max(0, rects[i].top - 14) + 'px,0)';
                }
            }
            // Fallback boxes: getAttribute is data-read (no layout)
            var fbBoxes = container.querySelectorAll('[data-ybu-fb]');
            for (var i = 0; i < fbBoxes.length; i++) {
                var box = fbBoxes[i];
                var ox = parseFloat(box.getAttribute('data-ybu-ox')) || 0;
                var oy = parseFloat(box.getAttribute('data-ybu-oy')) || 0;
                box.style.transform = 'translate3d(' + (ox - sx) + 'px,' + (oy - sy) + 'px,0)';
            }
        }

        window.__ybu_render = _ybu_render;
        window.__ybu_onScroll = _ybu_onScroll;
        window.__ybu_run = _ybu_render;  // backward compat
        window.addEventListener('scroll', _ybu_onScroll, {passive: true});
        window.addEventListener('resize', _ybu_onScroll, {passive: true});
        container._ybu_scrollFn = _ybu_onScroll;
        container._ybu_resizeFn = _ybu_onScroll;

        // MutationObserver: debounced 300ms, disconnect before render to avoid loop
        var _ybu_moTimer = null;
        if (window.MutationObserver) {
            var mo = new MutationObserver(function() {
                if (_ybu_moTimer) clearTimeout(_ybu_moTimer);
                _ybu_moTimer = setTimeout(function() {
                    mo.disconnect();
                    _ybu_render();
                    mo.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden', 'aria-hidden']});
                }, 300);
            });
            mo.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden', 'aria-hidden']});
            container._ybu_mo = mo;
        }

        _ybu_render();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _ybu_run);
    } else {
        _ybu_run();
    }
})();
"""



class PlaywrightBridge:
    """Unified browser driver via ``playwright.chromium.connect_over_cdp()``.

    All ops go through this class:
    - Interaction / navigation / tabs → Playwright Page API
    - Snapshot / highlight / eval → ``page.evaluate()`` / ``page.screenshot()``
    - Clipboard → ``page.evaluate()``
    """

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222", pipeline_name: str = "__chat__") -> None:
        self._cdp_url = cdp_url
        self._pipeline_name = pipeline_name
        self._run_id: str | None = None
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ref_map: dict[str, dict] = {}
        self._element_map: dict[str, Any] = {}
        self._last_highlight_elements: list[dict] = []
        self._highlight_guard_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._page_scan_done = asyncio.Event()
        self._page_scan_done.set()  # initially ready — no scan pending
        # Per-page element cache, so each tab shows its own highlights
        self._per_page_elements: dict[int, list[dict]] = {}
        # a11y / progressive mode state
        self._branch_index: dict[str, list[str]] = {}
        self._highlight_enabled: bool = True
        self._highlight_mode: str = "a11y"
        self._on_disconnect_cb: Callable[[], Any] | None = None
        self._health_check_task: asyncio.Task | None = None
        self._process_watch_task: asyncio.Task | None = None
        self._disconnected: bool = False
        self._seen_pages: set[Page] = set()
        self._background_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _schedule(self, coro):
        task = asyncio.ensure_future(coro)

        def _done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.warning("_schedule: background task failed", exc_info=exc)

        self._background_tasks.add(task)
        task.add_done_callback(_done)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def wait_for_page_scan(self, timeout: float = 5.0) -> None:
        """Wait until the current page's auto-scan completes.

        Called by the tool executor after a click/goto/fill/scroll so the
        LLM never sees stale ``_ref_map`` or ``_last_highlight_elements``.
        """
        try:
            await asyncio.wait_for(self._page_scan_done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug("wait_for_page_scan: timed out after %.1fs", timeout)

    async def start(self) -> None:
        """Connect to Chrome via CDP and grab the active page."""
        logger.info("PlaywrightBridge connecting to %s", self._cdp_url)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(self._cdp_url)
        self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()

        pages = self._context.pages
        if pages:
            self._page = pages[0]
        else:
            self._page = await self._context.new_page()

        self._browser.on("disconnected", lambda: self._schedule(self._on_browser_disconnected()))
        self._context.on("page", self._on_new_page)
        for p in self._context.pages:
            p.on("load", lambda pg=p: self._schedule(self._on_page_load(pg)))
            p.on("close", lambda pg=p: self._schedule(self._on_page_closed(pg)))
            p.on("framenavigated", lambda f, pg=p: self._schedule(self._on_frame_navigated(f, pg)))
        await self.ensure_highlights()
        # 给其他标签页也注入 bootstrap 框架（但不扫描，等切到时再扫）
        for p in self._context.pages:
            if p is not self._page:
                await self.ensure_highlights(p)
        # 不再在连接时绑定下载路径 — 由 set_download_dir 在 run_pipeline 开始时调用
        for p in self._context.pages:
            self._seen_pages.add(p)

        # 自动扫描当前页面，让开局就有高亮（不依赖 chat tool call）
        # 注意：不 await，让 scan 在后台跑，否则 CDP getFullAXTree/DOM.getDocument
        # 可能在页面未完全加载时阻塞 start() 数秒甚至无限期
        self._schedule(self._auto_scan())
        self._start_highlight_guard()
        logger.info("PlaywrightBridge connected (pages: %d)", len(self._context.pages))

    async def stop(self) -> None:
        """Release Playwright resources. Does NOT close Chrome."""
        logger.info("PlaywrightBridge stopping")
        self._stop_event.set()
        self._disconnected = True
        self._seen_pages.clear()
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        self._stop_health_check()
        if self._process_watch_task is not None:
            self._process_watch_task.cancel()
            self._process_watch_task = None
        if self._highlight_guard_task is not None:
            self._highlight_guard_task.cancel()
            self._highlight_guard_task = None
        try:
            if self._context:
                try:
                    self._context.remove_listener("page", self._on_new_page)
                except Exception:
                    logger.warning("Failed to remove page listener during stop", exc_info=True)
        except Exception:
            logger.warning("Failed to access context during stop", exc_info=True)
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    @property
    def page(self) -> Page | None:
        """The currently active Playwright Page."""
        return self._page

    async def _ensure_page(self) -> None:
        """Guard: auto-start the bridge if _page is None, raise otherwise.

        Called at the start of every method that uses ``self._page`` so that
        a call before ``start()`` or after ``stop()`` gets a clear error
        instead of ``NoneType can't be used in 'await' expression``.
        """
        if self._page is None:
            if self._disconnected:
                raise RuntimeError(
                    "PlaywrightBridge is disconnected. Call await bridge.start() to reconnect."
                )
            raise RuntimeError(
                "PlaywrightBridge._page is None. Call await bridge.start() before using browser operations."
            )

    # ------------------------------------------------------------------
    # New-page highlight auto-injection
    # ------------------------------------------------------------------

    async def _on_new_page(self, page: Page) -> None:
        """Auto-inject highlight JS and page ID when a new tab/page opens."""
        page.on("load", lambda pg=page: self._schedule(self._on_page_load(pg)))
        page.on("framenavigated", lambda f, pg=page: self._schedule(self._on_frame_navigated(f, pg)))
        page.on("close", lambda pg=page: self._schedule(self._on_page_closed(pg)))
        try:
            page_id = str(uuid.uuid4())[:8]
            await page.evaluate("(id) => { window.__ybu_page_id = id }", page_id)
            await asyncio.wait_for(
                page.wait_for_load_state("domcontentloaded"), timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.debug("_on_new_page: wait_for_load_state timed out")
        except Exception:
            logger.debug("_on_new_page: wait_for_load_state failed", exc_info=True)

        # 新标签页不要显示旧页面的高亮，先清空
        self._last_highlight_elements = []
        self._ref_map.clear()
        self._branch_index.clear()
        try:
            await page.evaluate("window.__ybu_last_elements = [];")
            await page.evaluate(_HIGHLIGHT_BOOTSTRAP)
        except Exception:
            logger.debug("_on_new_page highlight injection failed", exc_info=True)

        self._seen_pages.add(page)
        # 如果有活跃 run，为新页面设置下载路径
        if self._run_id is not None:
            ok = await self._set_page_download_behavior(page)
            if not ok:
                self._bind_download_fallback(page)

        # 新标签页自动设为活动页（让用户点链接后马上看到高亮）
        self._page = page
        # 不 await 扫描，让 scan 在后台跑，否则 getFullAXTree 可能阻塞数秒
        self._schedule(self._auto_scan())

    async def _on_page_closed(self, page: Page) -> None:
        """当页面被关闭时自动切换到其他可用页面。"""
        # 清理 per-page cache
        self._per_page_elements.pop(id(page), None)
        self._seen_pages.discard(page)
        if self._page is not page:
            return
        logger.info("current page closed, switching to another tab")
        if self._context and self._context.pages:
            self._page = self._context.pages[0]
            # 先清空旧元素数据，不让淘宝的几百个 badge 污染新标签页
            self._last_highlight_elements = []
            await self.ensure_highlights()
            try:
                await self._progressive_snapshot()
            except Exception:
                logger.debug("_on_page_closed: auto-scan failed", exc_info=True)
        else:
            self._page = None

    async def _on_browser_disconnected(self) -> None:
        """Called when the remote Chrome disconnects (closed/crashed).

        Stops all background tasks, clears references, and notifies the
        engine state via the disconnect callback. Idempotent — guarded by
        ``_disconnected`` flag.
        """
        if self._disconnected:
            return
        self._disconnected = True
        logger.warning("Remote Chrome disconnected")
        self._stop_event.set()
        self._stop_health_check()
        if self._process_watch_task is not None:
            self._process_watch_task.cancel()
            self._process_watch_task = None
        if self._highlight_guard_task is not None:
            self._highlight_guard_task.cancel()
            self._highlight_guard_task = None
        self._page = None
        self._context = None
        self._browser = None
        self._seen_pages.clear()
        await self._fire_disconnect_cb()

    async def _fire_disconnect_cb(self) -> None:
        """Fire the disconnect callback to notify EngineState."""
        cb = self._on_disconnect_cb
        if cb:
            try:
                await cb()
            except Exception:
                logger.exception("_fire_disconnect_cb: callback failed")

    # ------------------------------------------------------------------
    # Download directory management
    # ------------------------------------------------------------------

    async def _set_page_download_behavior(self, page: Page) -> bool:
        """Set CDP ``Page.setDownloadBehavior`` on *page*.

        Returns True on success, False if CDP command failed (caller
        should fall back to ``page.on("download")`` + ``save_as()``).
        Skips if no run is active (``_run_id`` is None).
        """
        path = self._resolve_download_path()
        if path is None:
            return False
        cdp_session = None
        try:
            cdp_session = await self._context.new_cdp_session(page)
            await cdp_session.send("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": str(path),
            })
            return True
        except Exception:
            logger.warning("CDP setDownloadBehavior failed for page, will fall back to download event", exc_info=True)
            return False
        finally:
            if cdp_session is not None:
                await cdp_session.detach()

    def _resolve_download_path(self, pipeline_name: str | None = None) -> Path | None:
        """Resolve the download directory for the current run.

        Returns ``WORKSPACES_ROOT / pipeline_name / "runs" / run_id / "downloads"``
        when ``_run_id`` is set, or ``None`` if no run is active.
        """
        if self._run_id is None:
            return None
        name = pipeline_name or self._pipeline_name
        path = WORKSPACES_ROOT / name / "runs" / self._run_id / "downloads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def set_download_dir(self, pipeline_name: str, run_id: str) -> None:
        """Set the download directory for the current run on all known pages."""
        self._pipeline_name = pipeline_name
        self._run_id = run_id
        for page in list(self._seen_pages):
            try:
                await self._set_page_download_behavior(page)
            except Exception:
                logger.debug("set_download_dir: failed for page %s", page, exc_info=True)

    def _bind_download_fallback(self, page: Page) -> None:
        """Fallback: listen for Playwright ``download`` event when CDP fails.

        Saves the downloaded file to the run download directory via
        ``download.save_as()``. Skips if no run is active.
        """
        async def _on_download(download):
            path = self._resolve_download_path()
            if path is None:
                return
            dest = path / download.suggested_filename
            try:
                await download.save_as(dest)
                logger.info("download fallback: saved %s", dest)
            except Exception:
                logger.exception("download fallback: save_as failed for %s", dest)

        page.on("download", _on_download)

    async def wait_for_download(
        self, timeout: int = 60
    ) -> dict:
        """Poll for a newly completed download file.

        Polls *download_dir* every 500 ms for a new file, then waits
        1 s and verifies the file size is stable (> 100 bytes).

        Returns ``{"ok": true, "path": "<absolute_path>"}`` or
        ``{"ok": false, "error": "timeout"}``.

        Known limitation: does not support concurrent downloads.
        """
        target_dir = self._resolve_download_path()
        if target_dir is None:
            return {"ok": False, "error": "no_active_run"}
        known = set(target_dir.iterdir()) if target_dir.exists() else set()

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            if not target_dir.exists():
                continue
            current = set(target_dir.iterdir())
            new_files = current - known
            if not new_files:
                continue

            candidate = new_files.pop()
            try:
                first_stat = candidate.stat()
                if first_stat.st_size <= 100:
                    continue
                await asyncio.sleep(1.0)
                second_stat = candidate.stat()
                if second_stat.st_size == first_stat.st_size:
                    return {"ok": True, "path": str(candidate)}
            except (OSError, FileNotFoundError):
                known = current
                continue

        return {"ok": False, "error": "timeout"}

    # ------------------------------------------------------------------
    # Health check — periodic CDP heartbeat
    # ------------------------------------------------------------------

    def start_health_check(self, interval: float = 3.0) -> None:
        """Start a background task that periodically verifies browser is alive.

        Sends a trivial CDP command (``page.evaluate("1+1")``). If it
        fails twice in a row the browser is considered dead and
        ``_on_browser_disconnected`` is called.
        """
        if self._health_check_task is not None:
            self._stop_health_check()
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(interval)
        )

    def _stop_health_check(self) -> None:
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            self._health_check_task = None

    async def _health_check_loop(self, interval: float) -> None:
        """CDP heartbeat: evaluate a trivial expression on a timer."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(interval)
                if self._disconnected:
                    break
                if self._page is None:
                    continue
                await self._page.evaluate("1+1")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning(
                    "Health check failed, retrying once in 2 s…"
                )
                try:
                    await asyncio.sleep(2)
                    if self._page is not None:
                        await self._page.evaluate("1+1")
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.error(
                        "Health check failed twice — browser unreachable, "
                        "triggering disconnect"
                    )
                    await self._on_browser_disconnected()
                    break

    # ------------------------------------------------------------------
    # Process watcher — monitor spawned subprocess
    # ------------------------------------------------------------------

    def watch_process(self, proc: asyncio.subprocess.Process) -> None:
        """Monitor a spawned browser subprocess.

        When the process exits (Edge window closed, crash, kill) the
        bridge is disconnected automatically.  This covers the case where
        Edge lingers as a background process but later exits (e.g.
        ``taskkill`` or system shutdown).
        """
        if self._process_watch_task is not None:
            self._process_watch_task.cancel()

        async def _watcher() -> None:
            try:
                await proc.wait()
                if not self._disconnected:
                    logger.warning(
                        "Spawned browser process exited (code=%s), "
                        "triggering disconnect",
                        proc.returncode,
                    )
                    await self._on_browser_disconnected()
            except Exception:
                logger.exception("Process watcher failed")

        self._process_watch_task = asyncio.create_task(_watcher())

    async def _is_highlight_enabled(self) -> bool:
        """Check whether highlight rendering is enabled (sync, no CDP round-trip)."""
        return self._highlight_enabled

    def set_highlight_config(self, mode: str) -> None:
        """Set highlighting mode: ``"a11y"``, ``"progressive"``, or ``"off"``."""
        if mode not in ("a11y", "progressive", "off"):
            raise ValueError(f"Invalid highlight mode: {mode!r}")
        self._highlight_mode = mode
        self._highlight_enabled = mode != "off"

    async def ensure_highlights(self, page: Page | None = None) -> None:
        """Inject highlight bootstrap and push element data into the page.

        For the active page (pg is self._page), pushes fresh element data and
        renders highlights.  For inactive pages, only ensures the bootstrap
        framework is present — never writes stale element data so highlights
        on other tabs stay clean.

        When ``_highlight_enabled`` is ``False``, clears overlay and skips.
        """
        pg = page or self._page
        if not pg:
            return
        try:
            if not self._highlight_enabled:
                # 清除旧 stamp 和 overlay
                await pg.evaluate("""
                    (function() {
                        var c = document.getElementById('ybu-highlights');
                        if (c) c.remove();
                        document.querySelectorAll('[data-ybu-ref]').forEach(function(el) {
                            el.removeAttribute('data-ybu-ref');
                        });
                        document.querySelectorAll('[data-ybu-prog-label]').forEach(function(el) {
                            el.removeAttribute('data-ybu-prog-label');
                        });
                        window.__ybu_last_elements = [];
                    })()
                """)
                return

            is_active = pg is self._page
            if is_active:
                display_elements = self._last_highlight_elements[:MAX_LLM_ELEMENTS]
                await pg.evaluate(
                    f"window.__ybu_last_elements = {_json.dumps(display_elements)};"
                )
            else:
                cached = self._per_page_elements.get(id(pg), [])
                await pg.evaluate(
                    f"window.__ybu_last_elements = {_json.dumps(cached[:MAX_LLM_ELEMENTS])};"
                )
            await pg.evaluate(_HIGHLIGHT_BOOTSTRAP)
            await pg.evaluate("window.__ybu_run && window.__ybu_run();")
        except Exception:
            logger.warning("ensure_highlights failed for %s", pg.url[:60] if pg.url else "(no url)", exc_info=True)

    async def _snapshot_current_page(self) -> dict:
        """Snapshot current page according to ``_highlight_mode``.

        ``"a11y"`` → :meth:`a11y_snapshot` with automatic fallback to
        :meth:`_progressive_snapshot` when the CDP Accessibility domain
        is unavailable.  ``"progressive"`` → :meth:`_progressive_snapshot`.
        """
        if self._highlight_mode == "a11y":
            try:
                return await self.a11y_snapshot()
            except A11yNotAvailable:
                logger.debug("a11y_snapshot unavailable, falling back to progressive")
                return await self._progressive_snapshot()
        else:
            return await self._progressive_snapshot()

    async def _auto_scan(self) -> None:
        """Auto-scan current page — delegates to :meth:`_snapshot_current_page`."""
        try:
            await self._snapshot_current_page()
        except Exception:
            logger.debug("_auto_scan: snapshot failed", exc_info=True)

    async def _on_page_load(self, page: Page) -> None:
        """Page load / reload 后自动重注高亮 + 扫描。"""
        self._page_scan_done.clear()
        try:
            await self.ensure_highlights(page)
            if page is self._page:
                await self._auto_scan()
            else:
                await self._scan_and_cache_page(page)
        finally:
            self._page_scan_done.set()

    async def _on_frame_navigated(self, frame, page: Page | None = None) -> None:
        """SPA pushState / replaceState — re-inject highlights + auto-scan."""
        pg = page or self._page
        if not pg or frame != pg.main_frame:
            return
        self._page_scan_done.clear()
        try:
            await self.ensure_highlights(pg)
            if pg is self._page:
                await self._auto_scan()
            else:
                await self._scan_and_cache_page(pg)
        finally:
            self._page_scan_done.set()

    async def _scan_and_cache_page(self, page: Page) -> None:
        """扫描非活跃页面的 DOM，缓存到 per-page cache，并渲染高亮。"""
        try:
            cdp = await self._context.new_cdp_session(page)
            try:
                doc = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
            finally:
                await cdp.detach()
        except Exception:
            logger.debug("_scan_and_cache_page: CDP session failed", exc_info=True)
            return

        elements: list[dict] = []

        def walk(node: dict) -> None:
            if node.get("nodeType") != 1:
                for child in node.get("children", []):
                    walk(child)
                return
            attrs_list = node.get("attributes", [])
            attrs: dict[str, str] = {}
            for i in range(0, len(attrs_list), 2):
                if i + 1 < len(attrs_list):
                    attrs[attrs_list[i]] = attrs_list[i + 1]
            tag = node["nodeName"].lower()
            bid = node["backendNodeId"]
            if not _is_interactive_progressive(tag, attrs):
                for child in node.get("children", []):
                    walk(child)
                return
            selector = _build_selector_from_node(tag, attrs)
            ref = f"@e_{bid}"
            elem_type = attrs.get("type", "text") if tag == "input" else ""
            elements.append({
                "ref": ref, "prog_label": str(bid),
                "selector": selector, "tag": tag,
                "type": elem_type, "text": "", "value": attrs.get("value", ""),
                "role": attrs.get("role", ""),
                "tentative": _is_tentative(tag, attrs),
                "x": 0, "y": 0, "width": 0, "height": 0,
            })
            for child in node.get("children", []):
                walk(child)

        walk(doc.get("root", {}))
        logger.debug("_scan_and_cache_page: found %d interactive elements", len(elements))

        if elements:
            sels = [e["selector"] for e in elements]
            js = (
                "(function(){"
                "var sels=" + _json.dumps(sels) + ";"
                "var selIdx={};"
                "var out=[];"
                "for(var i=0;i<sels.length;i++){"
                "var si=selIdx[sels[i]]||0;selIdx[sels[i]]=si+1;"
                "try{"
                "var all=document.querySelectorAll(sels[i]);"
                "if(all.length>si){"
                "var el=all[si];"
                "var r=el.getBoundingClientRect();"
                "var t=el.textContent||el.innerText||'';"
                "var cs=getComputedStyle(el);"
                "out.push({x:r.left,y:r.top,w:r.width,h:r.height,t:t.trim().substring(0,100),c:cs.cursor==='pointer'});"
                "}else{out.push({x:0,y:0,w:0,h:0,t:'',c:false});}"
                "}catch(e){out.push({x:0,y:0,w:0,h:0,t:'',c:false});}"
                "}"
                "return JSON.stringify(out);"
                "})()"
            )
            try:
                raw = await page.evaluate(js)
                if raw:
                    data = _json.loads(raw)
                    for el, d in zip(elements, data):
                        if isinstance(d, dict):
                            el["x"] = d.get("x", 0)
                            el["y"] = d.get("y", 0)
                            el["width"] = d.get("w", 0)
                            el["height"] = d.get("h", 0)
                            el["text"] = d.get("t", "")
                            el["clickable"] = d.get("c", False)
            except Exception:
                logger.debug("_scan_and_cache_page: position enrichment failed", exc_info=True)

        elements = [el for el in elements if not el.get("tentative") or el.get("clickable")]

        # 缓存到 per-page cache，供 ensure_highlights 在非活跃页上使用
        self._per_page_elements[id(page)] = list(elements)
        await self.ensure_highlights(page)

    # ------------------------------------------------------------------
    # Highlight guard — periodic safety-net refresh (every 2 s)
    # ------------------------------------------------------------------

    def _start_highlight_guard(self) -> None:
        """Background task: periodically re-inject highlights every ~2 s.

        Replicates the safety-net refresh that used to live in
        ``routes._highlight_guard`` before the Playwright migration.
        Covers async DOM mutations, injected scripts that clear the
        overlay, and other events the event-driven path misses.
        """

        async def _guard() -> None:
            while self._page is not None and not self._stop_event.is_set():
                await asyncio.sleep(2.0)
                try:
                    # 如果当前页已被用户关闭，自动切到其他页
                    if self._context and self._page not in self._context.pages:
                        if self._context.pages:
                            self._page = self._context.pages[0]
                            await self._snapshot_current_page()
                        else:
                            self._page = None
                            return
                    if self._highlight_enabled:
                        await self.ensure_highlights()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("_highlight_guard: iteration failed", exc_info=True)

        self._highlight_guard_task = asyncio.ensure_future(_guard())
        self._highlight_guard_task.add_done_callback(
            lambda t: logger.debug(
                "_highlight_guard: task ended (cancelled=%s)",
                t.cancelled(),
            )
        )

    # ------------------------------------------------------------------
    # Interaction ops
    # ------------------------------------------------------------------

    async def goto(self, url: str) -> dict:
        await self._ensure_page()
        # SSRF guard: only allow http/https
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": f"URL scheme not allowed: {url.split(':')[0]}:// (only http/https)"}
        await self._page.goto(url, wait_until="domcontentloaded")
        # 导航后扫描新页面，自动刷新高亮
        try:
            await self._progressive_snapshot()
        except Exception:
            logger.debug("goto: auto-scan failed", exc_info=True)
        return {"url": url}

    async def click(self, selector: str, click_count: int = 1) -> dict:
        await self._ensure_page()
        locator = self._page.locator(selector)
        try:
            if click_count > 1:
                await locator.dblclick(timeout=5000)
            else:
                await locator.click(timeout=5000)
        except Exception:
            await locator.wait_for(state="attached", timeout=3000)
            await locator.evaluate("el => el.click()")
        return {"selector": selector}

    # ------------------------------------------------------------------
    # Ref-based interaction (a11y / progressive mode) — REMOVED
    #
    # Ops now accept selector only (CSS / role= / text= …).
    # Ref is used internally for DOM stamping + badge display.
    # ------------------------------------------------------------------

    async def fill(self, selector: str, text: str) -> dict:
        await self._ensure_page()
        locator = self._page.locator(selector)
        try:
            await locator.fill(text, timeout=5000)
        except Exception:
            await locator.focus()
            await locator.fill("")
            await self._page.keyboard.type(text)
        return {"selector": selector}

    async def scroll(self, direction: str = "down", amount: int = 300) -> dict:
        await self._ensure_page()
        if direction == "down":
            js = f"window.scrollBy(0, {amount});"
        elif direction == "up":
            js = f"window.scrollBy(0, -{amount});"
        elif direction == "left":
            js = f"window.scrollBy(-{amount}, 0);"
        elif direction == "right":
            js = f"window.scrollBy({amount}, 0);"
        else:
            js = f"window.scrollBy(0, {amount});"
        await self._page.evaluate(js)
        return {"direction": direction, "amount": amount}

    async def source(self, strip_styles: bool = False, only_body: bool = False) -> str:
        await self._ensure_page()
        html = await self._page.content()
        if only_body:
            m = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.DOTALL | re.IGNORECASE)
            if m:
                html = m.group(1)
        if strip_styles:
            html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        return html

    async def evaluate(self, js: str) -> Any:
        await self._ensure_page()
        return await self._page.evaluate(js)

    # ------------------------------------------------------------------
    # New ops
    # ------------------------------------------------------------------

    async def hover(self, selector: str) -> dict:
        await self._ensure_page()
        await self._page.locator(selector).hover()
        return {"selector": selector}

    async def unhover(self, selector: str) -> dict:
        """Move mouse to (0,0) to unhover. ``selector`` is informational only."""
        await self._ensure_page()
        await self._page.mouse.move(0, 0)
        return {"selector": selector}

    async def focus(self, selector: str) -> dict:
        await self._ensure_page()
        await self._page.locator(selector).focus()
        return {"selector": selector}

    async def select(self, selector: str, value: str, mode: str = "value") -> dict:
        await self._ensure_page()
        locator = self._page.locator(selector)
        if mode == "label":
            await locator.select_option(label=value)
        elif mode == "index":
            await locator.select_option(index=int(value))
        else:
            await locator.select_option(value=value)
        return {"selector": selector}

    async def clear(self, selector: str, mode: str = "js") -> dict:
        await self._ensure_page()
        if mode == "pw":
            await self._page.locator(selector).clear()
        else:
            await self._page.evaluate(
                f"(function() {{ var el = document.querySelector({_json.dumps(selector)}); if (el) el.value = ''; }})()"
            )
        return {"selector": selector}

    async def keyboard_press(self, key: str) -> dict:
        await self._ensure_page()
        await self._page.keyboard.press(key)
        return {"key": key}

    async def keyboard_type(self, text: str) -> dict:
        await self._ensure_page()
        await self._page.keyboard.type(text)
        return {"text": text}

    async def navigate(self, action: str, hard: bool = False) -> dict:
        await self._ensure_page()
        if action == "back":
            await self._page.go_back()
        elif action == "forward":
            await self._page.go_forward()
        elif action == "reload":
            await self._page.reload()
        try:
            await self._progressive_snapshot()
        except Exception:
            logger.debug("navigate: auto-scan failed", exc_info=True)
        return {"action": action}

    async def wait(self, mode: str = "time", **kwargs: Any) -> dict:
        await self._ensure_page()
        if mode == "time":
            duration = kwargs.get("duration", 1000)
            await asyncio.sleep(duration / 1000.0)
        elif mode == "selector":
            selector = kwargs.get("selector", "")
            await self._page.wait_for_selector(selector)
        elif mode == "load":
            state = kwargs.get("state", "load")
            await self._page.wait_for_load_state(state)
        return {"mode": mode}

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    async def tab_new(self, url: str = "about:blank") -> dict:
        await self._ensure_page()
        if self._context is None:
            return {"ok": False, "error": "browser not connected"}
        new_page = await self._context.new_page()
        page_id = str(uuid.uuid4())[:8]
        await new_page.evaluate("(id) => { window.__ybu_page_id = id }", page_id)
        if url and url != "about:blank":
            await new_page.goto(url, wait_until="domcontentloaded")
        self._page = new_page
        return {"targetId": page_id, "url": new_page.url}

    async def tab_switch(self, target_id: str) -> dict:
        await self._ensure_page()
        if self._context is None:
            return {"ok": False, "error": "browser not connected"}
        for p in self._context.pages:
            pid = await asyncio.wait_for(p.evaluate("() => window.__ybu_page_id || ''"), timeout=5.0)
            if pid == target_id:
                await p.bring_to_front()
                self._page = p
                # 切换时先把缓存恢复，避免闪一下旧页面的高亮
                cached = self._per_page_elements.get(id(p))
                if cached is not None:
                    self._last_highlight_elements = list(cached)
                await self.ensure_highlights()
                try:
                    await self._progressive_snapshot()
                except Exception:
                    logger.debug("tab_switch: auto-scan failed", exc_info=True)
                return {"targetId": target_id, "url": p.url}
        raise ValueError(f"Tab not found: {target_id}")

    async def tab_close(self, target_id: str) -> dict:
        await self._ensure_page()
        if self._context is None:
            return {"ok": False, "error": "browser not connected"}
        for p in self._context.pages:
            pid = await asyncio.wait_for(p.evaluate("() => window.__ybu_page_id || ''"), timeout=5.0)
            if pid == target_id:
                await p.close()
                if self._page == p:
                    remaining = self._context.pages
                    if remaining:
                        self._page = remaining[0]
                    else:
                        self._page = await self._context.new_page()
                return {"targetId": target_id, "closed": True}
        raise ValueError(f"Tab not found: {target_id}")

    async def tab_list(self) -> list[dict]:
        await self._ensure_page()
        if self._context is None:
            return []
        result = []
        for i, p in enumerate(self._context.pages):
            try:
                url = p.url
                title = await p.title()
                pid = await p.evaluate("() => window.__ybu_page_id || ''")
                if not pid:
                    pid = str(uuid.uuid4())[:8]
                    await p.evaluate("(id) => { window.__ybu_page_id = id }", pid)
            except Exception:
                url = ""
                title = ""
                pid = ""
            result.append({
                "index": i,
                "targetId": pid,
                "url": url,
                "title": title,
            })
        return result

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    async def copy_to_clipboard(self, selector: str) -> dict:
        await self._ensure_page()
        text = await self._page.evaluate(
            f"(function() {{ var el = document.querySelector({_json.dumps(selector)}); return el ? (el.textContent || el.innerText || '') : ''; }})()"
        )
        return {"text": text, "selector": selector}

    async def paste_from_clipboard(self, selector: str, index: int = -1) -> dict:
        """Paste clipboard content into an input element.

        Note: navigator.clipboard.readText() requires a user gesture (click/keydown)
        or the "clipboard-read" permission. In headless/automated contexts this
        will often return an empty string.
        """
        await self._ensure_page()
        text = await self._page.evaluate("() => navigator.clipboard?.readText() || ''")
        js = (
            f"(function() {{"
            f"var el = document.querySelector({_json.dumps(selector)});"
            f"if (!el) return;"
            f"var t = {_json.dumps(text)};"
            f"if ({index} < 0) {{ el.value = (el.value || '') + t; }}"
            f"else {{ var v = el.value || ''; el.value = v.slice(0, {index}) + t + v.slice({index}); }}"
            f"el.dispatchEvent(new Event('input', {{bubbles: true}}));"
            f"}})()"
        )
        await self._page.evaluate(js)
        return {"selector": selector, "text": text}

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    async def wait_for_network_idle(self) -> None:
        await self._ensure_page()
        await self._page.wait_for_load_state("networkidle")

    async def wait_for_page_load(self) -> None:
        await self._ensure_page()
        await self._page.wait_for_load_state("load")

    # ------------------------------------------------------------------
    # Page HTML (with optional cache)
    # ------------------------------------------------------------------

    async def get_page_html(self, cached: bool = False) -> str:
        await self._ensure_page()
        if cached and "raw_html" in self._element_map:
            return self._element_map.get("raw_html", "")
        html = await self._page.content()
        self._element_map["raw_html"] = html
        return html

    # ------------------------------------------------------------------
    # Snapshot / Highlight
    # ------------------------------------------------------------------

    async def screenshot(self) -> str:
        await self._ensure_page()
        data = await self._page.screenshot(type="png", full_page=False)
        return base64.b64encode(data).decode("utf-8")

    async def a11y_snapshot(self, query: str = "") -> dict:
        """Snapshot via CDP ``Accessibility.getFullAXTree`` with DOM stamping.

        Returns ``{elements: [{ref, role, name, nth}], mode: "a11y"}``.
        Coordinates are never stored — the JS renderer computes them live
        from ``[data-ybu-ref]`` elements via ``getBoundingClientRect()``.

        If *query* is provided, only elements whose name or role contains
        the query string (case-insensitive) are returned.

        .. note::

           Uses a direct CDP ``Accessibility.getFullAXTree`` call rather than
           Playwright's removed ``page.accessibility.snapshot()`` API (unavailable
           since Playwright 1.48+).  Falls back to ``_progressive_snapshot()``
           if the CDP Accessibility domain is not supported.
        """
        await self._ensure_page()
        # Enable Accessibility domain, then get the full AX tree via CDP
        try:
            cdp = await self._context.new_cdp_session(self._page)
        except Exception as exc:
            logger.debug("a11y_snapshot: couldn't create CDP session", exc_info=True)
            raise A11yNotAvailable(
                f"CDP session not available: {exc}"
            ) from exc
        CDP_TIMEOUT = 8.0
        try:
            try:
                await asyncio.wait_for(cdp.send("Accessibility.enable"), timeout=CDP_TIMEOUT)
            except asyncio.TimeoutError:
                logger.debug("a11y_snapshot: CDP Accessibility.enable timed out")
            except Exception:
                logger.debug("a11y_snapshot: CDP Accessibility.enable failed", exc_info=True)
            result = await asyncio.wait_for(
                cdp.send("Accessibility.getFullAXTree", {}),
                timeout=CDP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.debug("a11y_snapshot: CDP getFullAXTree timed out")
            raise A11yNotAvailable("CDP getFullAXTree timed out")
        except A11yNotAvailable:
            raise
        except Exception as exc:
            logger.debug("a11y_snapshot: CDP getFullAXTree failed", exc_info=True)
            raise A11yNotAvailable(
                f"CDP Accessibility.getFullAXTree failed: {exc}"
            ) from exc
        finally:
            await cdp.detach()

        nodes = result.get("nodes", [])
        elements = _flatten_cdp_ax_nodes(nodes)

        # Filter by query (generic field matching)
        if query:
            elements = [el for el in elements if _match(el, query)]

        # I1: clear old _ref_map so stale refs don't survive
        self._ref_map.clear()
        # I4: clear _branch_index so progressive data doesn't leak
        self._branch_index.clear()

        highlight_on = await self._is_highlight_enabled()

        # I2: clean old DOM stamps before applying new ones
        if highlight_on:
            await self._page.evaluate(
                'document.querySelectorAll("[data-ybu-ref]")'
                '.forEach(el => el.removeAttribute("data-ybu-ref"));'
                'document.querySelectorAll("[data-ybu-prog-label]")'
                '.forEach(el => el.removeAttribute("data-ybu-prog-label"))'
            )

        name_counter: dict[str, int] = {}
        for i, el in enumerate(elements):
            ref = f"{A11Y_REF_PREFIX}{i}"
            name = el["name"] or ""
            if name:
                key = f"{el['role']}:{name}"
            else:
                key = f"{el['role']}:__empty__:{i}"
            name_counter[key] = name_counter.get(key, 0) + 1
            nth = name_counter[key] - 1

            el["ref"] = ref
            el["nth"] = nth
            el["prog_label"] = ref.lstrip("@")
            # CSS attribute selector matching the data-ybu-ref stamped below
            el["selector"] = f'[data-ybu-ref="{ref}"]'

            locator = self._page.get_by_role(el["role"], name=el["name"], exact=True)
            locator = locator.nth(nth)

            if highlight_on:
                try:
                    await locator.evaluate(
                        f'el => el.setAttribute("data-ybu-ref", {_json.dumps(ref)})'
                    )
                except Exception:
                    logger.warning("Set ref attr failed for %s", ref, exc_info=True)

            self._ref_map[ref] = {
                "ref": ref, "role": el["role"], "name": el["name"], "nth": nth,
                "selector": el["selector"],
            }

        self._last_highlight_elements = list(elements)
        await self.ensure_highlights()

        # Strip ref from public elements
        public_elements = [{k: v for k, v in el.items() if k != "ref"} for el in elements]
        return {
            "elements": public_elements, "mode": "a11y",
            "url": self._page.url,
            "title": await self._page.title(),
        }

    async def _progressive_snapshot(self, query: str = "") -> dict:
        """CDP DOM walk + two-phase density-adaptive disclosure.

        Phase 1: full-depth walk collecting every interactive element.
        Phase 2: density detection → shallow sampling for dense containers.
        """
        await self._ensure_page()
        self._ref_map.clear()

        highlight_on = await self._is_highlight_enabled()
        if highlight_on:
            await self._page.evaluate(
                'document.querySelectorAll("[data-ybu-ref]")'
                '.forEach(el => el.removeAttribute("data-ybu-ref"));'
                'document.querySelectorAll("[data-ybu-prog-label]")'
                '.forEach(el => el.removeAttribute("data-ybu-prog-label"))'
            )

        cdp = await self._context.new_cdp_session(self._page)
        try:
            CDP_TIMEOUT = 8.0
            doc = await asyncio.wait_for(
                cdp.send("DOM.getDocument", {"depth": -1, "pierce": True}),
                timeout=CDP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.debug("_progressive_snapshot: DOM.getDocument timed out")
            return {"elements": [], "folded": [], "mode": "progressive"}
        finally:
            await cdp.detach()

        # Phase 1: full-depth walk
        state = CollectState(ref_map=self._ref_map)
        state.walk(doc.get("root", {}))

        # Phase 2: build LLM view
        view_elements, folded, branch_index = build_llm_view(state)

        # Filter by query if provided (generic field matching)
        if query:
            view_elements = [e for e in view_elements if _match(e, query)]
            # Re-stamp kept refs after filter
            kept_refs = {e["ref"] for e in view_elements}
            for el in state.elements_all:
                el["_in_view"] = el["ref"] in kept_refs
            for f in folded:
                f["sampled"] = sum(
                    1 for ref in f.get("_sampled_refs", []) if ref in kept_refs
                )

        # Stamp via CDP backendNodeId (single session reused)
        if highlight_on:
            cdp_stamp = await self._context.new_cdp_session(self._page)
            try:
                for el in view_elements:
                    try:
                        bid = int(el["backendNodeId"])
                        result = await cdp_stamp.send("DOM.resolveNode", {"backendNodeId": bid})
                        await cdp_stamp.send("Runtime.callFunctionOn", {
                            "objectId": result["object"]["objectId"],
                            "functionDeclaration": (
                                f'function() {{'
                                f' this.setAttribute("data-ybu-ref", {_json.dumps(el["ref"])});'
                                f' this.setAttribute("data-ybu-prog-label", {_json.dumps(el["_prog_label"])});'
                                f'}}'
                            ),
                        })
                    except Exception:
                        logger.warning("Prog-highlight stamp failed", exc_info=True)
            finally:
                await cdp_stamp.detach()

        self._branch_index = branch_index
        self._last_highlight_elements = list(view_elements)
        self._per_page_elements[id(self._page)] = list(view_elements)
        await self.ensure_highlights()

        # Strip private fields AND ref before returning to LLM
        show_hidden = bool(query)
        public_elements = []
        for el in view_elements:
            pub = {}
            for k, v in el.items():
                if k.startswith("_") or k == "ref":
                    continue
                if (k in ("hidden", "aria_hidden")) and not show_hidden:
                    continue
                pub[k] = v
            public_elements.append(pub)
        public_folded = [{k: v for k, v in f.items() if not k.startswith("_")}
                         for f in folded]

        return {
            "elements": public_elements,
            "folded_containers": public_folded,
            "branch_index": {k: len(v) for k, v in branch_index.items()},
            "mode": "progressive",
            "url": self._page.url,
            "title": await self._page.title(),
            "folded_note": (
                "Folded containers hold dense interactive regions (product feeds, nav menus, lists). "
                "Use snapshot(expand_key='c_N') to browse inside. "
                "Each container sampled a few representative items — the rest are hidden to save context."
            ),
        }

    async def expand_branch(self, key: str, limit: int = 30, offset: int = 0) -> dict:
        """Expand a folded container branch — pure in-memory, zero CDP round-trips."""
        if key not in self._branch_index:
            return {"elements": [], "total": 0, "error": "container not found"}
        idxs = self._branch_index[key]
        total = len(idxs)
        page = []
        for idx in idxs[offset:offset + limit]:
            el = self._ref_map.get(idx)
            if not el:
                continue
            page.append({k: v for k, v in el.items() if not k.startswith("_") and k != "ref"})
        return {
            "elements": page, "total": total, "returned": len(page),
            "offset": offset, "has_more": (offset + len(page)) < total,
        }

    async def _wait_for_highlight_render(self, timeout_ms: int = 500) -> None:
        """Wait for highlight overlay DOM to be mounted and at least one frame rendered.

        Call before screenshot(image=True) — ensure_highlights() is fire-and-forget.
        """
        await self._ensure_page()
        try:
            await self._page.wait_for_function(
                "() => document.querySelector('.ybu-overlay-container') !== null || document.getElementById('ybu-highlights') !== null",
                timeout=timeout_ms,
            )
            await self._page.evaluate(
                "() => new Promise(r => requestAnimationFrame(r))"
            )
        except Exception:
            logger.warning("ensure_highlights wait/eval failed", exc_info=True)

    async def aria_snapshot(self) -> dict:
        """Snapshot via Playwright's ``aria_snapshot(mode='ai')`` — text-based accessibility tree.

        Returns ``{summary: str, mode: "aria"}``.
        Uses the browser's built-in accessibility engine — no JS injection, no CSP issues.
        The ``"ai"`` mode produces a LLM-optimized YAML-like tree of all interactive
        and semantic elements with their roles, accessible names, and hierarchy.
        """
        await self._ensure_page()
        text = await self._page.aria_snapshot(mode="ai")
        return {"summary": text, "mode": "aria"}


    async def capture_snapshot(self) -> dict:
        await self._ensure_page()
        result: dict = {}
        try:
            result["screenshot_base64"] = await self.screenshot()
        except Exception:
            logger.debug("capture_snapshot: screenshot failed", exc_info=True)
        try:
            result["html"] = await self._page.evaluate("document.documentElement.outerHTML")
        except Exception:
            logger.debug("capture_snapshot: html extraction failed", exc_info=True)
        try:
            meta_raw = await self._page.evaluate(
                "JSON.stringify({url: window.location.href, title: document.title})"
            )
            meta = _json.loads(meta_raw)
            result["url"] = meta.get("url", "")
            result["title"] = meta.get("title", "")
        except Exception:
            logger.debug("capture_snapshot: meta extraction failed", exc_info=True)
        return result

    # ------------------------------------------------------------------
    # Element mapping
    # ------------------------------------------------------------------

    async def reset_ref_map(self) -> None:
        self._ref_map = {}
        self._element_map = {}
        self._last_highlight_elements = []
        self._per_page_elements.clear()
        self._branch_index.clear()

    def get_element_by_index(self, ref: str) -> dict:
        if not self._ref_map:
            return {"ref": ref, "error": "no highlights injected"}

        raw = ref.strip()
        if raw.startswith("@"):
            if raw.startswith("@e") and not raw.startswith("@e_") and raw[2:].isdigit():
                normalized = "@e_" + raw[2:]
            else:
                normalized = raw
        elif raw.startswith("e_"):
            normalized = "@" + raw
        elif raw.startswith("e") and raw[1:].isdigit():
            normalized = "@e_" + raw[1:]
        else:
            normalized = "@e_" + raw

        el = self._ref_map.get(normalized)
        if el is None:
            return {"ref": normalized, "error": "not found"}

        return {
            "ref": el.get("ref", normalized),
            "tag": el.get("tag", ""),
            "type": el.get("type", ""),
            "text": el.get("text", ""),
            "selector": el.get("selector", ""),
            "bounds": {
                "x": el.get("x", 0),
                "y": el.get("y", 0),
                "w": el.get("width", 0),
                "h": el.get("height", 0),
            },
        }
