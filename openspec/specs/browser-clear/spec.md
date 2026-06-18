## ADDED Requirements

### Requirement: browser_clear 工具
系统 MUST 提供 `browser_clear` 工具，默认通过 JS 模式（`page.evaluate()` 设置 `value=""`）清空输入框，也可指定 `mode="pw"` 使用 Playwright `locator.clear()`。

#### Scenario: 默认 JS 模式清空
- **WHEN** LLM 调用 `browser_clear(selector="#search")` 不传 mode
- **THEN** executor 调用 `bridge.clear("#search", "js")`（默认 mode 为 `"js"`）
- **AND** 通过 `page.evaluate()` 设置 `element.value = ""`
- **AND** 返回 `{"result": {"selector": "#search"}}`

#### Scenario: Playwright 模式清空
- **WHEN** LLM 调用 `browser_clear(selector="#search", mode="pw")`
- **THEN** executor 调用 `bridge.clear("#search", "pw")`
- **AND** Playwright 自动聚焦、全选、删除内容
