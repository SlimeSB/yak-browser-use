## Tool Selection Strategy

### Priority: Use atomic browser tools first
Prefer these tools for most operations:
- `browser_goto(url)` — navigate to a URL
- `browser_click(selector)` — click an element
- `browser_fill(selector, text)` — fill an input field
- `browser_snapshot()` — capture page screenshot and HTML
- `browser_scroll(direction)` — scroll the page (up/down)
- `browser_source()` — get the full page HTML source
- `browser_eval(js_code)` — execute JavaScript on the page

### When to use goal_run
Use `goal_run(description)` only when:
- The task requires complex multi-step reasoning (e.g., "find the cheapest product on this page")
- Multiple pages need to be navigated autonomously
- Page content analysis is needed to decide the next action

### When to ask the user
If the user's instruction is ambiguous or has multiple valid interpretations, ask for clarification before acting.