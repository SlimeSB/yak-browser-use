## ADDED Requirements

### Requirement: pipeline_finish 工具作为 Agent Swimlane 退出信号

系统 MUST 提供 pipeline_finish 工具，让 agent 在 swimlane 模式下主动结束 pipeline 执行。

#### Scenario: Agent 调用 pipeline_finish 完成 pipeline

- **WHEN** agent 调用 pipeline_finish(status="completed", summary="...") 工具
- **THEN** 系统 MUST 调用 budget.exhaust() 使 IterationBudget 立即耗尽
- **AND** conversation_loop 的 check_exit_conditions() MUST 检测到 budget.is_exhausted 为 True
- **AND** conversation_loop MUST 正常退出 while 循环
- **AND** 工具执行结果 MUST 包含 {"ok": true, "status": "completed", "summary": "..."}

#### Scenario: Agent 调用 pipeline_finish 报告失败

- **WHEN** agent 调用 pipeline_finish(status="failed", summary="...") 工具
- **THEN** 系统 MUST 调用 budget.exhaust() 使 IterationBudget 立即耗尽
- **AND** 工具执行结果 MUST 包含 {"ok": true, "status": "failed", "summary": "..."}

#### Scenario: pipeline_finish 工具在所有模式下可见

- **WHEN** 系统构建工具列表（get_all_tools()）
- **THEN** pipeline_finish 工具 MUST 包含在 PIPELINE_TOOLS 中
- **AND** 工具定义 MUST 包含 status 参数（"completed" | "failed"）和 summary 参数
