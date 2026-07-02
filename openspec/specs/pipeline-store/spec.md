## ADDED Requirements

### Requirement: pipeline_create — 创建新 pipeline 预设
系统 MUST 提供 `pipeline_create` 工具，从步骤列表创建新的 pipeline 预设文件。

#### Scenario: 创建有效 pipeline
- **WHEN** Agent 调用 `pipeline_create` 并传入 `pipeline_name`、`description`、`steps` 数组
- **THEN** 新的 `.pipeline.yaml` 文件被写入预设目录
- **AND** 通过 WebSocket 推送 `pipeline.edit` 事件（original 为空字符串）
- **AND** 返回 JSON 包含 `ok: true`

#### Scenario: 创建已存在的 pipeline
- **WHEN** Agent 调用 `pipeline_create` 但同名文件已存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息，不覆盖已有文件

#### Scenario: pipeline_name 无效
- **WHEN** Agent 调用 `pipeline_create` 但 `pipeline_name` 为空字符串或含路径分隔符
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 步骤列表为空
- **WHEN** Agent 调用 `pipeline_create` 但 `steps` 为空数组
- **THEN** Pydantic 验证失败（`min_length=1`），返回错误

### Requirement: pipeline_load — 读取 pipeline 摘要
系统 MUST 提供 `pipeline_load` 工具，读取指定 pipeline 的结构化摘要，不返回完整 YAML 内容。

#### Scenario: 读取存在的 pipeline
- **WHEN** Agent 调用 `pipeline_load` 并传入有效的 `pipeline_name`
- **THEN** 返回 JSON 包含 `ok: true`、`name`、`description`、`step_count`、`required_params`、`steps` 数组
- **AND** 每个 step 包含 `name`、`type`（browser/tool/goal）、`description`、`tool_name`（可选）、`browser_op_count`（可选）

#### Scenario: 读取不存在的 pipeline
- **WHEN** Agent 调用 `pipeline_load` 但 pipeline 不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

### Requirement: pipeline_list — 列出所有 pipeline 预设
系统 MUST 提供 `pipeline_list` 工具，列出 workspace 下所有可用的 pipeline 预设文件。

#### Scenario: 存在多个预设
- **WHEN** Agent 调用 `pipeline_list`
- **THEN** 返回 JSON 包含 `ok: true` 和 `presets` 数组
- **AND** 每个 preset 包含 `name`、`description`、`step_count`

#### Scenario: 部分文件解析失败
- **WHEN** 某些 `.pipeline.yaml` 文件无法解析
- **THEN** 对应 preset 的 `description` 标注 `(parse error)`，`step_count` 为 0

### Requirement: pipeline_add_step — 追加或插入步骤
系统 MUST 提供 `pipeline_add_step` 工具，允许 Agent 在 pipeline 中追加新步骤或在指定步骤后插入。

#### Scenario: 追加到末尾
- **WHEN** Agent 调用 `pipeline_add_step` 不传 `after` 参数
- **THEN** 新步骤被追加到 `steps` 数组末尾

#### Scenario: 在指定步骤后插入
- **WHEN** Agent 调用 `pipeline_add_step` 并传入 `after` 参数指向存在的步骤名
- **THEN** 新步骤被插入到该步骤之后

#### Scenario: 锚点步骤不存在
- **WHEN** Agent 调用 `pipeline_add_step` 但 `after` 指向的步骤不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

### Requirement: pipeline_remove_step — 删除步骤
系统 MUST 提供 `pipeline_remove_step` 工具，删除指定步骤。

#### Scenario: 删除存在的步骤
- **WHEN** Agent 调用 `pipeline_remove_step` 并传入存在的 `step_name`
- **THEN** 该步骤从 `steps` 数组中移除
- **AND** 修改后的 pipeline 通过 Pydantic 验证后写入文件
- **AND** 通过 WebSocket 推送 `pipeline.edit` 事件

#### Scenario: 删除后 steps 为空
- **WHEN** 删除 pipeline 中唯一的步骤
- **THEN** Pydantic 验证失败（`min_length=1`），返回错误，文件不被修改

### Requirement: pipeline_update_step — 增量修改步骤
系统 MUST 提供 `pipeline_update_step` 工具，允许 Agent 修改 pipeline 中某个步骤的指定字段（单步或批量），而非全量替换。

#### Scenario: 修改 browser_ops
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.browser_ops`
- **THEN** 目标步骤的 `browser_ops` 被替换为新值，`tool_name` 和 `goal_description` 被清除

#### Scenario: 修改 description
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.description`
- **THEN** 目标步骤的 `description` 被更新，其他字段不变

#### Scenario: 批量更新多个 step
- **WHEN** Agent 调用 `pipeline_update_step(pipeline_name="bili", steps_updates={"step_1": {"browser_ops": [...]}, "step_3": {"description": "新描述"}})`
- **THEN** 系统一次性加载 pipeline.yaml，修改多个 step，验证通过后写盘
- **AND** 返回 `{"ok": True, "result": "已在 pipeline 'bili' 中批量更新 2 个步骤: step_1, step_3"}`

#### Scenario: 批量更新 all-or-nothing 语义
- **WHEN** 批量更新中某 step 不存在
- **THEN** 系统 MUST 返回错误，已成功更新的其他 step 变更也不写盘（内存操作回滚）

#### Scenario: 修改导致类型互斥冲突
- **WHEN** 修改后的步骤同时包含 `browser_ops` 和 `tool_name`
- **THEN** Pydantic 验证失败，返回错误，文件不被修改
