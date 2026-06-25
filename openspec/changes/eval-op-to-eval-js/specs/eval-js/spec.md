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
