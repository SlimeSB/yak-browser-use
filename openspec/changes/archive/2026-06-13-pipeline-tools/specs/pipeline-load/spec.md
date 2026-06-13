## ADDED Requirements

### Requirement: 读取 pipeline 摘要
系统 MUST 提供 `pipeline_load` 工具，读取指定 pipeline 的结构化摘要，不返回完整 YAML 内容。`browser_op_count` 为 `browser_ops` 数组的长度（0 表示无 browser 操作）。

#### Scenario: 读取存在的 pipeline
- **WHEN** Agent 调用 `pipeline_load` 并传入有效的 `pipeline_name`
- **THEN** 返回 JSON 包含 `ok: true`、`name`、`description`、`step_count`、`required_params`、`steps` 数组
- **AND** 每个 step 包含 `name`、`type`（browser/tool/goal）、`description`、`depends_on`、`tool_name`（可选）、`browser_op_count`（可选）

#### Scenario: 验证 required_params 字段
- **WHEN** pipeline 定义了 `required_params: [keyword, category]`
- **THEN** `pipeline_load` 返回的 JSON 中 `required_params` 为 `["keyword", "category"]`

#### Scenario: 读取不存在的 pipeline
- **WHEN** Agent 调用 `pipeline_load` 并传入不存在的 `pipeline_name`
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: pipeline_name 参数为空
- **WHEN** Agent 调用 `pipeline_load` 但 `pipeline_name` 为空字符串
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

#### Scenario: pipeline 文件格式损坏
- **WHEN** pipeline 文件存在但 YAML 解析或 Pydantic 验证失败
- **THEN** 返回 JSON 包含 `ok: false` 和具体错误信息
