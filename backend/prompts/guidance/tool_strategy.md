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
- `browser_get_element_by_number(ref)` — get element details by @eN reference

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