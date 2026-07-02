## ADDED Requirements

### Requirement: json_field_exists 验收
系统 SHALL 支持 `json_field_exists` check 类型，验证 shared_store 中某 step 数据的指定 JSON 路径是否存在且非 None。

#### Scenario: 字段存在时通过
- **WHEN** check 为 `{json_field_exists: {step: "step_2", field: "ops"}}` 且 shared_store["step_2"]["data"]["ops"] 存在
- **THEN** run_check 返回 `{ok: true}`

#### Scenario: 字段不存在时失败
- **WHEN** check 为 `{json_field_exists: {step: "step_2", field: "ops"}}` 但路径不存在
- **THEN** run_check 返回 `{ok: false, error: "字段不存在: ops"}`

#### Scenario: step 不在 shared_store 中时失败
- **WHEN** check 引用不存在的 step 名
- **THEN** run_check 返回 `{ok: false}`

#### Scenario: 支持嵌套路径
- **WHEN** check 的 field 为 `"a.b.c"` 格式的纯点号分隔路径（dict key 导航，不支持数组索引）
- **THEN** run_check 逐层遍历 dict，全部存在且非 None 才返回 ok

#### Scenario: 缺少 shared_store 参数时报错
- **WHEN** check 包含 json_field_exists 但 shared_store=None
- **THEN** run_check 返回 `{ok: false, error: "json_field_exists 需要 shared_store"}`
