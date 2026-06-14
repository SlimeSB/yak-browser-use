## ADDED Requirements

### Requirement: _PH- 分支纯门禁检查
`runner_preset.py` 中 `_execute_tool_step_with_guardian` 函数的 `_PH-` 分支 MUST 只做门禁检查——验证工具文件是否存在，不编排任何代码生成或生命周期流程。

#### Scenario: 工具文件已存在
- **WHEN** 执行一个 `_PH-` 前缀的 step
- **AND** 对应的 `tools_dir/_PH-xxx.py` 文件已存在
- **THEN** MUST 直接调用 `ToolRunner.load_and_call()` 执行工具
- **AND** MUST NOT 调用任何代码生成方法

#### Scenario: 工具文件不存在
- **WHEN** 执行一个 `_PH-` 前缀的 step
- **AND** 对应的 `tools_dir/_PH-xxx.py` 文件不存在
- **THEN** MUST 返回 `{"status": "failed", "error": {"code": "TOOL_NOT_GENERATED", "message": "..."}}`
- **AND** 错误消息 MUST 提示 agent 需通过 `ph-tool-generation` skill 先生成代码

#### Scenario: 非 _PH- 前缀的步骤不受影响
- **WHEN** 执行一个不以 `_PH-` 开头的普通工具步骤
- **THEN** 流程 MUST 保持原有逻辑不变

### Requirement: 移除 _default_llm_call_fn
`runner_preset.py` MUST NOT 包含 `_default_llm_call_fn()` 函数。LLM 调用能力已由 Hermes agent 层提供，runner_preset 不再需要。

#### Scenario: _default_llm_call_fn 不存在
- **WHEN** 在 `engine/runner_preset.py` 中搜索 `_default_llm_call_fn`
- **THEN** MUST NOT 找到任何定义

### Requirement: 移除 _PH_PREFIX 常量
`runner_preset.py` MUST NOT 包含 `_PH_PREFIX` 常量。前缀检查逻辑内联到门禁分支中。

#### Scenario: _PH_PREFIX 不存在
- **WHEN** 在 `engine/runner_preset.py` 中搜索 `_PH_PREFIX`
- **THEN** MUST NOT 找到任何定义

### Requirement: 移除 llm_call_fn 参数
`run_pipeline()` 函数签名 MUST NOT 包含 `llm_call_fn` 参数。所有调用 `run_pipeline(llm_call_fn=...)` 的地方 MUST 移除该参数。

#### Scenario: run_pipeline 签名不含 llm_call_fn
- **WHEN** 检查 `run_pipeline()` 的函数签名
- **THEN** MUST NOT 包含名为 `llm_call_fn` 的参数

#### Scenario: 所有调用点已清理
- **WHEN** 在项目所有 `.py` 文件中搜索 `llm_call_fn`
- **THEN** MUST NOT 找到任何引用（除注释和文档外）

## REMOVED Requirements

### Requirement: 移除 _PH- 分支的编排逻辑
`_execute_tool_step_with_guardian` 的 `_PH-` 分支 MUST NOT 包含任何代码生成编排逻辑（如调用 `run_ph_lifecycle`、循环重试生成等）。

**Reason**: 编排逻辑已迁移到 Hermes skill `ph-tool-generation`，runner_preset 只需做门禁检查。

**Migration**: 原来依赖 runner_preset 编排 _PH- 工具生命周期的调用方，应改为先通过 `ph-tool-generation` skill 生成代码，再调用 `run_pipeline`。

#### Scenario: 门禁分支不编排流程
- **WHEN** 检查 `_execute_tool_step_with_guardian` 中 `_PH-` 分支的代码
- **THEN** MUST NOT 包含对 `run_ph_lifecycle` 的调用
- **AND** MUST NOT 包含代码生成相关的循环或重试逻辑
