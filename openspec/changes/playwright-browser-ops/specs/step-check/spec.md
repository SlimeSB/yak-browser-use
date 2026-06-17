## MODIFIED Requirements

### Requirement: run_check 参数变更
`run_check()` 函数的签名 MUST 从 `run_check(check_def, cdp_helpers)` 改为 `run_check(check_def, bridge)`，所有浏览器操作通过 PlaywrightBridge 执行。

#### Scenario: url_contains 检查
- **WHEN** `run_check({"url_contains": "wd=机械键盘"}, bridge)` 被调用
- **THEN** 通过 `bridge.page.url` 获取当前页面 URL
- **AND** 如果 URL 包含 `"wd=机械键盘"` 则返回 `{"ok": true, "result": "url_contains: 通过"}`
- **AND** 如果不包含则返回 `{"ok": false, "result": "url_contains: 失败", "error": "URL 不包含 'wd=机械键盘'"}`

#### Scenario: element_exists 检查
- **WHEN** `run_check({"element_exists": "#search"}, bridge)` 被调用
- **THEN** 通过 `bridge.evaluate("!!document.querySelector('#search')")` 检查元素是否存在
- **AND** 如果元素存在则返回 `{"ok": true}`
- **AND** 如果不存在则返回 `{"ok": false}`

#### Scenario: text_contains 检查
- **WHEN** `run_check({"text_contains": "搜索结果"}, bridge)` 被调用
- **THEN** 通过 `bridge.evaluate("document.body.textContent || ''")` 获取页面文本
- **AND** 使用 `textContent` 而非 `innerText`（`textContent` 不受 CSS 影响，更可靠）
- **AND** 如果文本包含 `"搜索结果"` 则返回 `{"ok": true}`
- **AND** 如果不包含则返回 `{"ok": false}`

#### Scenario: element_visible 检查
- **WHEN** `run_check({"element_visible": ".result-list"}, bridge)` 被调用
- **THEN** 通过 `bridge.evaluate()` 执行 JS 检查元素可见性
- **AND** 检查 `display !== 'none'` 且 `visibility !== 'hidden'`
- **AND** 如果可见则返回 `{"ok": true}`
- **AND** 如果不可见或不存在则返回 `{"ok": false}`

#### Scenario: 多个条件同时检查
- **WHEN** `run_check({"url_contains": "wd=", "element_exists": "#search"}, bridge)` 被调用
- **THEN** 所有条件都通过才返回 `{"ok": true}`
- **AND** 任一条件失败则返回 `{"ok": false}`

#### Scenario: 空 check 定义
- **WHEN** `run_check({}, bridge)` 或 `run_check(None, bridge)` 被调用
- **THEN** 返回 `{"ok": true, "result": "无验收条件，默认通过"}`

### Requirement: runner_preset 调用方适配
`runner_preset.py` 中调用 `run_check()` 时 MUST 传入 `bridge` 而非 `cdp_helpers`。

#### Scenario: browser step 后验收
- **WHEN** `runner_preset.py` 调用 `execute_browser_step()` 返回且 `step_def.check` 不为 None
- **THEN** `runner_preset.py` 调用 `run_check(step_def.check, bridge)`
- **AND** 验收通过则继续下一步
- **AND** 验收失败则向用户输出失败原因并终止 pipeline 执行

#### Scenario: tool step 后验收
- **WHEN** `runner_preset.py` 调用 `execute_tool_step()` 返回且 `step_def.check` 不为 None
- **THEN** 同样调用 `run_check(step_def.check, bridge)` 进行验收
