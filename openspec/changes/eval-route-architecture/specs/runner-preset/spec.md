## REMOVED Requirements

### Requirement: 移除 _PH- 工具执行分支
`runner_preset.py` 的 `_execute_tool_step_with_guardian` 函数 MUST NOT 包含 `if tool_name.startswith("_PH-"):` 分支。

**Reason:** eval 路线不做动态代码生成，`_PH-` 工具的执行路径（ToolRunner 的 rename_ph_file、update_pipeline_refs 等）没有使用场景。

**Migration:** 无。`_PH-` 工具从未在 main 分支上正式可用。

#### Scenario: _PH- 分支已移除
- **WHEN** 检查 `_execute_tool_step_with_guardian` 函数的代码
- **THEN** `if tool_name.startswith("_PH-"):` 代码块 MUST NOT 存在
- **AND** 函数 MUST 直接进入常规 tool 执行路径

## MODIFIED Requirements

### Requirement: _execute_tool_step_with_guardian 常规工具执行
`_execute_tool_step_with_guardian` MUST 直接执行常规工具，不再判断 `_PH-` 前缀。

#### Scenario: 执行常规 tool 步骤
- **WHEN** 调用 `_execute_tool_step_with_guardian(step_def, tools_dir, step_dir, run_dir, ctx, events, pg)`
- **THEN** 系统 MUST 从 step_def 提取 tool_name
- **AND** 系统 MUST 收集 input_files 并验证路径
- **AND** 系统 MUST 调用 `execute_tool_step()` 执行工具
- **AND** 系统 MUST 返回执行结果

#### Scenario: pipeline_path 参数已移除
- **WHEN** 检查 `_execute_tool_step_with_guardian` 的函数签名
- **THEN** `pipeline_path` 参数 MUST NOT 存在（仅被 `_PH-` 分支的 `update_pipeline_refs` 引用）
- **AND** `run_pipeline` 中调用 `_execute_tool_step_with_guardian` 时 MUST NOT 传入 `pipeline_path`

#### Scenario: tool 步骤执行失败
- **WHEN** `execute_tool_step()` 返回失败结果
- **THEN** 系统 MUST 返回包含错误码和错误信息的失败结果
