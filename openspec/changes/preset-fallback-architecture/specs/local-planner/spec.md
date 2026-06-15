## ADDED Requirements

### Requirement: 操作失败后本地规划替代操作

当 browser op 执行失败且重试耗尽后，系统 MUST 通过单次 LLM 调用生成替代 browser_ops，不切换执行引擎。

#### Scenario: 点击选择器不存在时生成替代操作

- **WHEN** 某个 browser step 的 click 操作因选择器不存在而失败，且重试耗尽
- **THEN** 系统 MUST 调用 RuntimePlanner.plan_replacement_ops()，传入失败操作详情、步骤目标描述、错误信息和当前页面的简化 HTML
- **AND** LLM 返回的替代 browser_ops 数量由 LLM 自行决定，系统不限制
- **AND** 系统 MUST 使用 machine.replace_remaining() 替换当前步骤的 ops
- **AND** 系统 MUST 继续执行当前步骤（重新进入主循环）

#### Scenario: 本地规划也失败时进入终端故障

- **WHEN** RuntimePlanner.plan_replacement_ops() 返回 None 或抛出异常
- **THEN** 系统 MUST 记录错误日志并进入终端故障（terminal failure）
- **AND** 系统 MUST 设置 pipeline 状态为 "failed"

#### Scenario: 本地规划生成的操作再次失败

- **WHEN** 替代 ops 执行后再次失败
- **THEN** 系统 MUST 重新走失败路径（retry → Local Planner），不进入 Agent Swimlane
- **AND** 如果 Local Planner 连续失败超过 3 次，系统 MUST 进入终端故障
