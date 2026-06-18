## ADDED Requirements

### Requirement: browser_focus 工具
系统 MUST 提供 `browser_focus` 工具，通过 Playwright `locator.focus()` 实现元素聚焦操作。

#### Scenario: 聚焦输入框
- **WHEN** LLM 调用 `browser_focus(selector="#search")`
- **THEN** executor 调用 `bridge.focus("#search")`
- **AND** Playwright 自动滚动到视口并聚焦元素
- **AND** 返回 `{"result": {"selector": "#search"}}`

#### Scenario: 聚焦后配合 keyboard 输入
- **WHEN** LLM 先调用 `browser_focus(selector="#input")` 再调用 `browser_type_text(text="hello")`
- **THEN** 文本追加到已有内容（不清空），适用于追加输入场景
