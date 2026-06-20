## Why

`toolgen-test` 分支探索的 tool gen 路线（`_PH-` 动态代码生成 + AST 安全检查 + 文件系统写入）经实践验证是过度设计。核心发现：`ctx.eval(js)` 覆盖了绝大多数浏览器交互场景，复杂场景通过渐进式调试即可解决，Python 生态能力通过预设 tool 补齐，不需要运行时动态生成 Python 代码。

当前 `main` 分支上 tool gen 代码生成逻辑尚未合入，但保留了 `_PH-` 工具的执行路径（`runner_preset.py` 中 `_execute_tool_step_with_guardian` 的 `_PH-` 分支、`tool_runner.py` 中的 `rename_ph_file` 等）。这些残留代码与 eval 路线方向不一致，需要清理。

本次变更将架构从 tool gen 路线切换到 eval 路线：引入精简版 ToolContext（浏览器操作 SDK）、eval agent（subagent 处理复杂 DOM/验证码）、file_read/file_write（纯文本文件读写）、format_convert（any-to-any 格式转换），同时清理 main 分支上残留的 `_PH-` 执行路径。

## What Changes

- **新增** `backend/engine/ops.py`：从 toolgen-test 合入 ToolContext + build_tool_kwargs，精简为纯浏览器操作 SDK（砍掉 data ops、cdp escape hatch、DANGEROUS_MODULES）
- **新增** `backend/tests/test_ops.py`：ToolContext 的 browser/safety 测试
- **新增** `backend/engine/eval_agent.py`：eval agent subagent 实现，支持 prompt 模板注入、JS 函数库注入、迭代试错循环
- **新增** `backend/prompts/eval_agent/system.md`：eval agent 默认 system prompt 模板
- **新增** `backend/prompts/eval_agent/js_lib.js`：内置 JS 原子函数库（isVisible、retryUntil、waitForElement 等）
- **新增** `backend/tools/format_convert.py`：any-to-any 格式转换统一入口（xlsx/csv/json），复用现有 `tools/adapters.py`
- **新增** `backend/tools/file_read.py` + `backend/tools/file_write.py`：纯文本文件读写预设 tool
- **修改** `backend/engine/runner_preset.py`：删除 `_execute_tool_step_with_guardian` 中的 `_PH-` 分支（~40 行），保留常规 tool 执行路径
- **修改** `backend/engine/_lifecycle/tool_runner.py`：删除 `_PH_PREFIX`、`is_ph_tool`、`strip_ph_prefix`、`rename_ph_file`、`update_pipeline_refs`、`_replace_ph_refs`（~80 行），保留 `load_and_call`
- **修改** planner prompt：添加 eval agent 启动条件指导（主 LLM 自行判断何时进入 eval agent）
- **不合并** toolgen-test 分支的 tool gen 代码（`_inline_generate_and_execute`、`prompts/tool_gen/`、`test_ph_generation.py`、`test_ops_safety.py` 等），全部留在分支

## Capabilities

### New Capabilities

- `tool-context`: 精简版 ToolContext（ops.py），提供 ctx.eval / ctx.type / ctx.click / ctx.snapshot / ctx.wait / ctx.screenshot / ctx.source 七个浏览器操作方法，以及 domain whitelist + circuit breaker 安全机制
- `eval-agent`: eval agent subagent，接收 purpose + snapshot + 失败反馈，通过迭代 eval 试错完成复杂 DOM 操作或验证码识别，返回数据摘要
- `file-io`: file_read / file_write 预设 tool，纯文本文件读写，不做格式解析
- `format-convert`: format_convert 预设 tool，xlsx/csv/json 之间的 any-to-any 格式转换统一入口

### Modified Capabilities

- `tool-runner`: 删除 `_PH-` 工具专属方法（is_ph_tool、strip_ph_prefix、rename_ph_file、update_pipeline_refs），保留 load_and_call 常规工具执行
- `runner-preset`: 删除 `_execute_tool_step_with_guardian` 中的 `_PH-` 工具执行分支

## Impact

- **代码**：新增 ~5 个文件（ops.py、eval_agent.py、format_convert.py、file_read.py、file_write.py），修改 2 个文件（runner_preset.py、tool_runner.py），新增 3 个 prompt/JS 资源文件
- **依赖**：format_convert 引入 openpyxl（xlsx 读写），ToolContext 依赖现有 PlaywrightBridge
- **接口**：ToolContext 方法名 `eval` / `type` 与 Python 内置函数同名（有意的设计选择），不影响外部 API
- **测试**：新增 test_ops.py（browser/safety 测试），eval agent 和 format_convert 的测试在实现时补充
- **分支**：toolgen-test 分支保留不动，不合入 main
