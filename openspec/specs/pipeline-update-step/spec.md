## ADDED Requirements

### Requirement: 增量修改步骤
系统 MUST 提供 `pipeline_update_step` 工具，允许 Agent 修改 pipeline 中某个步骤的指定字段，而非全量替换。

#### Scenario: 修改 browser_ops
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.browser_ops`
- **THEN** 目标步骤的 `browser_ops` 被替换为新值，`tool_name` 和 `goal_description` 被清除
- **AND** 修改后的 pipeline 通过 Pydantic 验证后写入文件
- **AND** 通过 WebSocket 推送 `pipeline.edit` 事件

#### Scenario: 修改 description
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.description`
- **THEN** 目标步骤的 `description` 被更新，其他字段不变

#### Scenario: 修改 tool_name
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.tool_name`
- **THEN** 目标步骤的 `tool_name` 被更新，`browser_ops` 和 `goal_description` 被清除

#### Scenario: 修改 goal_description
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.goal_description`
- **THEN** 目标步骤的 `goal_description` 被更新，`browser_ops` 和 `tool_name` 被清除

#### Scenario: 修改 depends_on
- **WHEN** Agent 调用 `pipeline_update_step` 并传入 `updates.depends_on`
- **THEN** 目标步骤的 `depends_on` 被替换为新值

#### Scenario: updates 为空对象
- **WHEN** Agent 调用 `pipeline_update_step` 但 `updates` 为空对象 `{}`
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息，文件不被修改

#### Scenario: 步骤不存在
- **WHEN** Agent 调用 `pipeline_update_step` 但 `step_name` 在 pipeline 中不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 目标 pipeline 不存在
- **WHEN** Agent 调用 `pipeline_update_step` 但 `pipeline_name` 对应的文件不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 修改导致类型互斥冲突
- **WHEN** 修改后的步骤同时包含 `browser_ops` 和 `tool_name`
- **THEN** Pydantic 验证失败，返回错误，文件不被修改
