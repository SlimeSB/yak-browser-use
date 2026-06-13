## ADDED Requirements

### Requirement: 删除步骤并清理依赖
系统 MUST 提供 `pipeline_remove_step` 工具，删除指定步骤并自动清理其他步骤中对该步骤的 `depends_on` 引用。

#### Scenario: 删除存在的步骤
- **WHEN** Agent 调用 `pipeline_remove_step` 并传入存在的 `step_name`
- **THEN** 该步骤从 `steps` 数组中移除
- **AND** 其他步骤的 `depends_on` 中对该步骤名的引用被清理
- **AND** 修改后的 pipeline 通过 Pydantic 验证后写入文件
- **AND** 通过 WebSocket 推送 `pipeline.edit` 事件

#### Scenario: 步骤不存在
- **WHEN** Agent 调用 `pipeline_remove_step` 但 `step_name` 不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 目标 pipeline 不存在
- **WHEN** Agent 调用 `pipeline_remove_step` 但 `pipeline_name` 对应的文件不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 删除后 steps 为空
- **WHEN** 删除 pipeline 中唯一的步骤
- **THEN** Pydantic 验证失败（`min_length=1`），返回错误，文件不被修改
