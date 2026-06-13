## ADDED Requirements

### Requirement: goal 步骤 interactive 注入
系统 MUST 在 goal 步骤启动前自动获取 interactive snapshot，并通过 `extend_system_message` 将 @eN 交互元素列表注入到 Agent 的 system message 中。

#### Scenario: goal 步骤启动前获取 interactive snapshot
- **WHEN** `run_goal_step()` 被调用且 cdp_helpers 可用
- **THEN** 在创建 browser-use Agent 之前调用 `cdp_helpers.capture_snapshot_interactive()`
- **AND** 将返回的交互元素列表格式化为 @eN 引用文本

#### Scenario: 注入到 extend_system_message
- **WHEN** interactive snapshot 成功获取到交互元素
- **THEN** 将 @eN 元素列表追加到 `extend_system_message` 参数中
- **AND** 格式为 "当前页面可交互元素：\n@e1: button "提交"\n@e2: input[text] "搜索"..."
- **AND** 传递给 `Agent(extend_system_message=...)` 构造函数

#### Scenario: interactive snapshot 失败时的降级
- **WHEN** `capture_snapshot_interactive()` 失败（返回空或异常）
- **THEN** 不修改 `extend_system_message`
- **AND** goal 步骤正常执行，只是缺少 @eN 引用

#### Scenario: cdp_helpers 不可用
- **WHEN** `run_goal_step()` 被调用但 `cdp_helpers` 为 None
- **THEN** 跳过 interactive snapshot 获取
- **AND** goal 步骤正常执行

#### Scenario: 已有 system_prompt 时的合并
- **WHEN** `step_def` 中已包含 `system_prompt` 字符串
- **THEN** @eN 元素列表追加到已有 system_prompt 之后
- **AND** 两者之间用换行分隔

### Requirement: @eN 引用格式
系统 MUST 使用统一的 @eN 引用格式，使 Agent 可以通过 `@eN` 精确引用页面元素。

#### Scenario: @eN 引用格式
- **WHEN** interactive snapshot 返回元素列表
- **THEN** 每个元素的 ref 格式为 `@eN`（N 为从 1 开始的数字）
- **AND** 注入到 system message 的格式为 `@eN: <tag>[<type>] "<text>"`

#### Scenario: Agent 使用 @eN 引用
- **WHEN** Agent 需要点击或填写某个交互元素
- **THEN** Agent 可以在 action 参数中使用 `@eN` 作为 selector 引用
- **AND** 系统通过映射表将 `@eN` 解析为对应的 CSS selector

### Requirement: @eN 映射表与解析
系统 MUST 维护 `{ref: selector}` 映射表，并通过 `execute_browser_op()` 的 `element_map` 参数在 click/fill handler 中解析 @eN 引用。

#### Scenario: 映射表创建
- **WHEN** `capture_snapshot_interactive()` 返回 elements 数组
- **THEN** 系统构建 `{ref: selector}` 映射表（如 `{"@e1": "button#submit", "@e2": "input[name='q']"}`）
- **AND** 映射表存储在 goal step 上下文中

#### Scenario: 映射表生命周期
- **WHEN** 每次新的 interactive snapshot 执行
- **THEN** 映射表被重建（旧映射表被替换）
- **AND** 映射表仅在当前 goal step 期间有效

#### Scenario: execute_browser_op() 签名增加 element_map 参数
- **WHEN** `execute_browser_op()` 被调用
- **THEN** 签名变为 `(op_type: str, params: dict, cdp_helpers: object, element_map: dict | None = None)`
- **AND** click/fill handler 可通过 `element_map` 解析 @eN 引用

#### Scenario: execute_browser_step() 构建并传递映射表
- **WHEN** `execute_browser_step()` 中 snapshot op 返回 interactive 模式结果
- **THEN** 从返回的 elements 中构建 `{ref: selector}` 映射表
- **AND** 在后续调用 `execute_browser_op()` 时传入 `element_map` 参数

#### Scenario: click handler 解析 @eN
- **WHEN** `execute_browser_op()` 收到 click op 且 value 以 `@e` 开头（如 `@e3`）
- **THEN** 从 `element_map` 中查找 `@e3` 对应的 CSS selector
- **AND** 使用解析后的 CSS selector 执行点击操作

#### Scenario: fill handler 解析 @eN
- **WHEN** `execute_browser_op()` 收到 fill op 且 selector 以 `@e` 开头
- **THEN** 从 `element_map` 中查找对应的 CSS selector
- **AND** 使用解析后的 CSS selector 执行填写操作

#### Scenario: @eN 在映射表中不存在
- **WHEN** click/fill handler 收到 `@eN` 引用但 `element_map` 中无对应条目
- **THEN** 操作失败并返回错误信息 "Unknown element reference: @eN"
