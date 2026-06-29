## ADDED Requirements

### Requirement: pipeline_view 合并 load 和 list
系统 MUST 提供 `pipeline_view` 工具，合并原有 `pipeline_load` 和 `pipeline_list` 的功能。无 `name` 参数时返回列表，有 `name` 参数时返回详情。

#### Scenario: 无参数列出所有 pipeline
- **WHEN** Agent 调用 `pipeline_view()`
- **THEN** 返回 JSON 包含 `ok: true` 和所有 pipeline 的名称及描述列表

#### Scenario: 指定名称返回详情
- **WHEN** Agent 调用 `pipeline_view(name="my-pipeline")`
- **THEN** 返回 JSON 包含 `ok: true`、`name`、`description`、`step_count`、`required_params`、`steps` 数组
- **AND** 每个 step MUST 包含完整的 `browser_ops` 列表（非仅计数）

#### Scenario: pipeline 不存在
- **WHEN** Agent 调用 `pipeline_view(name="nonexistent")`
- **THEN** 返回 JSON 包含 `ok: false` 和 `error` 消息

### Requirement: 移除 pipeline_load 和 pipeline_list 注册
系统 MUST 从 registry 中移除 `pipeline_load` 和 `pipeline_list` 的工具注册。

#### Scenario: get_all_tools 不包含旧工具名
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中 MUST NOT 包含 `pipeline_load`
- **AND** MUST NOT 包含 `pipeline_list`
- **AND** MUST 包含 `pipeline_view`
