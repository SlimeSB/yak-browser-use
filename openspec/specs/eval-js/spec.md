## ADDED Requirements

### Requirement: browser_eval_js 工具注册

系统 MUST 在 `tools/registry.py` 中注册名为 `browser_eval_js` 的工具（非 `eval_js`），通过独立 handler 执行（不在 `_BROWSER_OPS` 循环中）。

#### Scenario: browser_eval_js 出现在工具列表中
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中包含 `browser_eval_js`

### Requirement: browser_eval_js 通过 registry 执行

`browser_eval_js` MUST 通过 `registry.dispatch()` 执行。handler 从 `ctx.cdp_helpers` 获取 bridge，优先读取 `script_file` 参数指定的文件内容作为 JS 代码，通过 `bridge.evaluate()` 执行。

#### Scenario: 使用 script_file 执行 JS
- **WHEN** Agent 调用 `browser_eval_js(script_file="tools/extract.js")`
- **THEN** handler 通过 `validate_path` 校验路径后读取文件内容
- **AND** 调用 `bridge.evaluate(code)` 执行
- **AND** 返回执行结果

#### Scenario: script_file 不存在时返回错误
- **WHEN** Agent 调用 `browser_eval_js(script_file="scripts/nonexistent.js")`
- **THEN** 返回 `{"ok": False, "error": "脚本文件不存在: scripts/nonexistent.js"}`

#### Scenario: script_file 路径越界时返回错误
- **WHEN** Agent 调用 `browser_eval_js(script_file="../../../etc/passwd")`
- **THEN** 系统通过 `validate_path` 拒绝并返回越界错误

### Requirement: browser_eval_js 结果走数据流

`browser_eval_js` 的执行结果 MUST 支持 `output_to` 参数写入 shared_store，与 `file_read` 等工具一致。

#### Scenario: output_to 写入 shared_store
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", output_to="my_data")`
- **THEN** `ctx.shared_store["my_data"]` 被设为 evaluate 执行结果
- **AND** 返回给 LLM 的 result MUST 与不加 `output_to` 时保持一致

#### Scenario: Agent 不提供 output_to 参数
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js")` 且不提供 `output_to`
- **THEN** 系统 MUST 不修改 `ctx.shared_store`，行为与变更前完全相同

### Requirement: browser_eval_js 支持 return_format 参数

`return_format` 参数 MUST 接受三个可选值：`raw`（默认）、`json`、`csv`。

#### Scenario: return_format=csv 时将数组转为 CSV 文本
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", return_format="csv")` 且结果为数组
- **THEN** 返回的 result MUST 是 CSV 格式的文本

#### Scenario: return_format=json 时将结果转为 JSON 文本
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", return_format="json")`
- **THEN** 返回的 result MUST 是 `json.dumps(result, ensure_ascii=False)` 后的文本

#### Scenario: return_format=raw 时保持原样返回
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", return_format="raw")`
- **THEN** 返回的 result MUST 等于 `bridge.evaluate()` 的原始返回值

#### Scenario: return_format=csv 但结果不是数组
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", return_format="csv")` 但结果为字符串
- **THEN** MUST 返回 `"return_format=csv requires array result, got str"`

### Requirement: browser_eval_js tool description 更新

`browser_eval_js` 的 tool description MUST 包含以下提示信息：脚本在 `() => { ... }` 中执行，顶层不要写 `return`；如需多行逻辑使用箭头函数；必须提供 `script_file` 参数从 workspace 加载 JS 文件。
