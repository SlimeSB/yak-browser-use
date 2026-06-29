## ADDED Requirements

### Requirement: pipeline_update_step 深路径 patch
`pipeline_update_step` 的 `updates` 参数 MUST 支持 `"key[n].field"` 格式的深路径 patch，允许修改数组元素的单个字段而不重传整个数组。

#### Scenario: 修改 browser_ops 数组元素的单个字段
- **WHEN** Agent 调用 `pipeline_update_step(updates={"browser_ops[2].text": "新关键字"})`
- **THEN** 目标步骤的第 3 个 browser_op 的 `text` 字段 MUST 被更新为 "新关键字"
- **AND** 该 browser_op 的其他字段（如 `selector`）MUST 保持不变
- **AND** 其他 browser_op 元素 MUST 保持不变

#### Scenario: 深路径与全量替换混用
- **WHEN** Agent 调用 `pipeline_update_step(updates={"description": "新描述", "browser_ops[0].value": "新值"})`
- **THEN** `description` MUST 被全量替换为 "新描述"
- **AND** 第一个 browser_op 的 `value` 字段 MUST 被更新为 "新值"
- **AND** 两个变更 MUST 同时生效

#### Scenario: 索引越界
- **WHEN** Agent 调用 `pipeline_update_step(updates={"browser_ops[10].text": "xxx"})` 但 browser_ops 数组长度不足
- **THEN** PipelineStore MUST 返回错误，文件不被修改

#### Scenario: 非 list 字段使用深路径
- **WHEN** Agent 调用 `pipeline_update_step(updates={"name[0].x": "yyy"})` 但 `name` 不是 list 类型
- **THEN** PipelineStore MUST 返回错误，文件不被修改

### Requirement: PipelineStore update_step 深路径解析
`PipelineStore.update_step` 方法 MUST 解析 `updates` dict 中的 key，判断是否为深路径格式 `"<key>[<n>].<field>"`。

#### Scenario: 识别深路径 key
- **WHEN** `update_step` 收到 key 为 `"browser_ops[3].selector"`
- **THEN** 系统 MUST 解析出：`list_key = "browser_ops"`、`index = 3`、`field = "selector"`
- **AND** 对目标 step 的 `browser_ops[3].selector` 执行字段级更新

#### Scenario: value 为 list 时全量替换
- **WHEN** `update_step` 收到 key 为 `"browser_ops"` 且 value 为 list 类型
- **THEN** 系统 MUST 全量替换目标 step 的 `browser_ops` 列表
