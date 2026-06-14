## ADDED Requirements

### Requirement: scratchpad 存储
系统 MUST 提供 `engine/scratchpad.py` 模块，用于存储浏览器操作产生的大体积数据（HTML、截图、@eN 元素列表），使其不进入 LLM messages 上下文。

#### Scenario: 存储快照数据
- **WHEN** 编排层调用 `scratchpad.store(snapshot_dict)`
- **THEN** 数据写入当前 session 对应的 `ScratchpadRecord`
- **AND** `ScratchpadRecord` 包含 `url`、`title`、`elements`、`element_map`、`raw_html`、`summary` 字段（首版不存截图，base64 太大且文件路径在纯内存 scratchpad 中无意义）
- **AND** `url` 和 `title` 来自 CDP helper 返回值（`capture_snapshot()` / `capture_snapshot_interactive()` 各自在一次 CDP eval 中获取 `window.location.href` 和 `document.title`）

#### Scenario: 读取缓存数据
- **WHEN** 调用 `scratchpad.get(session_id)`
- **THEN** 返回该 session 的 `ScratchpadRecord` 实例
- **AND** 如果 session 不存在则自动创建空 record

#### Scenario: 新快照覆盖旧数据
- **WHEN** 同一 session 内多次调用 `scratchpad.store()`
- **THEN** 每次调用覆盖前一次的 `url`、`title`、`elements`、`element_map`、`raw_html`、`summary`
- **AND** `summary` 根据最新数据重新生成

#### Scenario: session 隔离
- **WHEN** 使用不同 `session_id` 调用 `scratchpad.store()` 和 `scratchpad.get()`
- **THEN** 不同 session 的数据互不影响
- **AND** 默认 session_id 为 `"default"`

### Requirement: store_raw_html 增量更新
`scratchpad.store_raw_html()` MUST 只更新 `raw_html` 字段，不覆盖 `url`、`title`、`elements`、`element_map` 等其他字段。

#### Scenario: browser_source 后不破坏 snapshot 缓存
- **WHEN** LLM 先调 `browser_snapshot(interactive)` 再调 `browser_source()`
- **THEN** `browser_source` 通过 `store_raw_html()` 只更新 `raw_html`
- **AND** `url`、`title`、`elements`、`element_map` 保持 `browser_snapshot` 写入的值
- **AND** 后续 `browser_get_element_by_number` 仍能命中 scratchpad 缓存

#### Scenario: 独立调用 store_raw_html
- **WHEN** `scratchpad.store_raw_html("<html>...", session_id)` 被调用
- **THEN** 仅 `raw_html` 字段被更新
- **AND** 其他字段保持不变（如果 session 不存在则自动创建空 record）

### Requirement: element_map 自动构建
`scratchpad.store()` MUST 在存储 elements 列表时自动构建 `ref → selector` 映射表。

#### Scenario: 从 elements 构建 element_map
- **WHEN** `scratchpad.store()` 收到包含 `elements` 字段的 snapshot dict
- **THEN** 遍历 elements 列表，提取每个元素的 `ref` 和 `selector` 字段
- **AND** 构建 `{ref: selector}` 字典存入 `element_map`
- **AND** 跳过 `ref` 或 `selector` 为空的元素

#### Scenario: elements 为空时 element_map 为空
- **WHEN** `scratchpad.store()` 收到的 elements 为空列表
- **THEN** `element_map` 为空字典 `{}`

### Requirement: 摘要生成
`scratchpad._build_summary()` MUST 根据 `ScratchpadRecord` 的内容生成一行人类可读的摘要文本。

#### Scenario: 有标题和元素
- **WHEN** record 包含 `title="淘宝网"` 且 `elements` 有 15 个元素
- **THEN** 摘要为 `"页面标题: 淘宝网 | 15个可交互元素"`

#### Scenario: 仅有元素
- **WHEN** record 包含 `elements` 有 8 个元素但 `title` 为空
- **THEN** 摘要为 `"8个可交互元素"`

#### Scenario: 无数据
- **WHEN** record 的 `title` 为空且 `elements` 为空
- **THEN** 摘要为 `"页面快照已获取"`

### Requirement: element_map 同步
`scratchpad.sync_element_map()` MUST 支持从外部 elements 列表增量更新 `element_map`，不覆盖其他字段。

#### Scenario: 从 add_dom_highlights 结果同步
- **WHEN** 编排层调用 `scratchpad.sync_element_map(elements, session_id)`
- **THEN** 从 elements 列表重建 `element_map`（`{ref: selector}` 映射）
- **AND** 不覆盖 `url`、`title`、`raw_html` 等其他字段
- **AND** 如果 elements 为空则 `element_map` 清空

#### Scenario: 无 session 时自动创建
- **WHEN** `scratchpad.sync_element_map(elements, "new-session")` 被调用且 session 不存在
- **THEN** 自动创建新的 `ScratchpadRecord` 并设置 `element_map`
