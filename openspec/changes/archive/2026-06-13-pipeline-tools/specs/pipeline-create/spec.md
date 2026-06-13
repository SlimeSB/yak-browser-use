## ADDED Requirements

### Requirement: 创建新 pipeline 预设
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
- **WHEN** Agent 调用 `pipeline_create` 但 `pipeline_name` 为空字符串或含路径分隔符（`/`、`\`）
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: 步骤列表为空
- **WHEN** Agent 调用 `pipeline_create` 但 `steps` 为空数组
- **THEN** Pydantic 验证失败（`min_length=1`），返回错误

#### Scenario: 步骤类型互斥
- **WHEN** 某步骤同时包含 `browser_ops` 和 `tool_name`
- **THEN** Pydantic 验证失败，返回错误
