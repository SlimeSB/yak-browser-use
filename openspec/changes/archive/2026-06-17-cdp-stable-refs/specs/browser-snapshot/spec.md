## MODIFIED Requirements

### Requirement: browser_snapshot mode 参数
`browser_snapshot` 工具的 schema MUST 新增可选的 `mode` 参数，支持 `interactive`、`full`、`simplified` 三种模式，默认值为 `interactive`。

#### Scenario: 默认 interactive 模式
- **WHEN** LLM 调用 `browser_snapshot()` 不传 mode 参数
- **THEN** 使用 `mode="interactive"`
- **AND** 调用 `capture_snapshot_interactive()` 获取元素列表
- **AND** 元素 ref 格式：旧模式为 `@eN`，新模式（`use_stable_refs=True`）为 `@e_XXXXX`
- **AND** 重数据（elements 完整列表）写入 scratchpad
- **AND** messages 中只保留摘要（如 `"📸 快照已获取（15个可交互元素），页面标题: 淘宝网"`）

#### Scenario: 显式指定 interactive 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="interactive")`
- **THEN** 行为与默认模式一致

#### Scenario: full 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="full")`
- **THEN** 调用 `capture_snapshot()` 获取截图和完整 HTML
- **AND** 重数据（screenshot_base64、html）写入 scratchpad
- **AND** messages 中只保留摘要（如 `"📸 完整快照已获取（含截图+HTML），数据已缓存"`）

#### Scenario: simplified 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="simplified")`
- **THEN** 调用 `capture_snapshot_simplified()` 获取文本摘要
- **AND** 数据量小，不隔离（直接返回摘要文本）

### Requirement: 编排层重数据过滤
`tool_executor.py` 的 `execute_tool_calls_sequential()` MUST 在工具结果回写 messages 前对 `browser_snapshot` 和 `browser_source` 的结果进行重数据摘录和 scratchpad 写入。

#### Scenario: interactive 模式过滤
- **WHEN** `browser_snapshot(mode="interactive")` 返回 `{result: {elements: [...], url: "...", title: "..."}}`
- **THEN** `elements`、`url`、`title` 写入 scratchpad
- **AND** `result_dict["result"]` 替换为摘要文本
- **AND** 摘要包含元素数量和页面标题

#### Scenario: full 模式过滤
- **WHEN** `browser_snapshot(mode="full")` 返回 `{screenshot_base64: "...", html: "...", result: {}}`
- **THEN** `screenshot_base64`、`html` 从 `result_dict` 顶层移除并写入 scratchpad
- **AND** `result_dict["result"]` 替换为摘要文本

#### Scenario: interactive 降级时重数据隔离
- **WHEN** `browser_snapshot(mode="interactive")` 返回 `{result: {elements: [], mode: "interactive", degraded: true, screenshot_base64: "...", html: "..."}}`
- **THEN** 编排层检测到 `degraded: true` 标记
- **AND** `screenshot_base64` 和 `html` 从 `result_dict["result"]` 中移除并写入 scratchpad
- **AND** `result_dict["result"]` 替换为摘要 `"📸 快照已获取（降级为 full 模式，0个可交互元素），数据已缓存"`
- **AND** 降级带来的大体积数据不进入 messages

#### Scenario: simplified 模式不过滤
- **WHEN** `browser_snapshot(mode="simplified")` 返回文本摘要
- **THEN** 不触发 scratchpad 写入
- **AND** 结果原样进入 messages

#### Scenario: browser_source 过滤
- **WHEN** `browser_source()` 返回 `{html: "<html>...", result: {length: 15000}}`
- **THEN** `html` 从 `result_dict` 顶层移除并写入 scratchpad
- **AND** `result_dict["result"]` 保留 `{length: 15000}`

#### Scenario: 非重数据工具不过滤
- **WHEN** `browser_click`、`browser_fill`、`browser_goto` 等工具返回结果
- **THEN** 不触发 scratchpad 写入
- **AND** 结果原样进入 messages

## ADDED Requirements

### Requirement: 新模式元素编号格式

系统 MUST 在 `use_stable_refs=True` 时，`browser_snapshot(mode="interactive")` 返回的元素使用 `@e_XXXXX` 格式（CDP backend_node_id），而非 `@eN` 顺序索引。

#### Scenario: 新模式返回 @e_XXXXX 格式
- **WHEN** `use_stable_refs=True` 且调用 `browser_snapshot(mode="interactive")`
- **THEN** 返回的 elements 中每个元素的 `ref` 字段格式为 `@e_{backendNodeId}`
- **AND** 同一元素在多次 snapshot 中 ref 保持不变（只要 DOM 不重建）

#### Scenario: 旧模式返回 @eN 格式
- **WHEN** `use_stable_refs=False` 且调用 `browser_snapshot(mode="interactive")`
- **THEN** 返回的 elements 中每个元素的 `ref` 字段格式为 `@e1..@eN`
- **AND** 行为与变更前完全一致
