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

### Requirement: pipeline_update_step 支持 steps_updates 字典批量更新
`pipeline_update_step` MUST 接受 `steps_updates` 字典参数（key=step_name, value=updates dict），并在一次调用中批量更新多个 step。系统 SHALL 只加载和写盘一次 pipeline.yaml 文件。

#### Scenario: 批量更新多个 step
- **WHEN** Agent 调用 `pipeline_update_step(pipeline_name="bili", steps_updates={"step_1": {"browser_ops": [...]}, "step_3": {"description": "新描述"}})`
- **THEN** 系统一次性加载 pipeline.yaml，修改 step_1 的 browser_ops 和 step_3 的描述，验证通过后写盘
- **AND** 返回 `{"ok": True, "result": "已在 pipeline 'bili' 中批量更新 2 个步骤: step_1, step_3"}`

#### Scenario: 批量更新中某 step 失败
- **WHEN** Agent 调用包含无效 step_name 的 steps_updates（如 `{"step_invalid": {"description": "test"}}`）
- **THEN** 系统 MUST 收集该 step 的错误，返回 `{"ok": False, "error": "[step_invalid] step not found"}`
- **AND** 已成功更新的其他 step 变更也不写盘（内存操作回滚）

#### Scenario: 批量更新中部分 step 有效、部分无效
- **WHEN** Agent 调用 `steps_updates={"step_1": {"description": "有效"}, "step_ghost": {"description": "不存在"}}`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "[step_ghost] step not found"}`
- **AND** step_1 的有效变更也不写盘（all-or-nothing 语义，内存操作不持久化）

#### Scenario: steps_updates 为空时返回错误
- **WHEN** Agent 调用 `pipeline_update_step(pipeline_name="bili", steps_updates={})`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "必须提供 steps_updates（或 step_name + updates）"}`
- **AND** 不修改 pipeline 文件

#### Scenario: 两个参数都不传时返回错误
- **WHEN** Agent 调用 `pipeline_update_step(pipeline_name="bili")`，不传 `steps_updates`、`step_name`、`updates`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "必须提供 steps_updates（或 step_name + updates）"}`
- **AND** 不修改 pipeline 文件

## MODIFIED Requirements

### Requirement: pipeline_update_step 兼容旧调用方式（step_name + updates）
`pipeline_update_step` MUST 继续支持旧的调用方式：传中 `step_name` (string) 和 `updates` (dict) 时，系统 SHALL 将其视为单步更新，行为与旧版本一致。

#### Scenario: 旧接口调用仍正常工作
- **WHEN** Agent 调用 `pipeline_update_step(pipeline_name="bili", step_name="step_1", updates={"description": "修改"})`
- **THEN** 系统 SHALL 自动将参数转换为 `{"step_1": {"description": "修改"}}` 格式并执行更新
- **AND** 返回结果中包含 "step_1"

#### Scenario: steps_updates 和 step_name 同时存在时优先 steps_updates
- **WHEN** Agent 同时传了 `steps_updates` 和 `step_name`（极少见的错误使用）
- **THEN** 系统 SHALL 优先使用 `steps_updates`，忽略 `step_name` 和 `updates`
