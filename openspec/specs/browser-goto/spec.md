## MODIFIED Requirements

### Requirement: browser_goto 底层实现
`browser_goto` 工具的底层实现 MUST 从 CDP `Page.navigate` 改为 Playwright `page.goto()`，利用 Playwright 的 auto-wait 特性。

#### Scenario: 导航到 URL
- **WHEN** LLM 调用 `browser_goto(url="https://example.com")`
- **THEN** executor 调用 `bridge.goto("https://example.com")`
- **AND** Playwright 通过 `page.goto(url, wait_until="domcontentloaded")` 导航
- **AND** 自动等待 DOM 内容加载完成后返回
- **AND** 导航后自动调用 `bridge.reset_ref_map()` 清空元素映射
- **AND** 返回 `{"result": {"url": "https://example.com"}}`

#### Scenario: 导航失败
- **WHEN** URL 不可达或超时
- **THEN** Playwright 抛出超时异常
- **AND** executor 捕获并返回错误信息
