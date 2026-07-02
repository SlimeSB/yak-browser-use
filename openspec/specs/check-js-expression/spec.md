## ADDED Requirements

### Requirement: js_expression 验收
系统 SHALL 支持 `js_expression` check 类型，在浏览器中执行自定义 JS 表达式，返回 truthy 则通过。

#### Scenario: JS 返回 truthy 时通过
- **WHEN** check 为 `{js_expression: "return document.title.includes('bilibili')"}` 且 evaluate 返回 true
- **THEN** run_check 返回 `{ok: true}`

#### Scenario: JS 返回 falsy 时失败
- **WHEN** check 包含 js_expression 但 evaluate 返回 false / null / undefined
- **THEN** run_check 返回 `{ok: false}`

#### Scenario: 缺少 bridge 时报错
- **WHEN** check 包含 js_expression 但 bridge=None
- **THEN** run_check 返回 `{ok: false, error: "js_expression 需要浏览器环境(bridge)"}`
