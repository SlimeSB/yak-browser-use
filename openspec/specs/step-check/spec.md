## Error Message Conventions

实现时以下错误消息 MUST 统一使用，不要在子 spec 中各自发明：

| 场景 | error 内容 |
|---|---|
| check 字段缺失（schema 必填校验，Pydantic 层） | `"check 为必填字段"` |
| check 字段为空 dict（schema model_validator） | `"check 不能为空字典，请提供验收条件或 {ignore: true}"` |
| `output_exists` / `file_contains` 缺少 step_dir | `"output_exists/file_contains 需要 step_dir"` |
| `json_field_exists` 缺少 shared_store | `"json_field_exists 需要 shared_store"` |
| `js_expression` 缺少 bridge | `"js_expression 需要浏览器环境(bridge)"` |
| 通用参数非空字符串校验失败 | `"{key} 需要非空字符串值，实际为 {type}"` |
| check 字段含不支持的 key（schema 层） | `"check 字段不支持 key: '{key}'，合法值: {valid_keys}"` |
| 字段路径不存在（json_field_exists） | `"字段不存在: {field}"` |
| 输出文件不存在（output_exists） | `"输出文件不存在: {path}"` |
| 路径越界 | `"路径越界: {path}"` |
| 路径不是文件（file_contains） | `"路径不是文件: {path}"` |

---

## MODIFIED Requirements

### Requirement: run_check 函数签名扩展

`run_check()` 的签名 MUST 从 `run_check(check_def, bridge)` 扩展为 `run_check(check_def, bridge, step_dir=None, shared_store=None)`，以支持不依赖浏览器的文件/数据验收。

#### Scenario: 浏览器类验收调用
- **WHEN** `run_check({"url_contains": "bilibili.com"}, bridge)` 被调用（不传 step_dir/shared_store）
- **THEN** 行为与现有完全一致，通过 bridge 操作

#### Scenario: 文件类验收调用
- **WHEN** `run_check({"output_exists": "out.csv"}, bridge, step_dir=step_dir)` 被调用
- **THEN** 检查 step_dir/out.csv 是否存在，不需要 bridge

#### Scenario: 数据类验收调用
- **WHEN** `run_check({"json_field_exists": {"step": "s2", "field": "ops"}}, bridge, shared_store=shared_store)` 被调用
- **THEN** 检查 shared_store["s2"]["data"]["ops"] 路径

### Requirement: run_check 支持的 check 类型全集

`run_check()` MUST 支持以下所有 check 类型：`url_contains`、`element_exists`、`text_contains`、`element_visible`（原有 4 种），`output_exists`、`file_contains`、`js_expression`、`json_field_exists`、`ignore`（新增 5 种）。

#### Scenario: 原有 4 种 check 行为不变
- **WHEN** check 仅包含 url_contains / element_exists / text_contains / element_visible 之一
- **THEN** 行为与现有完全一致

#### Scenario: output_exists 验证
- **WHEN** check 为 `{output_exists: "downloads/result.csv"}` 且文件存在
- **THEN** 返回 `{ok: true}`
- **AND** 文件不存在时返回 `{ok: false, error: "输出文件不存在: downloads/result.csv"}`
- **AND** step_dir=None 时返回 `{ok: false, error: "output_exists/file_contains 需要 step_dir"}`
- **AND** 路径越界时返回 `{ok: false, error: "路径越界: ..."}`

#### Scenario: file_contains 验证
- **WHEN** check 为 `{file_contains: {path: "result.csv", text: "BV"}}` 且文件内容包含 BV
- **THEN** 返回 `{ok: true}`
- **AND** 文件不包含文本时返回 `{ok: false}`
- **AND** 路径不是文件时返回 `{ok: false, error: "路径不是文件: ..."}`

#### Scenario: js_expression 验证
- **WHEN** check 为 `{js_expression: "return document.title.includes('bilibili')"}` 且 bridge.evaluate 返回 truthy
- **THEN** 返回 `{ok: true}`
- **AND** evaluate 返回 falsy/null/undefined 时返回 `{ok: false}`
- **AND** bridge=None 时返回 `{ok: false, error: "js_expression 需要浏览器环境(bridge)"}`

