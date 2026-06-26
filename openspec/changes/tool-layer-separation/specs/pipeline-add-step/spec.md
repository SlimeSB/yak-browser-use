## MODIFIED Requirements

### Requirement: pipeline_add_step 合并 record_step 功能
`pipeline_add_step` MUST 支持 `op_type` 和 `op_args` 参数，合并原 `record_step` 的执行后记录能力。原 `record_step` 工具 SHALL 被移除。

原本 `pipeline_add_step` 仅有 `after` 参数用于插入，新增 `op_type`（可选）和 `op_args`（可选）两个参数：
- 当 `op_type` 有值时，行为等价于原 `record_step`：构造 browser_op 并追加/更新到 pipeline
- 当 `op_type` 为空时，创建 outline placeholder step

#### Scenario: 执行后记录 browser op
- **WHEN** Agent 调用 `pipeline_add_step(pipeline_name="xxx", step_name="step_1", description="打开百度", op_type="goto", op_args={"url": "https://baidu.com"})`
- **THEN** 系统 MUST 构造 `browser_ops: [{goto: "https://baidu.com"}]` 并写入 pipeline
- **AND** 系统 MUST 保存 checkpoint 并推送 `pipeline.edit` WebSocket 事件

#### Scenario: 创建 outline placeholder step
- **WHEN** Agent 调用 `pipeline_add_step(pipeline_name="xxx", step_name="step_1", description="待填充")` 不传 `op_type`
- **THEN** 系统 MUST 创建仅有 name 和 description 的 placeholder step
- **AND** 后续再次调用 `pipeline_add_step(pipeline_name="xxx", step_name="step_1", ..., op_type="fill", ...)` 时 MUST 更新同名 step

#### Scenario: 插入到指定步骤后
- **WHEN** Agent 调用 `pipeline_add_step(pipeline_name="xxx", step_name="step_2", ..., after="step_1")`
- **THEN** 新 step MUST 插入到 `step_1` 之后
- **AND** `op_type` 参数与 `after` 参数可同时使用

#### Scenario: 追加到末尾（原有行为保留）
- **WHEN** Agent 调用 `pipeline_add_step` 不传 `after` 参数
- **THEN** 新步骤 MUST 追加到 `steps` 数组末尾

## REMOVED Requirements

### Requirement: 移除 record_step 工具注册
原 `record_step` 工具 SHALL 被移除。**Reason:** 功能已合并入 `pipeline_add_step`。**Migration:** 调用方将 `record_step(pipeline_name, step_name, description, op_type, op_args)` 改为 `pipeline_add_step(pipeline_name, step_name, description, op_type, op_args)`。
