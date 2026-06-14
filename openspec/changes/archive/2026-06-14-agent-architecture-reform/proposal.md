## Why

当前系统存在两层 Agent 架构：主 LLM（conversation_loop）通过 `goal_run` 工具委托复杂任务给 browser-use 子 Agent。这种工具式委托存在三个固有缺陷：

1. **子 Agent 不能问用户**：子 Agent 运行时主循环阻塞在 `await agent.run()`，两者不能同时活跃。子 Agent 遇到不确定的情况无法向用户澄清，只能猜测或失败。
2. **自学习半成品**：`_extract_learned_ops` 是 stub 实现，子 Agent 的操作不会自动写入 pipeline YAML。而主 LLM 直接用 browser_* 工具时每步调 `record_step` 是实时落盘的。
3. **上下文膨胀**：每次 `browser_snapshot()` 返回的 HTML（可达 15KB）和截图 base64 全部进入 messages 永久保留，随对话增长快速耗尽 token 预算。

browser-use Agent 的核心能力（页面简化、元素编号、元素定位）已实现在 `cdp/helpers.py` 中作为纯工具函数，不依赖 browser-use 库。去掉子 Agent 的条件已经成熟。

## What Changes

- **去掉 browser-use 子 Agent**：`goal_run` 不再 spawn 子 Agent，改为返回模式切换提示文本，引导主 LLM 用 `todo` + `browser_*` 逐步执行复杂任务。
- **新增 scratchpad 模块**：重数据（HTML、截图、@eN 元素列表）不进 messages，存入内存 scratchpad，messages 只保留摘要。
- **编排层过滤**：在 `tool_executor.py` 中对 `browser_snapshot` 和 `browser_source` 的结果进行重数据摘录 + scratchpad 写入 + 摘要生成。
- **增强现有工具**：`browser_snapshot` 加 `mode` 参数（默认 `interactive`），`browser_source` 加 `cached` 参数，`browser_get_element_by_number` 优先从 scratchpad 读取。
- **新增 goal-execution skill**：prompt 指引 LLM 在复杂任务场景下用 todo 拆解 + 逐步执行 + 不确定时问用户。
- **清理 orphan prompts**：将不再使用的 prompt 文件移入 `prompts/_archived/`。
- **新增 `check` 字段**：StepYaml 加 `check` 程序化验收字段，新增 `run_check()` 验收函数，为 preset 模式提供自动化验收基础设施。
- **简化 agent.py / executor.py**：stub `run_goal_step` 和 `execute_goal`，删除 `_extract_learned_ops`、`_save_partial_ops` 等辅助函数。

## Capabilities

### New Capabilities
- `scratchpad`: 重数据隔离存储，避免 HTML/截图等大体积数据进入 LLM 上下文
- `goal-execution`: 主 LLM 用 todo + browser_* 自主管理复杂浏览器任务，可中途问用户
- `step-check`: 程序化验收条件，支持 url_contains / element_exists / text_contains / element_visible

### Modified Capabilities
- `goal-run`: 从 spawn 子 Agent 改为模式切换信号，不再创建独立 Agent 实例
- `browser-snapshot`: 新增 mode 参数（interactive/full/simplified），默认 interactive，重数据走 scratchpad
- `browser-source`: 新增 cached 参数，支持从 scratchpad 读取缓存 HTML
- `browser-get-element`: 优先从 scratchpad element_map 查找，回退到 CDP _element_map

## Impact

- **engine/agent.py**：大幅简化，删除 browser-use 依赖，stub `run_goal_step`
- **engine/executor.py**：stub `execute_goal`，新增 `run_check()`，`execute_browser_op` 默认 mode 改为 `interactive`
- **engine/_harness/tool_executor.py**：新增编排层过滤逻辑，清理 goal_run 相关的 budget pause/resume
- **engine/_harness/tools.py**：更新 tool schema（加 mode/cached/check 参数），修正 record_step 描述
- **engine/scratchpad.py**（新建）：scratchpad 模块
- **prompts/**：更新 chat/preset system prompt，新建 goal-execution skill，清理 orphan prompts
- **compiler/schema.py**：StepYaml 加 `check` 字段
- **tests/**：新增 scratchpad 和编排层过滤测试，更新工具数量断言
- **依赖**：browser-use 库不再被 engine/agent.py 直接引用（可能仍被其他模块间接使用）
