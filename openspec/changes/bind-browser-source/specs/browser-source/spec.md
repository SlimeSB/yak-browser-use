## MODIFIED Requirements

### Requirement: browser_source tool description
The `browser_source` tool description in `_BROWSER_SCHEMAS` MUST be updated from a neutral description to a warning-focused description that communicates: (1) heavy/large output, (2) `output_to` is mandatory, (3) alternatives preferred, (4) how to read stored content.

Previous description:
> "Get the HTML source of the current page. Without selector: returns full page HTML. With selector: returns outerHTML of the matching element."

New description MUST contain warnings about size, `output_to` requirement, shared_store behavior, guidance on data_browse, and mention of alternatives.

#### Scenario: LLM inspects browser_source tool schema
- **WHEN** the LLM reads the browser_source function definition from the API
- **THEN** the description SHALL prominently warn that this tool returns large payloads and requires `output_to`

## REMOVED Requirements

### Requirement: browser_source returns HTML to context
**Reason**: HTML content directly in context window causes token bloat and degraded reasoning. HTML is now stored in shared_store and only metadata is returned.
**Migration**: LLM must use `data_browse(key=<output_to_key>)` to read stored HTML content, or use `browser_eval_js` for targeted extraction.
**Scope**: This change only affects chat mode (registry handler path). Pipeline/preset mode calls `execute_browser_op` directly and is unaffected by the `output_to` requirement — it still receives HTML in the result dict, but `strip_styles` now defaults to `True`.

#### Scenario: LLM calls browser_source in chat mode and expects HTML in response
- **WHEN** an LLM calls `browser_source(output_to="my_html")` in chat mode expecting to see HTML in the tool result
- **THEN** the response SHALL only contain `{"output_to": "my_html", "size": N, "note": "..."}` without any HTML content

#### Scenario: pipeline preset executes browser_source step
- **WHEN** a pipeline preset step executes `{"browser_source": {"strip_styles": false}}` via `execute_browser_op`
- **THEN** the result dict SHALL still contain `html` field (preset path is not intercepted by registry handler)
