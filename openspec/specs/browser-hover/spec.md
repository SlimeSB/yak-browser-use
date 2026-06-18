## ADDED Requirements

### Requirement: browser_hover 工具
系统 MUST 提供 `browser_hover` 工具，通过 Playwright `locator.hover()` 实现鼠标悬停操作，自动等待元素可见并滚动到视口。

#### Scenario: 悬停指定元素
- **WHEN** LLM 调用 `browser_hover(selector="#menu")`
- **THEN** executor 调用 `bridge.hover("#menu")`
- **AND** Playwright 自动等待元素可见、滚动到视口、dispatch 真实 mouseMoved 事件
- **AND** 返回 `{"result": {"selector": "#menu"}}`

#### Scenario: 悬停 @eN 引用元素
- **WHEN** LLM 调用 `browser_hover(selector="@e3")`
- **THEN** executor 通过 `_resolve_element_ref("@e3", element_map, bridge)` 解析为 CSS 选择器
- **AND** 调用 `bridge.hover(resolved_selector)`

#### Scenario: 悬停失败
- **WHEN** 目标元素不存在或不可见
- **THEN** Playwright 抛出超时异常
- **AND** executor 捕获并返回错误信息
