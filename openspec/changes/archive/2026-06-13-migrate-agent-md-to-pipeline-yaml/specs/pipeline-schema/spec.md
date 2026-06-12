## ADDED Requirements

### Requirement: PipelineYaml 顶层结构
系统 MUST 支持 `pipeline.yaml` 的顶层字段：`name`（必填）、`description`（可选）、`required_params`（可选）、`system_prompt`（可选）、`url_aliases`（可选）、`steps`（必填，非空列表）。

#### Scenario: 解析最小合法文件
- **WHEN** 读取一个只包含 `name` 和含至少一个步骤的 `steps` 字段的 pipeline.yaml 文件
- **THEN** Pydantic 校验通过，返回 PipelineYaml 对象

#### Scenario: 缺少 name 字段
- **WHEN** 读取一个不含 `name` 字段的 pipeline.yaml 文件
- **THEN** Pydantic 抛出 ValidationError，错误信息指明 `name` 字段缺失

#### Scenario: steps 为空列表
- **WHEN** 读取一个 `steps: []` 的 pipeline.yaml 文件
- **THEN** Pydantic 抛出 ValidationError，因为 steps 至少需要一个元素

### Requirement: StepYaml 步骤定义
系统 MUST 支持步骤的公共字段：`name`（必填）、`description`（可选，多行文本使用 YAML `|` literal block scalar）、`depends_on`（可选，`list[str]`，元素为其他步骤的 `name`）、`system_prompt`（可选）、`input_ref`（可选，`Union[str, dict]`，字符串或键值映射均可）、`output_ref`（可选）、`input_schema`（可选）、`output_schema`（可选）、`params`（可选）。步骤类型由互斥字段决定：`browser_ops` → browser、`tool_name` → tool、`goal_description` → goal。若三个类型字段均未填写，则 `step_type` 默认推断为 "goal"。

#### Scenario: Browser 步骤
- **WHEN** 步骤包含 `browser_ops` 字段且不含 `tool_name` 和 `goal_description`
- **THEN** 该步骤的 `step_type` 自动推断为 "browser"，`is_goal` 为 false

#### Scenario: Tool 步骤
- **WHEN** 步骤包含 `tool_name` 字段且不含 `browser_ops` 和 `goal_description`
- **THEN** 该步骤的 `step_type` 自动推断为 "tool"

#### Scenario: Goal 步骤
- **WHEN** 步骤包含 `goal_description` 字段且不含 `browser_ops` 和 `tool_name`
- **THEN** 该步骤的 `step_type` 自动推断为 "goal"，`is_goal` 为 true

#### Scenario: 三个类型字段均未填写
- **WHEN** 步骤既不包含 `browser_ops`、`tool_name`，也不包含 `goal_description`
- **THEN** `step_type` 默认推断为 "goal"，行为与旧解析器的 `_finalize_step` 兜底逻辑一致

#### Scenario: 同时填写多个类型字段
- **WHEN** 步骤同时包含 `browser_ops` 和 `goal_description`
- **THEN** Pydantic 抛出 ValidationError，因为类型字段互斥

#### Scenario: depends_on 为字符串列表
- **WHEN** 步骤包含 `depends_on: ["打开首页", "填写表单"]`
- **THEN** `depends_on` 被解析为 `list[str]`，值为其他步骤的 `name`

#### Scenario: input_ref 为字符串
- **WHEN** 步骤包含 `input_ref: "some_raw_value"`
- **THEN** `input_ref` 被解析为 `str`，与旧解析器的 `input: some_string` 行为一致

#### Scenario: input_ref 为字典
- **WHEN** 步骤包含 `input_ref: {key: "value"}`
- **THEN** `input_ref` 被解析为 `dict`

### Requirement: BrowserOp 浏览器操作
系统 MUST 支持浏览器操作类型：`goto`（跳转）、`click`（点击）、`fill`（填写）、`snapshot`（截图）、`scroll`（滚动）、`source`（获取源码）、`eval`（执行 JS）、`wait`（等待）、`wait_for_network`（等待网络）。

Pydantic 层 BrowserOp 的类型为 `dict`（pass-through），不在 Pydantic 层做操作类型校验。格式转换由 `StepYaml.to_step_def()` 中的专用转换函数完成：遍历每个 dict 的唯一键值对，键为操作类型名、值为操作参数，映射为内部格式 `{type: op_type, ...}`。

#### Scenario: goto 操作
- **WHEN** browser_ops 中包含 `{goto: "https://example.com"}`
- **THEN** `to_step_def()` 将其转换为 `{type: "goto", value: "https://example.com"}`

#### Scenario: fill 操作含 selector
- **WHEN** browser_ops 中包含 `{fill: {selector: "#input", value: "hello"}}`
- **THEN** `to_step_def()` 将其转换为 `{type: "fill", selector: "#input", value: "hello"}`

#### Scenario: 未知操作类型
- **WHEN** browser_ops 中包含未定义的键名
- **THEN** dict pass-through 原样通过 Pydantic 校验；`to_step_def()` 中未知键名按通用规则转换：值为标量 → `{type: key, value: val}`，值为 dict → `{type: key, ...dict}`

### Requirement: PipelineYaml 到内部格式转换
系统 MUST 提供 `PipelineYaml.to_agent_md()` 将 Pydantic 模型转换为内部 `AgentMD` 对象，以及 `StepYaml.to_step_def()` 将步骤模型转换为 `StepDef` 对象，保证 engine 可以消费。

#### Scenario: to_agent_md 转换
- **WHEN** 调用 `PipelineYaml.to_agent_md()`
- **THEN** 返回 `AgentMD` 对象，其 `name`、`description`、`steps`、`frontmatter` 字段与 YAML 数据一致

#### Scenario: StepDef.key 由 name 决定
- **WHEN** 步骤 `name` 为 "打开首页"
- **THEN** 生成的 `StepDef.key` 等于 `name` 原值 "打开首页"（保留大小写，不做转换）
