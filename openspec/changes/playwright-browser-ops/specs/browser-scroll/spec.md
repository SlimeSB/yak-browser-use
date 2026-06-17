## MODIFIED Requirements

### Requirement: browser_scroll 底层实现
`browser_scroll` 工具的底层实现 MUST 从 CDP `Runtime.evaluate` 改为 Playwright `page.evaluate()`，行为等价。executor 构建 `window.scrollBy()` JS 代码后通过 `bridge.evaluate()` 执行。

#### Scenario: 向下滚动
- **WHEN** LLM 调用 `browser_scroll(direction="down", amount=300)`
- **THEN** executor 构建 `window.scrollBy(0, 300)` JS 代码
- **AND** 通过 `bridge.evaluate(js_code)` 执行（不使用 `bridge.scroll()` 封装方法，scroll 操作直接走 evaluate）
- **AND** 返回 `{"result": {"direction": "down", "amount": 300}}`

#### Scenario: 向上滚动
- **WHEN** LLM 调用 `browser_scroll(direction="up", amount=300)`
- **THEN** executor 构建 `window.scrollBy(0, -300)` JS 代码
- **AND** 通过 `bridge.evaluate(js_code)` 执行

#### Scenario: 默认参数
- **WHEN** LLM 调用 `browser_scroll()` 不传参数
- **THEN** 默认 `direction="down"`、`amount=300`
