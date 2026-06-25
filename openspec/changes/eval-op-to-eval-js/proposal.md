## Why

`browser_eval` 当前是 `execute_browser_op()` 中的一个分支，执行 JS 后结果直接塞回 LLM 上下文，无法进入 shared_store / `{path}` 数据流。`file_read` / `captcha` / `file_write` 之间已经打通了数据管道，`browser_eval` 是这个链路上的唯一断层。

同时 `expand_branch` 本质上是 snapshot 的子查询，不应该是独立 op。`get_element_by_number` 名字不准确——它做的是查 selector，且依赖缓存不及时刷新。

三个小重构合并一次做，目标：净减少 4 个 browser ops，打通 eval 数据流，消除架构上的孤立点。

## What Changes

- **新增** `eval_js` tool 在 `tools/registry.py` 中注册，handler 通过 `ctx.cdp_helpers` 执行 JS，结果自然走 shared_store / `{path}` 引用
- **删除** `browser_eval` from `_BROWSER_OPS`、`execute_browser_op()` 分支、`execute_browser_step()` 分支和白名单列表
- **合并** `browser_expand_branch` into `browser_snapshot`，加 `expand_key` 参数
- **删除** `browser_expand_branch` from `_BROWSER_OPS`、两个执行器中的分支
- **重命名** `browser_get_element_by_number` → `browser_lookup_selector`，每次调用刷新缓存
- **更新** `prompts/` 中所有引用 `browser_eval` 的地方改为 `eval_js`
- **更新** `prompts/` 中 `get_element_by_number` → `lookup_selector`

## Capabilities

### New Capabilities
- `eval-js`: 独立 tool 形式的 JS 执行能力，结果可通过 `{path}` 被其他 tool 引用

### Modified Capabilities
- `browser-snapshot`: 新增 `expand_key` 参数，替代独立的 expand_branch op
- `browser-get-element`: 能力不变，重命名为 `lookup_selector`，调用语义更清晰

## Impact

- **代码**：`tools/registry.py` 减 2 op 加 1 handler；`engine/executor.py` 删 2 分支改 1 分支；`engine/eval_agent.py` 更新 tool 名；`engine/_harness/tool_executor.py` 删 scratchpad 快捷路径；`cdp/playwright_bridge.py` 更新 LLM 提示文本；`engine/_lifecycle/compensation.py` 清理死条目
- **API**：LLM 可见的 tool 从 `browser_eval` + `browser_expand_branch` + `browser_get_element_by_number` 变为 `eval_js` + `browser_lookup_selector`，snapshot 多一个可选参数
- **Preset 兼容性**：**BREAKING** — 旧 pipeline YAML 中 `{type: eval, ...}` 和 `{type: expand_branch, ...}` 会报 `Unknown op type` 错误。当前无存量 pipeline 使用这两个 op，风险可接受
- **Prompts**：system.md / tool_strategy.md / planner-expand.md / record_step.md 更新
