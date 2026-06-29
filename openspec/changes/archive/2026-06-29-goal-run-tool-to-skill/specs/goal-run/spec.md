## ADDED Requirements

### Requirement: goal-run 作为纯 skill
`goal_run` MUST 不再注册为 LLM 可调用 tool，改为仅通过 `goal-execution` SKILL.md（tag:system）提供指引。LLM 无需调用任何 tool 即可获得复杂目标执行的指令。

#### Scenario: goal_run 不在工具列表中
- **WHEN** 系统注册工具列表
- **THEN** `registry.get_schemas()` 返回的工具列表中 MUST NOT 包含 `goal_run`
- **AND** `get_all_tools()` MUST NOT 有 `include_goal_run` 参数

#### Scenario: LLM 无需调用 goal_run 即可获得指引
- **WHEN** LLM 收到用户提出的复杂目标
- **THEN** LLM MUST 直接使用 `todo` + `browser_*` 工具逐步执行
- **AND** 不需要先调用 `goal_run` 来触发模式切换

#### Scenario: goal-execution skill 自动注入
- **WHEN** 系统构建 system prompt
- **THEN** `goal-execution` SKILL.md（tag:system）MUST 被自动注入
- **AND** skill 内容 MUST 包含用 `todo` 拆解任务、逐步执行、记录步骤的指引

## REMOVED Requirements

### Requirement: goal_run 工具行为
**Reason**: `goal_run` tool 已删除，不再有"返回模式切换提示"的行为。LLM 直接通过 `goal-execution` skill 获取指引。

**Migration**: 删除 `_goal_run_handler` 函数。`goal-execution` SKILL.md（tag:system）自动注入逻辑不变。

### Requirement: goal_run 工具注册
**Reason**: `goal_run` tool 始终是 no-op（返回提示文字），与 `goal-execution` skill 内容重复，删除后 LLM 直接走 skill 指令。

**Migration**: 删除 `registry.register("goal_run", ...)` 注册、`_goal_run_handler` 函数、`include_goal_run` 参数、`get_browser_tools()` 函数。`goal-execution` SKILL.md 保持 system tag，自动注入逻辑不变。

### Requirement: goal_run tool schema
**Reason**: tool 已删除，schema 不再需要。

**Migration**: 删除 `GOAL_RUN_TOOL` 常量定义。不影响 pipeline YAML 中 `op_type == "goal_run"` 的逻辑。

### Requirement: goal_run handler
**Reason**: tool 已删除，handler 不再需要。

**Migration**: 删除 `_goal_run_handler` 函数。删除 `tool_executor.py` 中 `if not ok and fn_name == "goal_run"` 分支。

### Requirement: record_step 工具
**Reason**: `record_step.py` 整文件为零生产调用者的死代码，其功能已被 `pipeline_add_step` 合并。

**Migration**: 删除 `backend/src/yak_browser_use/tools/record_step.py` 文件。
