## MODIFIED Requirements

### Requirement: 工具注册列表
`get_all_tools()` 函数 MUST 调用 `registry.get_schemas()` 获取工具列表，不再通过手动拼接 `BROWSER_TOOLS`、`PIPELINE_TOOLS`、`RECORD_STEP_TOOL`、`TODO_TOOL`、`SKILL_*_TOOL`、`FILE_*_TOOL`、`FORMAT_CONVERT_TOOL`、`EVAL_AGENT_TOOL` 等模块级常量来构建。

#### Scenario: 获取全部工具
- **WHEN** 调用 `get_all_tools()`
- **THEN** 返回的工具列表来自 `registry.get_schemas()`
- **AND** 不再存在从 `BROWSER_TOOLS` 等模块级常量直接取值的代码路径
- **AND** 函数签名 MUST NOT 包含 `include_goal_run` 参数

### Requirement: eval_agent 受限制工具
`EvalAgent.get_restricted_tools()` MUST 调用 `registry.filter(allowed)` 获取受限工具列表，不再从 `BROWSER_TOOLS` 等常量手动拼接。

#### Scenario: 获取受限制工具
- **WHEN** 调用 `get_restricted_tools()`
- **THEN** 返回与重构前相同的受限制工具列表
- **AND** 实现方式为 `registry.filter(allowed_names)` 而非手动拼接 `BROWSER_TOOLS` 子集

## REMOVED Requirements

### Requirement: include_goal_run 参数
**Reason**: `goal_run` tool 已删除，`include_goal_run` 参数不再需要。

**Migration**: 删除 `get_all_tools(include_goal_run)` 参数，函数直接返回 `registry.get_schemas()` 的全部结果。删除 `get_browser_tools()` 函数（零生产调用者）。
