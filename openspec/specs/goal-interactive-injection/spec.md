## ADDED Requirements

### Requirement: @eN 引用解析

系统 MUST 通过 `_resolve_element_ref()` 函数在 `browser_click`、`browser_fill` 等工具 handler 中解析 `@eN` 和 `@e_XXXXX` 格式的引用为 CSS 引用。解析通过 `ensure_highlights()` 刷新的 `element_map` / `_ref_map` 进行查表。

#### Scenario: click handler 解析 @eN
- **WHEN** `_resolve_element_ref("@e3", element_map, bridge)` 被调用
- **THEN** 从 `element_map` 中查找 `@e3` 对应的 CSS selector
- **AND** 使用解析后的 CSS selector 调用 `bridge.click(resolved_selector)`

#### Scenario: fill handler 解析 @eN
- **WHEN** `_resolve_element_ref("@e3", element_map, bridge)` 被调用
- **THEN** 从 `element_map` 中查找 `@e3` 对应的 CSS selector
- **AND** 使用解析后的 CSS selector 调用 `bridge.fill(resolved_selector, "hello")`

#### Scenario: @eN 在映射表中不存在
- **WHEN** 收到 `@eN` 引用但映射表中无对应条目
- **THEN** 操作失败并返回错误信息 "Unknown element reference: @eN"

### Requirement: @eN 映射表维护

每次新的 `browser_snapshot(mode="progressive")` 或 `ensure_highlights()` 执行时 MUST 重建 `{ref: selector}` 映射表。新模式（`use_stable_refs=True`）使用 `_ref_map`（以 `@e_XXXXX` 为 key），旧模式（`use_stable_refs=False`）使用 `_element_map`（以 `@eN` 为 key）。

#### Scenario: 映射表生命周期
- **WHEN** 每次新的页面快照或高亮刷新执行
- **THEN** 映射表被重建（旧映射表被替换）

#### Scenario: 映射表创建
- **WHEN** `browser_snapshot(mode="progressive")` 返回 elements 数组
- **THEN** 系统构建 `{ref: selector}` 映射表（如 `{"@e1": "button#submit", "@e2": "input[name='q']"}`）
- **AND** 新模式下 ref 格式为 `@e_{backendNodeId}`
- **AND** 旧模式下 ref 格式为 `@e1..@eN`
