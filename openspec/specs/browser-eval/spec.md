## MODIFIED Requirements

### Requirement: browser_eval 底层实现
`browser_eval` 工具的底层实现 MUST 从 CDP `Runtime.evaluate` 改为 Playwright `page.evaluate()`，行为等价。

#### Scenario: 执行 JavaScript 代码
- **WHEN** LLM 调用 `browser_eval(code="document.title")`
- **THEN** executor 调用 `bridge.evaluate("document.title")`
- **AND** 通过 `page.evaluate()` 在浏览器中执行 JS
- **AND** 返回 JS 执行结果

#### Scenario: 执行复杂 JS 表达式
- **WHEN** LLM 调用 `browser_eval(code="Array.from(document.querySelectorAll('a')).map(a => a.href)")`
- **THEN** executor 调用 `bridge.evaluate(code)`
- **AND** 返回 JS 执行结果（数组等复杂类型由 Playwright 自动序列化）
