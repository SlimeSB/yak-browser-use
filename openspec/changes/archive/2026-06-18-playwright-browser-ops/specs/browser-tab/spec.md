## ADDED Requirements

### Requirement: browser_tab 工具
系统 MUST 提供 `browser_tab` 工具，通过 Playwright 的 `context.newPage()` / `bringToFront()` / `close()` 实现标签页管理。

#### Scenario: 新建标签页
- **WHEN** LLM 调用 `browser_tab(action="new", url="https://example.com")`
- **THEN** executor 调用 `bridge.tab_new("https://example.com")`
- **AND** Playwright 通过 `context.newPage()` 创建新标签页并导航
- **AND** 返回新标签页信息

#### Scenario: 切换标签页
- **WHEN** LLM 调用 `browser_tab(action="switch", target_id="ABC123")`
- **THEN** executor 调用 `bridge.tab_switch("ABC123")`
- **AND** Playwright 通过 `page.bringToFront()` 切换到目标标签页

#### Scenario: 关闭标签页
- **WHEN** LLM 调用 `browser_tab(action="close", target_id="ABC123")`
- **THEN** executor 调用 `bridge.tab_close("ABC123")`
- **AND** Playwright 通过 `page.close()` 关闭目标标签页

#### Scenario: 列出所有标签页
- **WHEN** LLM 调用 `browser_tab(action="list")`
- **THEN** executor 调用 `bridge.tab_list()`
- **AND** 返回所有标签页的 ID、URL、标题列表
