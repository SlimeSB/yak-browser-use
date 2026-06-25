## RENAMED Requirements

### Requirement: browser_get_element_by_number → browser_lookup_selector
系统 MUST 将 `browser_get_element_by_number` 重命名为 `browser_lookup_selector`，功能不变但语义更清晰。
- **FROM:** `browser_get_element_by_number(ref)`
- **TO:** `browser_lookup_selector(ref)`

### Requirement: browser_lookup_selector 每次刷新缓存
`browser_lookup_selector` 每次调用 MUST 先执行 `ensure_highlights()` 刷新页面元素映射，再从最新的 `element_map` 中查询 ref。

#### Scenario: 查询元素 selector
- **WHEN** LLM 调用 `browser_lookup_selector(ref="0-2-175")`
- **THEN** 系统先执行 `ensure_highlights()` 同步当前页面状态
- **AND** 从最新 element_map 查找对应 ref
- **AND** 返回 `{ref, selector, tag, text}`
