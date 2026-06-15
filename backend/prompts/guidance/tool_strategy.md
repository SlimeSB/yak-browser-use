## Tool Selection Strategy

### Priority: Use atomic browser tools first
Prefer these tools for most operations:
- `browser_goto(url)` — navigate to a URL
- `browser_click(selector)` — click an element
- `browser_fill(selector, text)` — fill an input field
- `browser_snapshot(mode?)` — capture page snapshot (interactive/full/simplified)
- `browser_scroll(direction)` — scroll the page (up/down)
- `browser_source(cached?)` — get the full page HTML source
- `browser_eval(js_code)` — execute JavaScript on the page
- `browser_get_element_by_number(ref)` — get element details by @eN or @e_XXXXX reference

### 页面内容与滚动
- `browser_snapshot(mode="interactive")` 只返回**当前视口内可见**的交互元素
- 如果要操作页面上方/下方的元素，先 `browser_scroll` 滚动，再 `browser_snapshot` 刷新
- 同一元素在多次 snapshot 中的 `@e_XXXXX` 编号是**稳定不变的**（只要 DOM 不重建）

### When to use goal_run
Use `goal_run(description)` to set a complex multi-step goal. After calling goal_run, use:
- `todo` to break the goal into 3-6 concrete steps
- `browser_*` tools to execute each step
- `record_step` to save each successful step
- `browser_snapshot()` to verify page state between steps

Typical scenarios:
- Multi-page workflows (search → filter → select → checkout)
- Tasks requiring page content analysis to decide next action
- Complex data extraction across multiple pages

### When to ask the user
If the user's instruction is ambiguous or has multiple valid interpretations, ask for clarification before acting.