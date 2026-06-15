## MODIFIED Requirements

### Requirement: 程序化执行失败路径

当 pipeline 步骤执行失败时，系统 MUST 按三层递进式 fallback 架构处理，而非直接终端故障。

#### Scenario: Op 执行失败走 Tier 1 + Tier 2 恢复

- **WHEN** browser op 执行返回 BROWSER_ERROR、TIMEOUT_ERROR 或 RUNTIME_ERROR
- **THEN** 系统 MUST 先尝试重试（Tier 1，已有逻辑）
- **AND** 重试耗尽后 MUST 调用 RuntimePlanner 生成替代 ops（Tier 2）
- **AND** 替代 ops 替换后 MUST 重新执行当前步骤

#### Scenario: Check 验证失败走 Tier 3 恢复

- **WHEN** check 验证返回 CHECK_FAILED
- **THEN** 系统 MUST 跳过重试（CHECK_FAILED 不在 RETRYABLE_ERRORS）
- **AND** 系统 MUST 启动 Agent Swimlane（Tier 3）
- **AND** agent 接管后 MUST 自主完成剩余 pipeline 步骤

#### Scenario: 所有恢复路径耗尽后终端故障

- **WHEN** Tier 2 Local Planner 也失败，或 Tier 3 Agent Swimlane 无法完成
- **THEN** 系统 MUST 设置 pipeline 状态为 "failed"
- **AND** 系统 MUST 记录完整的错误链（原始错误 + 恢复失败原因）
- **AND** 系统 MUST 执行正常的 finalise 流程
