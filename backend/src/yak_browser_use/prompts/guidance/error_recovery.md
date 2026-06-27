## Error Recovery Guidance

When a tool call fails, follow this diagnostic process:

### 1. Read the error message
The error message contains specific information about what went wrong.

### 2. Diagnose the root cause
- **Element not found**: The selector may be wrong, the page may have changed, or the element is not yet loaded.
- **Timeout**: The page may be slow, or the expected condition never occurred.
- **Navigation error**: The URL may be invalid or blocked.
- **Permission denied**: The page may have blocked the operation (CSP, iframe, etc.).
- **Stale element**: The page DOM has changed since the element was last referenced.

### 3. Take corrective action
- If the selector failed, use `browser_snapshot(mode="aria")` to see the current page state and find the correct selector.
- If the element may have moved, use `browser_lookup_selector(ref)` to refresh its selector.
- If the page is slow, use `browser_wait(mode="load")` or `browser_wait(mode="selector", selector="...")` before retrying.
- If the URL is invalid, ask the user for the correct URL.

### 4. Pipeline execution recovery
When a step fails during pipeline execution:
1. **Confirm state**: Call `browser_snapshot(mode="aria")` to verify the current page — you may have been redirected, logged out, or hit an error page.
2. **Retry with adjustment**: Fix the selector or wait condition, then retry the same operation (max 2 retries).
3. **Alternative path**: If retries fail, try a different approach to achieve the same outcome (e.g., navigate via a different link, use `browser_eval_js` instead of click).
4. **Skip and compensate**: If the step is non-critical, skip it and adjust downstream steps accordingly.
5. **Escalate to user**: After 2 failed retries with different approaches, pause and tell the user what happened, what you tried, and ask how to proceed.

### 5. Avoid blind retries
Do not retry the exact same operation without first diagnosing the failure. Each retry consumes the conversation budget. Always check page state between retries.
