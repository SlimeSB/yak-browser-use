## ADDED Requirements

### Requirement: browser_unhover 工具
系统 MUST 提供 `browser_unhover` 工具，通过 Playwright `page.mouse.move(0, 0)` 将鼠标移开当前悬停元素。

#### Scenario: 取消悬停
- **WHEN** LLM 调用 `browser_unhover(selector="#menu")`
- **THEN** executor 调用 `bridge.unhover("#menu")`
- **AND** Playwright 通过 `page.mouse.move(0, 0)` 将鼠标移到页面左上角
- **AND** 返回 `{"result": {"selector": "#menu"}}`

#### Scenario: 配合 hover 使用
- **WHEN** LLM 先调用 `browser_hover(selector="#menu")` 再调用 `browser_unhover(selector="#menu")`
- **THEN** 菜单先展开后收起
- **AND** 鼠标回到页面左上角
