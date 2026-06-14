## ADDED Requirements

### Requirement: 程序化验收
系统 MUST 提供 `run_check()` 函数，支持对当前页面状态进行程序化验收。

#### Scenario: url_contains 检查
- **WHEN** `run_check({"url_contains": "wd=机械键盘"}, cdp_helpers)` 被调用
- **THEN** 获取当前页面 URL
- **AND** 如果 URL 包含 `"wd=机械键盘"` 则返回 `{"ok": true, "result": "url_contains: 通过"}`
- **AND** 如果不包含则返回 `{"ok": false, "result": "url_contains: 失败", "error": "URL 不包含 'wd=机械键盘'"}`
- **AND** 返回结果中包含当前 URL

#### Scenario: element_exists 检查
- **WHEN** `run_check({"element_exists": "#search"}, cdp_helpers)` 被调用
- **THEN** 通过 `document.querySelector("#search")` 检查元素是否存在
- **AND** 如果元素存在则返回 `{"ok": true, "result": "element_exists: 通过"}`
- **AND** 如果不存在则返回 `{"ok": false, "result": "element_exists: 失败"}`

#### Scenario: text_contains 检查
- **WHEN** `run_check({"text_contains": "搜索结果"}, cdp_helpers)` 被调用
- **THEN** 获取页面 body 文本内容
- **AND** 如果文本包含 `"搜索结果"` 则返回 `{"ok": true}`
- **AND** 如果不包含则返回 `{"ok": false}`

#### Scenario: element_visible 检查
- **WHEN** `run_check({"element_visible": ".result-list"}, cdp_helpers)` 被调用
- **THEN** 通过 JS 检查元素是否可见（非 `display:none`、非 `visibility:hidden`、有尺寸）
- **AND** 如果可见则返回 `{"ok": true}`
- **AND** 如果不可见或不存在则返回 `{"ok": false}`

#### Scenario: 多个条件同时检查
- **WHEN** `run_check({"url_contains": "wd=", "element_exists": "#search"}, cdp_helpers)` 被调用
- **THEN** 所有条件都通过才返回 `{"ok": true}`
- **AND** 任一条件失败则返回 `{"ok": false}`，error 中包含第一个失败条件的描述

#### Scenario: 空 check 定义
- **WHEN** `run_check({}, cdp_helpers)` 或 `run_check(None, cdp_helpers)` 被调用
- **THEN** 返回 `{"ok": true, "result": "无验收条件，默认通过"}`

### Requirement: StepYaml check 字段
`StepYaml` MUST 支持可选的 `check` 字段用于定义程序化验收条件。

#### Scenario: check 字段定义
- **WHEN** pipeline YAML 中 step 包含 `check: { url_contains: "wd=机械键盘", element_exists: "#search" }`
- **THEN** `StepYaml.check` 解析为 `{"url_contains": "wd=机械键盘", "element_exists": "#search"}`
- **AND** `to_step_def()` 将 `check` 传递到 `StepDef.check`

#### Scenario: check 字段为空
- **WHEN** pipeline YAML 中 step 不包含 `check` 字段
- **THEN** `StepYaml.check` 为 `None`
- **AND** 不影响 step 正常执行

### Requirement: runner_preset 集成
`run_check()` MUST 由 `runner_preset.py` 在 step executor 返回后调用，而非在 StepMachine 内部。

#### Scenario: browser step 后验收
- **WHEN** `runner_preset.py` 调用 `execute_browser_step()` 返回且 `step_def.check` 不为 None
- **THEN** `runner_preset.py` 调用 `run_check(step_def.check, cdp_helpers)`
- **AND** 验收通过则继续下一步
- **AND** 验收失败则向用户输出失败原因并终止 pipeline 执行（与现有 step 执行失败的 fallback 行为一致）

#### Scenario: tool step 后验收
- **WHEN** `runner_preset.py` 调用 `execute_tool_step()` 返回且 `step_def.check` 不为 None
- **THEN** 同样调用 `run_check()` 进行验收

#### Scenario: goal step 后跳过验收
- **WHEN** `runner_preset.py` 调用 `execute_goal_step()` 返回且 `step_def.check` 不为 None
- **THEN** 跳过 `run_check()`（goal step 已 stub 化，不执行实际操作，验收无意义）

#### Scenario: 无 check 字段时跳过
- **WHEN** `runner_preset.py` 执行完 step 但 `step_def.check` 为 None
- **THEN** 跳过验收，直接继续下一步
