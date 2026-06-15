## Why

当前 `browser_snapshot(mode="interactive")` 返回的 `@e1` ~ `@e50` 是基于当前视口可见元素的顺序索引。每次滚动后元素顺序改变，同一个按钮在滚动前是 `@e3`、滚动后变成 `@e7`，LLM 无法跨 turn 可靠引用同一元素。用户滚动页面后想点击之前看到的按钮，必须重新 snapshot 再重新理解编号，体验很差。

更根本的问题是：LLM 看到的始终只是当前视口切片，而 `@eN` 这种无语义的临时编号让跨 turn 引用完全不可靠。Chrome DevTools Protocol 为每个 DOM 节点分配了唯一的 `backendNodeId`，在节点生命周期内绝对稳定，是天然的持久化编号方案。

## What Changes

- **新增** `CDPHelpers` 的 `use_stable_refs` 开关（默认 `False`，零行为变化）
- **新增** `_resolve_backend_refs()` 方法：通过 CDP 批量获取 `backendNodeId`，替换 JS 自分配的 `@eN` 为 `@e_XXXXX`
- **新增** `reset_ref_map()` 方法：页面导航时清空持久化映射
- **修改** `_element_map` → `_ref_map`：旧模式每次清空重建，新模式页面内持久、scroll 后增量更新
- **修改** `add_dom_highlights()`：新模式先 resolve backend refs 再注入 highlight，禁用 MutationObserver 重绘（避免 badge 显示错误 ref）
- **修改** `capture_snapshot_interactive()`：新模式在 highlight 之前完成 ref 解析
- **修改** `capture_snapshot_simplified()`：新模式跳过 `add_dom_highlights()` 调用（避免用 `@e1..@eN` 污染持久化映射）
- **修改** `remove_dom_highlights()`：新模式不清空持久化映射
- **修改** `get_element_by_index()`：ref 归一化逻辑兼容 `@e_XXXXX` 格式
- **修改** `tool_executor.py`：auto-refresh list 加入 `browser_scroll`；`_normalize_ref` 兼容 `@e_XXXXX` 格式
- **修改** `tools.py`：更新 `browser_snapshot` 和 `browser_get_element_by_number` 的 description
- **修改** `system.md` / `tool_strategy.md`：添加滚动指引和稳定 ref 说明

## Capabilities

### New Capabilities
- `stable-element-refs`: 使用 CDP backend_node_id 作为持久化元素编号，scroll 后同一元素编号不变

### Modified Capabilities
- `browser-snapshot`: interactive 模式返回的元素 ref 格式从 `@eN` 变为 `@e_XXXXX`（仅新模式）
- `dom-highlight-numbering`: 编号注入/移除/查询兼容 `@e_XXXXX` 格式；新模式禁用 MutationObserver
- `snapshot-interactive`: 新模式在 JS scan 后插入 CDP backend_node_id 解析步骤
- `browser-get-element`: ref 归一化兼容 `@e_XXXXX` 格式；scroll 后同步 scratchpad

## Impact

- **代码**：`backend/cdp/helpers.py`（核心改动 ~120 行）、`backend/engine/_harness/tool_executor.py`（~10 行）、`backend/engine/_harness/tools.py`（~10 行）、`backend/engine/executor.py`（~5 行）、`backend/prompts/chat/system.md`（~8 行）、`backend/prompts/guidance/tool_strategy.md`（~8 行）
- **JS 侧**：`backend/assets/simplify-dom.js` 完全不动
- **破坏性**：无。`use_stable_refs=False`（默认）保持完全向后兼容
- **性能**：新模式每次 snapshot 增加 50 次 CDP 调用（~500ms-1s），可接受；后续可批量优化
