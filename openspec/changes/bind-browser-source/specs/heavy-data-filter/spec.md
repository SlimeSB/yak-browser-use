## REMOVED Requirements

### Requirement: _apply_heavy_data_filter browser_source branch
**Reason**: The filter was a post-hoc guard that replaced HTML in results after it already entered context. With the registry handler now intercepting at the source (HTML never enters result), this branch is dead code.
**Migration**: Tests referencing this branch (`test_orchestration_filter.py`, `test_integration_agent_reform.py`) SHALL be removed. Only the `browser_source` condition block (lines 470-483 of tool_executor.py) SHALL be deleted — the `_apply_heavy_data_filter` function itself REMAINS because the `browser_snapshot` branch is still active and needed.

#### Scenario: browser_source tool call completes successfully
- **WHEN** browser_source executes via the registry handler
- **THEN** HTML is stored in shared_store, result contains only metadata, and the deleted `_apply_heavy_data_filter` browser_source branch never executes

#### Scenario: _apply_heavy_data_filter still processes browser_snapshot
- **WHEN** `browser_snapshot` returns heavy data (progressive/a11y/full mode)
- **THEN** `_apply_heavy_data_filter` still processes it via the remaining `browser_snapshot` branches (function remains intact)
