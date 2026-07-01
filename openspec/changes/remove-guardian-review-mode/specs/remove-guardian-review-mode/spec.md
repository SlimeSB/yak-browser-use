## ADDED Requirements

无新增需求。

## MODIFIED Requirements

无既有需求变更。

## REMOVED Requirements

### Requirement: 审查模式设置
系统 SHOULD 在设置页提供审查模式三选一（human/llm/none）。
- **Reason**: 该功能从未真正工作——human 和 llm 后端行为一致，审批端点返回 501 Not Implemented，且对安全模型无实际贡献。
- **Migration**: 移除设置 UI 和相关 store 逻辑。用户无需迁移，默认行为等同于之前的 `none`。

### Requirement: Guardian 审批门控
系统 MUST 在 pipeline 执行时通过 Guardian 检查 step 是否需要人工审批，并在需要时暂停执行等待审批。
- **Reason**: Guardian 类及相关辅助函数均为死代码——`record_failure`、`validate_output`、`llm_review_extra_ops`、`step_guard`、`split_by_guard_result` 均无调用者；审批端点返回 501。
- **Migration**: 删除整个 `guardian.py` 文件，移除 `runner_preset.py` 和 `routes.py` 中的相关调用。pipeline 执行不再有审批门控。

### Requirement: 审批 API 端点
系统 MUST 提供 `POST /api/pipeline/{thread_id}/review` 端点用于审批/拒绝待处理的 pipeline 操作。
- **Reason**: 端点返回 501 Not Implemented，从未真正实现。
- **Migration**: 删除该端点。前端不再调用审批接口。

### Requirement: 前端审批卡片
系统 SHOULD 在 LogTab 和 ExecTab 中展示 pendingReview 审批卡片，允许用户批准或拒绝。
- **Reason**: 审批卡片调用的后端端点返回 501，审批流程从未走通。
- **Migration**: 移除审批卡片 UI。保留 `pipelineStore` 中的 `pendingReview` 字段以防后端仍返回相关数据。
