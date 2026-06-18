## MODIFIED Requirements

### Requirement: browser_source 底层实现
`browser_source` 工具的底层实现 MUST 从 CDP 方法改为 Playwright `page.content()`。

#### Scenario: 获取页面源码（不缓存）
- **WHEN** LLM 调用 `browser_source()` 不传 `cached` 或 `cached=false`
- **THEN** executor 调用 `bridge.source()`（内部通过 `page.content()` 获取完整 HTML）
- **AND** 返回 HTML 内容和长度

#### Scenario: 使用缓存
- **WHEN** LLM 调用 `browser_source(cached=true)`
- **THEN** executor 调用 `bridge.get_page_html(cached=True)` 从 `bridge._element_map` 读取缓存
- **AND** 缓存不存在时 fallback 到 `bridge.source()`
