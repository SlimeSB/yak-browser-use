## 1. 准备与基础改造

- [x] 1.1 在 `CDPHelpers.__init__` 中添加 `use_stable_refs: bool = False` 参数，新增 `_ref_map: dict[str, dict]` 属性
- [x] 1.2 新增 `reset_ref_map()` 方法：清空 `_ref_map`，供 `browser_goto` 后调用

## 2. 核心实现 — CDP backend_node_id 解析与映射持久化

- [x] 2.1 实现 `_resolve_backend_refs(elements: list[dict]) -> list[dict]`：对每个元素用 `DOM.querySelector` + `DOM.describeNode` 获取 `backendNodeId`，替换 `ref` 为 `@e_XXXXX`；匹配失败或异常时降级为 `@e_unknown_{N}`（N 自增，避免多元素冲突）
- [x] 2.2 修改 `add_dom_highlights()`：新模式先调 `_resolve_backend_refs()` 再构建 `_ref_map`（增量更新：已存在 key 保留仅更新位置，新元素新增）；注入的 JS 代码中禁用 MutationObserver 和 ResizeObserver
- [x] 2.3 修改 `capture_snapshot_interactive()`：新模式在 JS scan 后、highlight 前调用 `_resolve_backend_refs()`，确保返回给调用方的 elements 包含 `@e_XXXXX` ref；`_resolve_backend_refs` 异常时降级使用 JS 原始 `@eN` ref
- [x] 2.4 修改 `capture_snapshot_simplified()`：新模式跳过 `add_dom_highlights()` 调用，避免 `@e1..@eN` 污染持久化映射
- [x] 2.5 修改 `remove_dom_highlights()`：新模式仅移除 DOM 高亮元素，不清空 `_ref_map`
- [x] 2.6 修改 `get_element_by_index()`：ref 归一化逻辑兼容 `@e_XXXXX` 格式（`@e_12345`、`e_12345` → `@e_12345`；纯数字 `12345` 依赖 `use_stable_refs` 参数区分格式），同时保持旧 `@eN` 格式兼容

## 3. 编排层改造

- [x] 3.1 修改 `tool_executor.py` 第 148 行 auto-refresh list：新模式加入 `"browser_scroll"`，使 scroll 后自动调用 `add_dom_highlights()`
- [x] 3.2 修改 `_normalize_ref(ref, use_stable_refs=False)`：新增 `use_stable_refs` 参数区分纯数字输入的格式选择；`@e_XXXXX` 和 `e_XXXXX` 前缀可自动识别无需此参数；保持旧格式兼容
- [x] 3.3 修改 `executor.py` 的 `execute_browser_op`：`browser_goto` 成功后调用 `cdp_helpers.reset_ref_map()`（仅新模式）

## 4. 工具描述与提示词更新

- [x] 4.1 更新 `tools.py` 中 `browser_snapshot` 的 description：说明 interactive 模式返回 `@e_XXXXX` 格式（新模式）或 `@eN` 格式（旧模式）
- [x] 4.2 更新 `tools.py` 中 `browser_get_element_by_number` 的 description：说明 ref 支持 `@e_XXXXX` 格式
- [x] 4.3 更新 `system.md`：在工具列表下方追加滚动指引和稳定 ref 说明
- [x] 4.4 更新 `tool_strategy.md`：追加滚动指引

## 5. 验证与收尾

- [x] 5.1 验证旧模式（`use_stable_refs=False`）零行为变化：snapshot 返回 `@eN`、scroll 不触发 refresh、MutationObserver 正常、simplified 正常 highlight
- [x] 5.2 验证新模式功能正确性：snapshot 返回 `@e_XXXXX`、scroll 后同一元素 ref 不变、goto 清空映射、simplified 不污染映射、remove 不清空映射、ref 归一化正确
- [x] 5.3 运行现有测试确保无回归
