## MODIFIED Requirements

### Requirement: browser_snapshot 底层实现
`browser_snapshot` 工具的底层实现 MUST 从 CDP `Runtime.evaluate` 改为 Playwright `page.evaluate()`，行为等价。所有 snapshot 方法（`capture_snapshot`、`capture_snapshot_interactive`、`capture_snapshot_simplified`）均通过 `bridge.evaluate()` 或 `bridge.simplify_dom()` 执行。

#### Scenario: interactive 模式通过 bridge 执行
- **WHEN** LLM 调用 `browser_snapshot(mode="interactive")`
- **THEN** executor 调用 `bridge.simplify_dom()` 而非 CDP `Runtime.evaluate`
- **AND** `bridge.simplify_dom()` 内部通过 `page.evaluate()` 运行 simplify-dom.js
- **AND** 返回结果格式与变更前一致

#### Scenario: full 模式通过 bridge 执行
- **WHEN** LLM 调用 `browser_snapshot(mode="full")`
- **THEN** executor 调用 `bridge.capture_snapshot()` 而非 CDP 方法
- **AND** `bridge.capture_snapshot()` 内部通过 `page.screenshot()` 和 `page.content()` 获取数据

#### Scenario: simplified 模式通过 bridge 执行
- **WHEN** LLM 调用 `browser_snapshot(mode="simplified")`
- **THEN** executor 调用 `bridge.evaluate()` 运行 TreeWalker 文本提取 JS
- **AND** 返回结果格式与变更前一致

### Requirement: execute_browser_op snapshot 参数变更
`execute_browser_op()` 中 snapshot handler 的参数 MUST 从 `cdp_helpers` 改为 `bridge: PlaywrightBridge`。

#### Scenario: snapshot op 使用 bridge
- **WHEN** `execute_browser_op("snapshot", params, bridge, element_map)` 被调用
- **THEN** 所有 snapshot 方法调用均通过 `bridge` 而非 `cdp_helpers`
- **AND** `cdp_helpers.capture_snapshot_interactive()` 改为 `bridge.simplify_dom()`
- **AND** `cdp_helpers.capture_snapshot()` 改为 `bridge.capture_snapshot()`
- **AND** `cdp_helpers.js()` 改为 `bridge.evaluate()`