#### Scenario: json_field_exists 验证
- **WHEN** check 为 `{json_field_exists: {step: "s2", field: "data.ops"}}` 且路径存在
- **THEN** 返回 `{ok: true}`
- **AND** 路径不存在时返回 `{ok: false, error: "字段不存在: ..."}`
- **AND** field 为 `"a.b.c"` 格式纯点号分隔路径时，逐层遍历 dict（dict key 导航，不支持数组索引）
- **AND** shared_store=None 时返回 `{ok: false, error: "json_field_exists 需要 shared_store"}`

#### Scenario: ignore 显式跳过
- **WHEN** check 为 `{ignore: true}`
- **THEN** 立即返回 `{ok: true, result: "ignore: 显式跳过验收"}`，不执行任何验证
- **AND** ignore 在 schema 校验时合法（Pydantic 校验通过）
- **AND** ignore 在运行时不需要 step_dir/shared_store
- **AND** ignore 与其他 key 并存时，`ignore: true` 始终优先——跳过全部检查

### Requirement: 非 string 值的 check key 不被通用校验循环误杀（BUG FIX）

当前代码中 `for key in check_def: if not isinstance(value, str): return "无效参数"` 的通用校验 MUST 被重构，使其不会拒绝 `file_contains`(dict)、`json_field_exists`(dict)、`ignore`(bool) 等非 string 值。

#### Scenario: file_contains 值是 dict 时不被拦截
- **WHEN** check 为 `{file_contains: {path: "x", text: "y"}}`
- **THEN** 通用循环跳过此 key，由 file_contains 专属分支做结构化校验

#### Scenario: ignore 值是 bool 时不被拦截
- **WHEN** check 为 `{ignore: true}`
- **THEN** 不进入通用 string 校验循环

#### Scenario: 原有 string key 仍受非空校验
- **WHEN** check 为 `{url_contains: ""}`（空字符串）
- **THEN** 仍返回"无效参数"错误

### Requirement: check 字段为必填（BREAKING）

`check` MUST 是必填字段——省略（`None`）或空 dict `{}` 均不合法。Pydantic validator 会拒绝这两种情况，系统 MUST 要求每步显式声明验收方式（实际验收 或 `{ignore: true}`）。

#### Scenario: 写入 pipeline 时省略 check
- **WHEN** LLM 写入一个 step 但未提供 `check` 字段
- **THEN** Pydantic ValidationError 报错："check 为必填字段"

#### Scenario: 写入 pipeline 时 check={}
- **WHEN** LLM 尝试写入 `check: {}`
- **THEN** Pydantic ValidationError 报错："check 不能为空字典，请提供验收条件或 {ignore: true}"

#### Scenario: 运行时收到空 check_def（不应发生）
- **WHEN** run_check 收到 `{}`（schema 理论上已拦截，但如有绕过）
- **THEN** 返回 `{ok: false, error: "check 定义不能为空"}`（不兜底，直接报错）

#### Scenario: 运行时收到 None（不应发生）
- **WHEN** run_check 收到 `None`
- **THEN** 返回 `{ok: false, error: "check 定义不能为 None"}`（不兜底，直接报错）

### Requirement: 不支持的 key 在 schema 层被拒绝（BREAKING）

StepYaml MUST 通过 Pydantic model_validator 校验 check 字段的所有 key 是否在全局合法集合内。

#### Scenario: 写入不支持的 key
- **WHEN** LLM 写入 `check: {foo: "bar"}`
- **THEN** Pydantic ValidationError 报错，列出支持的 key

#### Scenario: 写入合法 key
- **WHEN** check 为 `{ignore: true}` 或 `{url_contains: "x"}` 等已知 key
- **THEN** 校验通过

### Requirement: runner_preset 调用 run_check 时传递完整参数

`runner_preset.py` MUST 在调用 `run_check` 时传入 `step_dir` 和 `shared_store`。

#### Scenario: browser step 验收
- **WHEN** browser step 完成后有 check 定义
- **THEN** runner_preset 调用 `run_check(check_def, bridge, step_dir=step_dir, shared_store=shared_store)`

#### Scenario: tool step 验收
- **WHEN** tool step 完成后有 check 定义（如 output_exists）
- **THEN** runner_preset 同样传入 step_dir 和 shared_store
