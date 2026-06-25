## Tool Selection Strategy

### Priority: Use atomic browser tools first
Prefer these tools for most operations:
- `browser_goto(url)` — navigate to a URL
- `browser_click(selector)` — click an element
- `browser_fill(selector, text)` — fill an input field
- `browser_snapshot(mode?, query?, in_viewport?)` — 页面快照。推荐渐进式：simplified（概览）→ interactive+in_viewport+query（精准）→ interactive+query（全量搜）→ interactive（全量）
- `browser_scroll(direction)` — scroll the page (up/down)
- `browser_source(cached?)` — get the full page HTML source
- `eval_js(code)` — execute JavaScript on the page
- `browser_lookup_selector(ref)` — get element details by @e_XXXXX reference

### 页面内容与滚动
- 先用 `browser_snapshot(mode="simplified")` 了解页面结构（token 最少）
- 有目标后用 `browser_snapshot(mode="interactive", in_viewport=true, query="关键词")` 精准找
- 视口内没找到再用 `query` 全量搜，最后才用无参数全量
- 如果要操作页面上方/下方的元素，先 `browser_scroll` 滚动到目标区域，再用 `in_viewport=true` 刷新 snapshot
- 同一元素在多次 snapshot 中的 `@e_XXXXX` 编号是**稳定不变的**（只要 DOM 不重建）

### 反幻觉：Selector 必须来自实际页面
- **禁止**使用未经验证的 CSS selector。任何 click/fill 的 selector 必须先通过 `browser_snapshot` 或 `browser_lookup_selector` 确认存在
- Pipeline 中预先填写的 browser_ops 可能包含不准确的 selector —— 执行时以实际页面为准
- 如果 snapshot 中找不到 pipeline 指定的元素，用 `browser_snapshot(mode="interactive", query="关键词")` 重新搜索

### When to use goal_run
Use `goal_run(description)` to set a complex multi-step goal. After calling goal_run, use:
- `todo` to break the goal into 3-6 concrete steps
- `browser_*` tools to execute each step
- `record_step` to save each successful step
- `browser_snapshot(mode="simplified")` to verify page state between steps

Typical scenarios:
- Multi-page workflows (search → filter → select → checkout)
- Tasks requiring page content analysis to decide next action
- Complex data extraction across multiple pages

### When to ask the user
If the user's instruction is ambiguous or has multiple valid interpretations, ask for clarification before acting.

### 工具间数据传递 (shared_store)
工具支持通过 `source_key` 和 `_source_key` 在工具之间传递数据，避免大数据绕经 LLM 上下文：

**Producer（写入）：** 调用 `eval_agent` 时传 `source_key` 参数，结果自动存入 shared_store：
- `eval_agent(purpose="提取表格", snapshot="...", source_key="table_data")`
- 子 Agent 完成后的完整结果存入 `shared_store["table_data"]`

**Consumer（读取）：** **任意工具参数**中都可以用 `_source_key` 引用 shared_store 的数据，代替直接传值：
- `file_write(path="output.csv", content={"_source_key": "table_data"})`
- `captcha(type="ocr", image_bytes={"_source_key": "captcha_img"})`
- 所有参数位置都支持，`_source_key` 会在 dispatch 前被自动替换为实际数据

**注意：**
- `_source_key` 引用的是 shared_store 中 `{key}.data` 的值（即 producer 的原始返回数据）
- 如果引用的 key 不存在，会替换为 `__RESOLVE_FAILED__` 占位符，可重试纠正
- `_source_key` 替换发生在 schema 校验之前，LLM 不需要关心底层机制