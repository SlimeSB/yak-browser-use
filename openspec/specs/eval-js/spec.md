## ADDED Requirements

### Requirement: eval_js 工具注册
系统 MUST 在 `tools/registry.py` 中注册名为 `eval_js` 的工具，替代原有的 `browser_eval` op。

#### Scenario: eval_js 出现在工具列表中
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中包含 `eval_js` 而非 `browser_eval`

#### Scenario: eval_js 参数结构
- **WHEN** LLM 查看 `eval_js` 的 tool schema
- **THEN** schema 包含唯一必填参数 `code`（string，要执行的 JavaScript 代码）
- **AND** 不包含 `js_file`、`params`、`poll_seconds`、`output_file`、`silent`、`timeout` 等参数

### Requirement: eval_js 通过 registry 执行
`eval_js` MUST 通过 `registry.dispatch()` 执行，handler 通过 `ctx.cdp_helpers` 获取 bridge 调用 `evaluate()`。

#### Scenario: 执行内联 JS
- **WHEN** LLM 调用 `eval_js(code="document.title")`
- **THEN** 系统通过 ctx.cdp_helpers 执行 `bridge.evaluate("document.title")`
- **AND** 返回当前页面 title 字符串
- **AND** 结果通过 `source_key` 写入 shared_store，可被 `{path}` 引用

### Requirement: eval_js 结果走数据流
`eval_js` 的执行结果 MUST 支持 `source_key` 参数写入 shared_store，与 `file_read`/`captcha` 一致。

#### Scenario: source_key 写入 shared_store
- **WHEN** LLM 调用 `eval_js(code="JSON.stringify({a:1})", source_key="my_data")`
- **THEN** `shared_store["my_data"]` 被设为 eval 执行结果
- **AND** 后续 tool 可通过 `{my_data}` 引用该结果

---

## ADDED Requirements (data-pipeline-bind-variables)

### Requirement: browser_eval_js SHALL 支持 output_to 参数将执行结果存入 shared_store

当 Agent 调用 `browser_eval_js` 并提供 `output_to` 参数时，系统 MUST 在 JS 执行完成后将结果存入 `ctx.shared_store[output_to]` 变量中。

#### Scenario: Agent 将 eval_js 结果存入变量供后续使用

- **WHEN** Agent 调用 `browser_eval_js(code="document.querySelectorAll('a').length", output_to="link_count")`
- **THEN** 执行完成后 `ctx.shared_store["link_count"]` MUST 等于 `bridge.evaluate()` 的返回值
- **AND** 返回给 LLM 的 result MUST 与不加 `output_to` 时保持一致（不改变现有返回格式）

#### Scenario: Agent 不提供 output_to 参数

- **WHEN** Agent 调用 `browser_eval_js(code="1+1")` 且不提供 `output_to`
- **THEN** 系统 MUST 不修改 `ctx.shared_store`，行为与变更前完全相同

---

### Requirement: browser_eval_js SHALL 支持 return_format 参数控制返回格式

`return_format` 参数 MUST 接受三个可选值：`raw`（默认）、`json`、`csv`。

#### Scenario: return_format=csv 时将数组转为 CSV 文本

- **WHEN** Agent 调用 `browser_eval_js(code="[{'a':1},{'a':2}]", return_format="csv")`
- **THEN** 返回的 result MUST 是 CSV 格式的文本（第一行为表头 `a`，第二行为 `1`，第三行为 `2`）
- **AND** CSV MUST 正确处理特殊字符（逗号、引号、换行）的转义

#### Scenario: return_format=json 时将结果转为 JSON 文本

- **WHEN** Agent 调用 `browser_eval_js(code="1+1", return_format="json")`
- **THEN** 返回的 result MUST 是 `"2"`（JSON.stringify 后的文本）

#### Scenario: return_format=raw 时保持原样返回

- **WHEN** Agent 调用 `browser_eval_js(code="1+1", return_format="raw")`
- **THEN** 返回的 result MUST 等于 `bridge.evaluate()` 的原始返回值（数字 2）

#### Scenario: return_format=csv 但结果不是数组

- **WHEN** Agent 调用 `browser_eval_js(code="'hello'", return_format="csv")`
- **THEN** MUST 返回错误提示 `"return_format=csv requires array result, got str"` 或降级为 raw 格式
