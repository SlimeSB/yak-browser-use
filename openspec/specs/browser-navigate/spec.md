## ADDED Requirements

### Requirement: browser_navigate 工具
系统 MUST 提供 `browser_navigate` 工具，通过 Playwright 的 `page.goBack()` / `goForward()` / `reload()` 实现页面导航操作。

#### Scenario: 后退
- **WHEN** LLM 调用 `browser_navigate(action="back")`
- **THEN** executor 调用 `bridge.navigate("back")`
- **AND** Playwright 通过 `page.goBack()` 返回上一页
- **AND** 等待导航完成后返回 `{"result": {"action": "back"}}`

#### Scenario: 前进
- **WHEN** LLM 调用 `browser_navigate(action="forward")`
- **THEN** executor 调用 `bridge.navigate("forward")`
- **AND** Playwright 通过 `page.goForward()` 前进

#### Scenario: 刷新
- **WHEN** LLM 调用 `browser_navigate(action="reload")`
- **THEN** executor 调用 `bridge.navigate("reload")`
- **AND** Playwright 通过 `page.reload()` 刷新页面
