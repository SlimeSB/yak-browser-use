## Why

Agent 在使用 `browser_eval_js` 提取页面数据时，需要写几十行 JavaScript 代码，全部塞在 `code` 参数里。由于 LLM 调用的参数是 JSON 字符串，多行代码需要各种转义（`\n`、`\"` 等），极其痛苦且容易出错。

本次变更新增 `script_file` 参数，允许 Agent 先写 JS 文件到 workspace，再通过文件路径调用，大幅改善代码量大时的编写体验。同时增强 tool description，减少 LLM 因 `return` 语句导致的 `Illegal return statement` 错误。

## What Changes

- `browser_eval_js` 新增可选参数 `script_file`：接受 workspace 相对路径，读取文件内容作为 JS 代码执行
- 当 `script_file` 有值时，忽略 `code` 参数
- 更新 `browser_eval_js` 的 tool description，增加 "顶层不要写 return" 的提示，以及 `script_file` 的用法说明
- 路径安全复用现有 `validate_path`，不允许越界读取

## Capabilities

### New Capabilities

- `browser-eval-js-script-file`: 允许通过 workspace 文件路径加载 JS 脚本到 browser_eval_js 执行

### Modified Capabilities

- `browser-eval-js`: tool description 更新，新增 `script_file` 参数

## Impact

- 文件：`backend/src/yak_browser_use/tools/registry.py`
- `browser_eval_js` 的 schema 和 handler 逻辑变更
- 新增路径读取逻辑，依赖 `validate_path` 安全校验
- 向后兼容：`code` 参数仍可用，`script_file` 为可选新增
