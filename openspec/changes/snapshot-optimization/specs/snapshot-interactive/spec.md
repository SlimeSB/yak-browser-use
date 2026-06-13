## ADDED Requirements

### Requirement: 交互元素快照
系统 MUST 提供 `capture_snapshot_interactive()` 方法，提取页面中所有可交互元素并分配 @eN 引用。方法不写文件，返回数据 dict。

#### Scenario: 返回数据格式
- **WHEN** `capture_snapshot_interactive()` 成功执行
- **THEN** 返回 dict `{"elements": [...], "mode": "interactive"}`
- **AND** 每个元素包含 `ref`（@eN 格式）、`tag`、`type`、`text`、`selector` 字段
- **AND** 不写入任何文件

#### Scenario: 提取基本交互元素
- **WHEN** 页面包含 button、input（非 hidden）、select、textarea、a[href] 元素
- **THEN** 这些元素被包含在返回的 `elements` 数组中
- **AND** 元素按 DOM 遍历顺序编号（@e1, @e2, ...）

#### Scenario: 提取 ARIA 角色元素
- **WHEN** 页面包含 `[role="button"]`、`[role="link"]`、`[role="checkbox"]` 等 ARIA 角色元素
- **THEN** 这些元素也被提取并分配 @eN 引用

#### Scenario: 提取 onclick 元素
- **WHEN** 页面包含带有 `onclick` 属性的元素
- **THEN** 这些元素也被提取并分配 @eN 引用

#### Scenario: 过滤隐藏元素
- **WHEN** 页面包含 `display: none`、`visibility: hidden`、`offsetParent === null` 或不在视口内的元素
- **THEN** 这些元素不被包含在结果中

#### Scenario: 密码字段脱敏
- **WHEN** 页面包含 `type="password"` 的 input 元素
- **THEN** 该元素的 `value` 字段被替换为 `"***"`

#### Scenario: 元素数量上限
- **WHEN** 页面中可交互元素超过 50 个
- **THEN** 只返回前 50 个元素
- **AND** 在结果末尾包含截断提示信息

#### Scenario: 无交互元素
- **WHEN** 页面中没有任何可交互元素
- **THEN** 返回空数组 `[]`

### Requirement: pipeline YAML interactive 模式触发
系统 MUST 支持通过 pipeline YAML 的 `snapshot: { mode: "interactive" }` 语法触发 interactive 快照。

#### Scenario: YAML 显式指定 interactive 模式
- **WHEN** pipeline 步骤中 browser_ops 包含 `snapshot: { mode: "interactive" }`
- **THEN** `_convert_browser_op()` 产出 `{"type": "snapshot", "mode": "interactive"}`
- **AND** `execute_browser_step()` 将 mode 传入 `core_params = {"mode": "interactive"}`
- **AND** `execute_browser_op()` 从 `params["mode"]` 检测到 `"interactive"`，调用 `capture_snapshot_interactive()`
- **AND** `execute_browser_step()` 将返回的 `elements` 数据写入 `interactive_elements.json`

#### Scenario: YAML 仅指定 mode 无其他字段
- **WHEN** pipeline 步骤中 browser_ops 包含 `snapshot:\n  mode: interactive`
- **THEN** 行为与 `snapshot: { mode: "interactive" }` 一致

#### Scenario: execute_browser_step() snapshot handler 传递 mode
- **WHEN** `execute_browser_step()` 处理 snapshot op 且 op 包含 `mode` 字段
- **THEN** `core_params` 包含 `{"mode": op.get("mode", "full")}`
- **AND** 将 `core_params` 传递给 `execute_browser_op()`

### Requirement: interactive 模式降级链
系统 MUST 在 interactive 快照中实现 JS → full 两级降级链。

#### Scenario: JS 执行成功
- **WHEN** `_inject_simplify_js("interactive")` 成功返回结果
- **THEN** 使用 JS 返回的 elements 数据
- **AND** 返回 dict 中不包含 `degraded` 字段或 `degraded: false`

#### Scenario: JS 执行失败回退到 full
- **WHEN** `_inject_simplify_js("interactive")` 执行失败或无结果
- **THEN** 回退到 `capture_snapshot()` full 模式
- **AND** 返回 dict 中标记 `degraded: true`

#### Scenario: AXTree 路径不在本 change 中实现
- **WHEN** 考虑降级链设计
- **THEN** AXTree 路径作为后续优化选项，不在本 change 中实现
- **AND** 当前降级链仅包含 JS → full 两级

### Requirement: execute_browser_op() mode 分发
`execute_browser_op()` 的 snapshot handler MUST 根据 params 中的 mode 字段分发到对应方法。

#### Scenario: mode 为 interactive
- **WHEN** `execute_browser_op()` 收到 op `{"type": "snapshot", "mode": "interactive"}`
- **THEN** 从 `params.get("mode", "full")` 读取 mode 并分发
- **AND** 调用 `capture_snapshot_interactive()`
- **AND** 返回数据 dict 给 `execute_browser_step()` 处理文件 I/O

#### Scenario: mode 为 full
- **WHEN** `execute_browser_op()` 收到 op `{"type": "snapshot", "mode": "full"}`
- **THEN** 调用 `capture_snapshot()`
- **AND** 返回数据 dict 给 `execute_browser_step()` 处理文件 I/O

#### Scenario: 无 mode 字段默认 full
- **WHEN** `execute_browser_op()` 收到 op `{"type": "snapshot", "value": true}` 或 `{"type": "snapshot", "value": "true"}`
- **THEN** 调用 `capture_snapshot()` 作为默认 full 模式
