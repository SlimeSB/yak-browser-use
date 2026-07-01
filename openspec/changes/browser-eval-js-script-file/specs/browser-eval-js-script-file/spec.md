## ADDED Requirements

### Requirement: browser_eval_js 支持 script_file 参数
`browser_eval_js` MUST 接受可选的 `script_file` 参数。当该参数有值时，系统 SHALL 从 workspace 读取对应文件内容，作为 JavaScript 代码传递给 `bridge.evaluate()`，并忽略 `code` 参数。

#### Scenario: 使用 script_file 执行 JS 脚本
- **WHEN** Agent 调用 `browser_eval_js(script_file="scripts/extract.js")`
- **THEN** 系统读取 workspace 下 `scripts/extract.js` 文件内容，并将内容作为 JS 代码执行
- **AND** 返回执行结果（行为与传 `code` 参数一致）

#### Scenario: script_file 不存在时返回错误
- **WHEN** Agent 调用 `browser_eval_js(script_file="scripts/nonexistent.js")` 且文件不存在
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "脚本文件不存在: scripts/nonexistent.js"}`
- **AND** 不执行任何代码

#### Scenario: script_file 路径越界时返回错误
- **WHEN** Agent 调用 `browser_eval_js(script_file="../../../etc/passwd")`
- **THEN** 系统 MUST 通过 `validate_path` 拒绝并返回越界错误
- **AND** 不读取任何文件

#### Scenario: code 和 script_file 同时传值
- **WHEN** Agent 同时传了 `code` 和 `script_file`
- **THEN** 系统 SHALL 优先使用 `script_file`，忽略 `code` 参数

#### Scenario: 两个参数都不传时返回错误
- **WHEN** Agent 调用 `browser_eval_js()` 且 `code` 为空、`script_file` 为空
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "必须提供 code 或 script_file 参数"}`

## MODIFIED Requirements

### Requirement: browser_eval_js tool description 更新
`browser_eval_js` 的 tool description MUST 包含以下提示信息：脚本在 `() => { ... }` 中执行，顶层不要写 `return`；如需多行逻辑使用箭头函数；支持 `script_file` 从 workspace 加载 JS 文件。

#### Scenario: LLM schema 调用时能看到提示
- **WHEN** LLM 请求获取可用工具列表
- **THEN** 返回的 `browser_eval_js` tool schema description 中包含 `⚠️` 提示和 `script_file` 说明
