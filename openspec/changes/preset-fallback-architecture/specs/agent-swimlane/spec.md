## ADDED Requirements

### Requirement: Check 失败后切换到 Agent 自主执行

当 check 验证失败时，系统 MUST 收集运行时上下文并启动 conversation_loop，让 agent 自主完成剩余 pipeline 步骤。

#### Scenario: Check 失败触发 Agent Swimlane

- **WHEN** 某个步骤的 check 验证返回失败（CHECK_FAILED）
- **THEN** 系统 MUST 跳过 retry（CHECK_FAILED 不在 RETRYABLE_ERRORS 中）
- **AND** 系统 MUST 收集已完成步骤摘要（步骤名称 + 最终 URL）
- **AND** 系统 MUST 从 step_dir/step.json 提取检查点 URL
- **AND** 系统 MUST 获取当前页面简化 HTML 和 URL
- **AND** 系统 MUST 构建包含上述上下文的 user message
- **AND** 系统 MUST 调用 run_preset_loop() 并传入上下文消息和剩余步骤定义

#### Scenario: Agent 通过 pipeline_finish 正常完成

- **WHEN** agent 调用 pipeline_finish(status="completed") 工具
- **THEN** 系统 MUST 正常结束 pipeline 执行
- **AND** 系统 MUST 执行正常的 finalise 流程（写 version snapshot、执行树等）

#### Scenario: Agent 报告无法完成

- **WHEN** agent 调用 pipeline_finish(status="failed") 工具
- **THEN** 系统 MUST 设置 pipeline 状态为 "failed"
- **AND** 系统 MUST 记录 agent 提供的失败摘要

#### Scenario: Agent 执行超预算

- **WHEN** conversation_loop 的 IterationBudget 耗尽
- **THEN** 系统 MUST 设置 pipeline 状态为 "failed"
- **AND** 系统 MUST 记录 "budget exhausted" 错误
