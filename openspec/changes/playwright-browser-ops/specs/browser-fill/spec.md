## MODIFIED Requirements

### Requirement: browser_fill 底层实现
`browser_fill` 工具的底层实现 MUST 从 CDP `Input.insertText` 改为 Playwright `locator.fill()`，利用 Playwright 的 auto-wait 特性。

#### Scenario: 填充输入框
- **WHEN** LLM 调用 `browser_fill(selector="#search", text="hello")`
- **THEN** executor 调用 `bridge.fill("#search", "hello")`
- **AND** Playwright 自动聚焦、清空已有内容、逐字输入
- **AND** 触发完整事件链（focus/input/keydown/keyup/change）
- **AND** 返回 `{"result": {"selector": "#search"}}`

#### Scenario: 填充 @eN 引用元素
- **WHEN** LLM 调用 `browser_fill(selector="@e3", text="hello")`
- **THEN** executor 通过 `_resolve_element_ref("@e3", element_map, bridge)` 解析为 CSS 选择器
- **AND** 调用 `bridge.fill(resolved_selector, "hello")`

#### Scenario: 追加输入（不自动清空）
- **WHEN** LLM 需要追加输入而非替换
- **THEN** LLM 应使用 `browser_focus(selector="#input")` + `browser_type_text(text=" suffix")` 组合
- **AND** `browser_fill` 的 tool description 中注明此行为

### Requirement: browser_fill 行为变化说明
`browser_fill` 的 tool description MUST 明确说明该操作会自动清空已有内容再填入，追加输入请使用 `browser_focus` + `browser_type_text`。

#### Scenario: LLM 知晓行为差异
- **WHEN** LLM 读取 `browser_fill` 的 tool schema
- **THEN** description 中包含"自动清空已有内容"的说明
- **AND** 包含"追加输入请使用 browser_focus + browser_type_text"的提示
