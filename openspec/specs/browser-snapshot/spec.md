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

### Requirement: browser_snapshot 支持 expand_key 参数
`browser_snapshot` 工具 MUST 新增可选参数 `expand_key`，在 `mode="progressive"` 时指定要展开的折叠容器 key，替代独立的 `browser_expand_branch` op。

#### Scenario: snapshot 同时展开容器
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", expand_key="c_0")`
- **THEN** executor 先执行 progressive snapshot，然后展开 `c_0` 容器
- **AND** 返回结果中包含展开后的元素

### Requirement: browser_expand_branch op 移除
系统 MUST 从 `_BROWSER_OPS`、`execute_browser_op()`、`execute_browser_step()` 中移除 `expand_branch` op。

#### Scenario: 旧 pipeline 使用 expand_branch 会报错
- **WHEN** preser 模式执行到 `{type: expand_branch, key: "c_0"}` 步骤
- **THEN** `execute_browser_op()` 返回 `Unknown browser op type: expand_branch`

### Requirement: execute_browser_op snapshot 参数变更
`execute_browser_op()` 中 snapshot handler 的参数 MUST 从 `cdp_helpers` 改为 `bridge: PlaywrightBridge`。

#### Scenario: snapshot op 使用 bridge
- **WHEN** `execute_browser_op("snapshot", params, bridge, element_map)` 被调用
- **THEN** 所有 snapshot 方法调用均通过 `bridge` 而非 `cdp_helpers`
- **AND** `cdp_helpers.capture_snapshot_interactive()` 改为 `bridge.simplify_dom()`
- **AND** `cdp_helpers.capture_snapshot()` 改为 `bridge.capture_snapshot()`
- **AND** `cdp_helpers.js()` 改为 `bridge.evaluate()`
