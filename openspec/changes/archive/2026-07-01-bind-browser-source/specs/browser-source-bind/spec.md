## ADDED Requirements

### Requirement: browser_source SHALL require output_to parameter
registry handler MUST validate that `output_to` parameter is provided. If `output_to` is missing or empty, handler MUST return an error response with `ok: false` and a clear message instructing caller to provide a shared_store key name.

注意：使用 `output_to` 而非 `bind`，因为通用 `bind` 机制在 `_execute_single_tool_call` 中会在 dispatch 之前将 `bind` 从 args 中弹出，handler 无法感知。`output_to` 与 `browser_eval_js` 命名一致且不会被弹出。

#### Scenario: LLM calls browser_source without output_to
- **WHEN** LLM calls `browser_source` without providing `output_to` parameter
- **THEN** the handler returns `{"ok": false, "error": "browser_source requires an 'output_to' parameter..."}` with guidance on how to fix it

#### Scenario: LLM calls browser_source with output_to
- **WHEN** LLM calls `browser_source(output_to="page_html")`
- **THEN** the HTML is written to `shared_store["page_html"]` and the response contains only size metadata (no HTML content)

### Requirement: browser_source response SHALL NOT contain HTML content
After execution, the handler MUST remove HTML from result before returning to context. The response MUST include `output_to` (key name), `size`, and a `note` field with guidance on how to read the stored content via `data_browse`.

#### Scenario: HTML is large (>100KB)
- **WHEN** browser_source returns HTML larger than 100KB
- **THEN** the response note SHALL suggest using `data_browse` for paginated viewing and `browser_eval_js` for targeted extraction

#### Scenario: HTML is small (<100KB)
- **WHEN** browser_source returns HTML smaller than 100KB
- **THEN** the response note SHALL still include the output_to key and suggest next steps

### Requirement: browser_source schema SHALL indicate output_to is required and tool is heavy
The schema description in `_BROWSER_SCHEMAS["source"]` MUST clearly state: (1) this is a heavy tool returning large HTML, (2) `output_to` is required, (3) HTML is written to shared_store not returned, (4) preferred alternatives (browser_snapshot, browser_eval_js), (5) data_browse for reading content.

#### Scenario: LLM reads browser_source schema
- **WHEN** the LLM inspects the browser_source tool definition
- **THEN** the description SHALL contain "HEAVY", "MUST", "output_to", "shared_store", "data_browse", and mention alternatives

### Requirement: strip_styles default SHALL be True
The `strip_styles` parameter in `execute_browser_op` source branch MUST default to `True` instead of `False`. This applies to all execution paths (chat and preset).

#### Scenario: browser_source called without explicit strip_styles
- **WHEN** browser_source is invoked without `strip_styles` in args
- **THEN** the system SHALL strip `<style>` and `<script>` tags from the HTML before storing

#### Scenario: browser_source called with strip_styles=false
- **WHEN** browser_source is invoked with `{"strip_styles": false}` in args
- **THEN** the system SHALL preserve `<style>` and `<script>` tags in the HTML

### Requirement: output_to validation
The `output_to` parameter MUST be a non-empty string. If `output_to` is missing, empty string, or not a string type, the handler MUST return `{"ok": false, "error": ...}`.

#### Scenario: output_to is empty string
- **WHEN** LLM calls `browser_source(output_to="")`
- **THEN** handler returns error: `"browser_source requires a non-empty 'output_to' parameter"`

#### Scenario: output_to is not a string
- **WHEN** LLM calls `browser_source(output_to=123)`
- **THEN** handler returns error: `"browser_source 'output_to' must be a non-empty string"`
