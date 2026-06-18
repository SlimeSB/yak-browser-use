## ADDED Requirements

### Requirement: browser_select 工具
系统 MUST 提供 `browser_select` 工具，通过 Playwright `selectOption()` 实现下拉选择操作。

#### Scenario: 按值选择
- **WHEN** LLM 调用 `browser_select(selector="#country", value="CN", mode="value")`
- **THEN** executor 调用 `bridge.select("#country", "CN", "value")`
- **AND** Playwright 通过 `locator.selectOption("CN")` 选择对应选项
- **AND** 返回 `{"result": {"selector": "#country"}}`

#### Scenario: 按标签选择
- **WHEN** LLM 调用 `browser_select(selector="#country", value="中国", mode="label")`
- **THEN** executor 调用 `bridge.select("#country", "中国", "label")`
- **AND** Playwright 通过 `locator.selectOption({label: "中国"})` 选择

#### Scenario: 按索引选择
- **WHEN** LLM 调用 `browser_select(selector="#country", value="2", mode="index")`
- **THEN** executor 将 `value` 字符串 `"2"` 转为整数后调用 `bridge.select("#country", 2, "index")`
- **AND** Playwright 通过 `locator.selectOption({index: 2})` 选择
