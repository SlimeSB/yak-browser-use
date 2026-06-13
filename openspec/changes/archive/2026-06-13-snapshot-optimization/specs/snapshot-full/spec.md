## MODIFIED Requirements

### Requirement: 全量快照
系统 MUST 保持 `capture_snapshot()` 方法的现有行为不变，同时支持通过 pipeline YAML 显式指定 full 模式。

#### Scenario: snapshot: true 向后兼容
- **WHEN** pipeline 步骤中 browser_ops 包含 `snapshot: true`
- **THEN** 调用 `capture_snapshot()` 执行 full 模式快照
- **AND** 行为与变更前完全一致

#### Scenario: snapshot: { mode: "full" } 显式指定
- **WHEN** pipeline 步骤中 browser_ops 包含 `snapshot: { mode: "full" }`
- **THEN** 调用 `capture_snapshot()` 执行 full 模式快照
- **AND** 行为与 `snapshot: true` 一致

#### Scenario: 截图 + HTML 产出
- **WHEN** `capture_snapshot()` 成功执行
- **THEN** 返回 dict `{"screenshot_base64": "...", "html": "..."}`
- **AND** `execute_browser_step()` 将截图写入 `screenshot_<ts>.png`，HTML 写入 `page.html`

#### Scenario: 截图失败时继续
- **WHEN** `Page.captureScreenshot` 失败
- **THEN** 不中断执行，继续获取 HTML
- **AND** 返回结果中 `screenshot_base64` 为空字符串

#### Scenario: HTML 获取失败时继续
- **WHEN** `Runtime.evaluate` 获取 outerHTML 失败
- **THEN** 不中断执行
- **AND** 返回结果中 `html` 为空字符串

### Requirement: CLI snapshot 命令模式参数
CLI `chrome snapshot` 命令 MUST 支持 `--mode` 参数选择快照模式。

#### Scenario: 默认 full 模式
- **WHEN** 执行 `lbu chrome snapshot` 不带 `--mode` 参数
- **THEN** 使用 full 模式，产出 screenshot_<ts>.png 和 snapshot_<ts>.html

#### Scenario: 指定 interactive 模式
- **WHEN** 执行 `lbu chrome snapshot --mode interactive`
- **THEN** 使用 interactive 模式，产出 interactive_elements.json

#### Scenario: 指定 simplified 模式
- **WHEN** 执行 `lbu chrome snapshot --mode simplified`
- **THEN** 使用 simplified 模式，产出 page_summary.txt、detected_lists.json、detected_tables.json

#### Scenario: 无效 mode 参数
- **WHEN** 执行 `lbu chrome snapshot --mode invalid`
- **THEN** argparse 拒绝并显示错误信息，提示有效选项为 full/interactive/simplified

### Requirement: StepYaml snapshot op 的 dict value 支持
StepYaml 的 browser_ops 中 snapshot op 的 value 字段 MUST 支持 dict 类型以传递 mode 参数。

#### Scenario: snapshot: true 向后兼容
- **WHEN** pipeline YAML 中 `snapshot: true`
- **THEN** `_convert_browser_op()` 产出 `{"type": "snapshot", "value": true}`
- **AND** `execute_browser_op()` 将 `value=true` 视为 mode="full"

#### Scenario: snapshot: { mode: "interactive" }
- **WHEN** pipeline YAML 中 `snapshot: { mode: "interactive" }`
- **THEN** `_convert_browser_op()` 产出 `{"type": "snapshot", "mode": "interactive"}`
- **AND** `execute_browser_op()` 读取 `params["mode"]` 分发到 `capture_snapshot_interactive()`

#### Scenario: snapshot: { mode: "simplified" }
- **WHEN** pipeline YAML 中 `snapshot: { mode: "simplified" }`
- **THEN** `_convert_browser_op()` 产出 `{"type": "snapshot", "mode": "simplified"}`
- **AND** `execute_browser_op()` 读取 `params["mode"]` 分发到 `capture_snapshot_simplified()`

#### Scenario: snapshot: { mode: "full" }
- **WHEN** pipeline YAML 中 `snapshot: { mode: "full" }`
- **THEN** `_convert_browser_op()` 产出 `{"type": "snapshot", "mode": "full"}`
- **AND** `execute_browser_op()` 读取 `params["mode"]` 分发到 `capture_snapshot()`

### Requirement: execute_browser_op() mode 分发
`execute_browser_op()` 的 snapshot handler MUST 根据 params 中的 mode 字段分发到对应方法。

#### Scenario: value 为 True 或 "true" 字符串
- **WHEN** `execute_browser_op()` 收到 `{"type": "snapshot", "value": true}` 或 `{"type": "snapshot", "value": "true"}`
- **THEN** 调用 `capture_snapshot()` 作为默认 full 模式

#### Scenario: params 含 mode="full"
- **WHEN** `execute_browser_op()` 收到 `{"type": "snapshot", "mode": "full"}`
- **THEN** 调用 `capture_snapshot()`

#### Scenario: params 含 mode="interactive"
- **WHEN** `execute_browser_op()` 收到 `{"type": "snapshot", "mode": "interactive"}`
- **THEN** 调用 `capture_snapshot_interactive()`

#### Scenario: params 含 mode="simplified"
- **WHEN** `execute_browser_op()` 收到 `{"type": "snapshot", "mode": "simplified"}`
- **THEN** 调用 `capture_snapshot_simplified()`
