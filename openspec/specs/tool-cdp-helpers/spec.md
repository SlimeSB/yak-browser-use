## MODIFIED Requirements

### Requirement: ToolCDPHelpers 构造参数变更
`ToolCDPHelpers.__init__` MUST 从接受 `CDPHelpers` 改为接受 `PlaywrightBridge`，所有方法改为直接调用 bridge 方法。

#### Scenario: 构造参数变更
- **WHEN** 创建 `ToolCDPHelpers(bridge)` 传入 `PlaywrightBridge` 实例
- **THEN** 内部持有 `self._bridge` 引用
- **AND** 不再依赖 `CDPHelpers` 实例

#### Scenario: click 方法透传
- **WHEN** 工具脚本调用 `tool_cdp.click("#btn")`
- **THEN** `ToolCDPHelpers` 通过 `self._bridge.click("#btn")` 执行
- **AND** circuit breaker 在调用前后检查/重置失败计数

#### Scenario: fill 方法透传
- **WHEN** 工具脚本调用 `tool_cdp.fill("#input", "hello")`
- **THEN** `ToolCDPHelpers` 通过 `self._bridge.fill("#input", "hello")` 执行

#### Scenario: snapshot 方法透传
- **WHEN** 工具脚本调用 `tool_cdp.snapshot(mode="interactive")`
- **THEN** `ToolCDPHelpers` 通过 `self._bridge.simplify_dom()` 执行

### Requirement: ToolCDPHelpers evaluate 方法
`ToolCDPHelpers` MUST 新增 `evaluate(js)` 方法，透传 `bridge.evaluate()`，供 `extract.py` 等工具跑任意 JS。

#### Scenario: 执行任意 JS
- **WHEN** 工具脚本调用 `tool_cdp.evaluate("document.title")`
- **THEN** `ToolCDPHelpers` 通过 `self._bridge.evaluate("document.title")` 执行
- **AND** circuit breaker 在调用前后检查/重置失败计数
- **AND** 返回 JS 执行结果

### Requirement: ToolCDPHelpers circuit breaker 保留
`ToolCDPHelpers` MUST 保留 circuit breaker 逻辑：连续失败 3 次后抛出 `RuntimeError`，成功后重置计数。

#### Scenario: 连续失败触发熔断
- **WHEN** 工具脚本连续 3 次调用均失败
- **THEN** 第 4 次调用时 `_check_failures()` 抛出 `RuntimeError("Circuit breaker: 3 consecutive failures")`

#### Scenario: 成功后重置计数
- **WHEN** 工具脚本在失败后成功调用一次
- **THEN** `_fail_count` 重置为 0
- **AND** 后续调用不受熔断限制
