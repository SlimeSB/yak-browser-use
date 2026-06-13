## ADDED Requirements

### Requirement: 追加或插入步骤
系统 MUST 提供 `pipeline_add_step` 工具，允许 Agent 在 pipeline 中追加新步骤或在指定步骤后插入。

#### Scenario: 追加到末尾
- **WHEN** Agent 调用 `pipeline_add_step` 不传 `after` 参数
- **THEN** 新步骤被追加到 `steps` 数组末尾
- **AND** 修改后的 pipeline 通过 Pydantic 验证后写入文件
- **AND** 通过 WebSocket 推送 `pipeline.edit` 事件

#### Scenario: 在指定步骤后插入
- **WHEN** Agent 调用 `pipeline_add_step` 并传入 `after` 参数指向存在的步骤名
- **THEN** 新步骤被插入到该步骤之后

#### Scenario: 锚点步骤不存在
- **WHEN** Agent 调用 `pipeline_add_step` 但 `after` 指向的步骤不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 目标 pipeline 不存在
- **WHEN** Agent 调用 `pipeline_add_step` 但 `pipeline_name` 对应的文件不存在
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 新增带依赖的步骤
- **WHEN** Agent 调用 `pipeline_add_step` 且新步骤包含 `depends_on` 数组
- **THEN** 新步骤的 `depends_on` 被写入，不做引用存在性校验

#### Scenario: 新增步骤类型互斥
- **WHEN** 新步骤同时包含 `browser_ops` 和 `tool_name`
- **THEN** Pydantic 验证失败，返回错误
