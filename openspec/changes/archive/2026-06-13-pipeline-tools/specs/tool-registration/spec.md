## REMOVED Requirements

### Requirement: 移除 edit_pipeline 工具
`get_all_tools()` 返回的工具列表中 MUST NOT 包含 `edit_pipeline` 工具定义。该工具被 6 个 pipeline 操作工具替代。

#### Scenario: edit_pipeline 不在工具列表中
- **WHEN** 调用 `get_all_tools()`
- **THEN** 返回的工具列表中不包含函数名为 `edit_pipeline` 的工具

## MODIFIED Requirements

### Requirement: 工具注册列表
`get_all_tools()` 函数 MUST 返回包含 6 个 pipeline 操作工具和 1 个 record_step 工具的完整列表，不再包含 `edit_pipeline`。

#### Scenario: 包含 goal_run 时
- **WHEN** 调用 `get_all_tools(include_goal_run=True)`
- **THEN** 返回 15 个工具：7 个 browser_* + 1 个 goal_run + 6 个 pipeline_* + 1 个 record_step
- **AND** 列表中不包含 `edit_pipeline`

#### Scenario: 不包含 goal_run 时
- **WHEN** 调用 `get_all_tools(include_goal_run=False)`
- **THEN** 返回 14 个工具：7 个 browser_* + 6 个 pipeline_* + 1 个 record_step
- **AND** 列表中不包含 `goal_run` 和 `edit_pipeline`
