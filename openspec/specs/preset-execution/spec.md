## MODIFIED Requirements

### Requirement: 程序化执行失败恢复

当 pipeline 步骤执行失败时，系统 MUST 按分层恢复策略处理：

1. **Tier 1 — 重试**: browser op 执行返回 BROWSER_ERROR、TIMEOUT_ERROR 或 RUNTIME_ERROR 时，系统 MUST 先按 retry 配置重试
2. **Tier 2 — 终端恢复**: 重试耗尽后，step 标记为不可重试错误时，收集 failure_context 并设 `final_status="needs_recovery"`，交给 `api_run` 的 recovery loop 处理
3. **Tier 3 — Agent 接管**: recovery loop 中创建独立 agent session，发送 recovery prompt，agent 通过 ToolRegistry dispatch 使用 browser_* 工具修复后从 pipeline.yaml 重跑

#### Scenario: Op 执行失败走重试
- **WHEN** browser op 执行返回 BROWSER_ERROR、TIMEOUT_ERROR 或 RUNTIME_ERROR
- **THEN** 系统 MUST 先尝试重试（Tier 1，已有逻辑）
- **AND** 重试耗尽后进入终端恢复路径（整体交给 preset-recovery spec 描述的 recovery loop）

#### Scenario: Check 验证失败跳过重试
- **WHEN** check 验证返回 CHECK_FAILED
- **THEN** 系统 MUST 跳过重试（CHECK_FAILED 不在 RETRYABLE_ERRORS 中）
- **AND** 收集 failure_context，最终由 recovery loop 的 agent 接管

#### Scenario: 所有恢复路径耗尽后终端故障
- **WHEN** recovery loop 中所有 attempt 均失败，或 agent 调用 `pipeline_finish(status="failed")`
- **THEN** 系统 MUST 设置 pipeline 状态为 "failed"
- **AND** 系统 MUST 记录完整的错误链
- **AND** 系统 MUST 执行正常的 finalise 流程
