## ADDED Requirements

### Requirement: browser_wait 工具
系统 MUST 提供 `browser_wait` 工具，通过 Playwright 的 `waitForSelector()` / `waitForLoadState()` 实现等待操作。

#### Scenario: 等待指定时间
- **WHEN** LLM 调用 `browser_wait(mode="time", duration=2000)`
- **THEN** executor 调用 `bridge.wait(mode="time", duration=2000)`
- **AND** bridge 内部通过 `asyncio.sleep(2)` 等待 2000 毫秒
- **AND** 返回 `{"result": {"mode": "time"}}`

#### Scenario: 等待元素出现
- **WHEN** LLM 调用 `browser_wait(mode="selector", selector="#result")`
- **THEN** executor 调用 `bridge.wait(mode="selector", selector="#result")`
- **AND** Playwright 通过 `page.waitForSelector("#result")` 等待元素出现

#### Scenario: 等待页面加载
- **WHEN** LLM 调用 `browser_wait(mode="load", state="networkidle")`
- **THEN** executor 调用 `bridge.wait(mode="load", state="networkidle")`
- **AND** Playwright 通过 `page.waitForLoadState("networkidle")` 等待网络空闲
