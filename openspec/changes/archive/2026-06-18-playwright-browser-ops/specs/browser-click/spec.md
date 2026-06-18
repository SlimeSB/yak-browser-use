## MODIFIED Requirements

### Requirement: browser_click 底层实现
`browser_click` 工具的底层实现 MUST 从 CDP `Input.dispatchMouseEvent` 改为 Playwright `locator.click()`，利用 Playwright 的 auto-wait/auto-scroll 特性。

#### Scenario: 点击指定选择器
- **WHEN** LLM 调用 `browser_click(selector="#btn")`
- **THEN** executor 调用 `bridge.click("#btn", click_count=1)`
- **AND** Playwright 自动等待元素可见、滚动到视口、dispatch 真实鼠标事件
- **AND** 返回 `{"result": {"selector": "#btn"}}`

#### Scenario: 双击
- **WHEN** LLM 调用 `browser_click(selector="#btn", clickCount=2)`
- **THEN** executor 调用 `bridge.click("#btn", click_count=2)`
- **AND** Playwright 执行双击操作

#### Scenario: 点击 @eN 引用元素
- **WHEN** LLM 调用 `browser_click(selector="@e3")`
- **THEN** executor 通过 `_resolve_element_ref("@e3", element_map, bridge)` 解析为 CSS 选择器
- **AND** 调用 `bridge.click(resolved_selector)`

#### Scenario: 点击失败
- **WHEN** 目标元素不存在或不可见
- **THEN** Playwright 抛出超时异常
- **AND** executor 捕获并返回错误信息

## ADDED Requirements

### Requirement: browser_click clickCount 参数
`browser_click` 工具的 schema MUST 新增可选的 `clickCount` 参数，默认值为 1，支持双击操作。

#### Scenario: 默认单击
- **WHEN** LLM 调用 `browser_click(selector="#btn")` 不传 `clickCount`
- **THEN** 默认 `clickCount=1`，执行单击

#### Scenario: 显式双击
- **WHEN** LLM 调用 `browser_click(selector="#btn", clickCount=2)`
- **THEN** 执行双击操作
