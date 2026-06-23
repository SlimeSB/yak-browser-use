## Error Recovery Guidance

When a tool call fails, follow this diagnostic process:

### 1. Read the error message
The error message contains specific information about what went wrong.

### 2. Diagnose the root cause
- **Element not found**: The selector may be wrong, the page may have changed, or the element is not yet loaded.
- **Timeout**: The page may be slow, or the expected condition never occurred.
- **Navigation error**: The URL may be invalid or blocked.

### 3. Take corrective action
- If the selector failed, use `browser_snapshot()` to see the current page state and find the correct selector.
- If the page is slow, wait for it to fully load before retrying.
- If the URL is invalid, ask the user for the correct URL.

### 4. Avoid blind retries
Do not retry the exact same operation without first diagnosing the failure. Each retry consumes the conversation budget.