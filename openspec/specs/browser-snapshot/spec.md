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

### Requirement: browser_snapshot 重数据剥离
`_apply_heavy_data_filter` 中 browser_snapshot 的重数据剥离逻辑 MUST 当场构建 summary 返回，不再依赖 scratchpad 持久化存储。

对于 a11y / interactive / progressive 模式，直接从 snapshot 返回结果中提取 elements、url、title，调用内联的 `_build_snapshot_summary(elements, url, title)` 生成中文摘要，替换 `result_dict["result"]`。

对于 full 模式，剥离 `screenshot_base64` 和 `html` 字段，返回简短的确认消息，不再将 HTML 写入 scratchpad。

#### Scenario: a11y 模式当场生成摘要
- **WHEN** LLM 调用 `browser_snapshot(mode="a11y")` 且结果包含 15 个 elements
- **THEN** `_apply_heavy_data_filter` 从 `result_payload` 提取 `elements`、`url`、`title`
- **AND** 调用 `_build_snapshot_summary(elements, url, title)` 当场生成中文摘要
- **AND** `result_dict["result"]` 替换为该摘要字符串
- **AND** 不调用任何 scratchpad 函数

#### Scenario: progressive 模式当场生成摘要
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive")` 且结果包含 elements 和 folded_containers
- **THEN** `_apply_heavy_data_filter` 当场生成包含元素列表的摘要
- **AND** `result_dict["result"]` 替换为该摘要字符串
- **AND** 不持久化 elements 到任何外部存储

#### Scenario: full 模式剥离重数据
- **WHEN** LLM 调用 `browser_snapshot(mode="full")` 且结果包含 screenshot_base64 和 html
- **THEN** `_apply_heavy_data_filter` 从 `result_dict` 中移除 `screenshot_base64` 和 `html`
- **AND** `result_dict["result"]` 替换为 "📸 完整快照已获取（含截图+HTML）"
- **AND** 不将 HTML 写入 scratchpad

#### Scenario: aria 模式不处理（含降级）
- **WHEN** LLM 调用 `browser_snapshot(mode="aria")`，无论是否降级
- **THEN** `_apply_heavy_data_filter` 直接返回，不修改 result
- **AND** 不写入任何存储
- **AND** 降级场景由 LLM 自行判断是否需要换模式重新 snapshot

### Requirement: snapshot 摘要生成函数
系统 MUST 在 `tool_executor.py` 中提供 `_build_snapshot_summary(elements, url, title)` 函数，输入为独立的 elements 列表、url 字符串、title 字符串，输出中文摘要文本。行为等价于原 `scratchpad._build_summary()`。

#### Scenario: 有标题和元素
- **WHEN** `_build_snapshot_summary(elements, "https://example.com", "示例页面")` 被调用且 elements 有 10 个元素
- **THEN** 摘要包含 "页面标题: 示例页面"、"页面URL: https://example.com"、"10个可交互元素"
- **AND** 每个元素格式为 `@e_0 <button> "点击我" [data-testid=btn]`

#### Scenario: 无数据
- **WHEN** `_build_snapshot_summary([], "", "")` 被调用
- **THEN** 返回 "页面快照已获取"
