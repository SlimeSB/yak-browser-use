## MODIFIED Requirements

### Requirement: 工具注册列表
`get_all_tools()` 函数 MUST 改为调用 `registry.get_schemas()` 获取工具列表，不再通过手动拼接 `BROWSER_TOOLS`、`GOAL_RUN_TOOL`、`PIPELINE_TOOLS`、`RECORD_STEP_TOOL`、`TODO_TOOL`、`SKILL_*_TOOL`、`FILE_*_TOOL`、`FORMAT_CONVERT_TOOL`、`EVAL_AGENT_TOOL` 等模块级常量来构建。`include_goal_run` 参数 MUST 改为通过 `registry.filter()` 或条件判断实现等价行为。

#### Scenario: 包含 goal_run 时
- **WHEN** 调用 `get_all_tools(include_goal_run=True)`
- **THEN** 返回的工具列表与重构前一致（包含所有已注册工具）
- **AND** 列表中包含 `goal_run` 工具

#### Scenario: 不包含 goal_run 时
- **WHEN** 调用 `get_all_tools(include_goal_run=False)`
- **THEN** 返回的工具列表与重构前一致
- **AND** 列表中不包含 `goal_run`

#### Scenario: 工具列表来源
- **WHEN** 审视 `get_all_tools()` 的实现
- **THEN** 工具列表来自 `registry.get_schemas()` 或 `registry.filter()` 方法
- **AND** 不再存在从 `BROWSER_TOOLS` 等模块级常量直接取值的代码路径

### Requirement: eval_agent 受限制工具
`EvalAgent.get_restricted_tools()` MUST 改为调用 `registry.filter(allowed)` 获取受限工具列表，不再从 `BROWSER_TOOLS` 等常量手动拼接。

#### Scenario: 获取受限制工具
- **WHEN** 调用 `get_restricted_tools()`
- **THEN** 返回与重构前相同的受限制工具列表
- **AND** 实现方式为 `registry.filter(allowed_names)` 而非手动拼接 `BROWSER_TOOLS` 子集
