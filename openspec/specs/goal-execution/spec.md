## ADDED Requirements

### Requirement: goal-execution 模式
系统 MUST 在 LLM 调用 `goal_run(description)` 后引导其使用 `todo` + `browser_*` 工具逐步执行复杂任务，而非 spawn 独立的 browser-use 子 Agent。

#### Scenario: goal_run 返回模式切换提示
- **WHEN** LLM 调用 `goal_run(description="在淘宝搜索机械键盘并加入购物车")`
- **THEN** 工具返回标准提示文本，包含目标描述和执行指引
- **AND** 提示文本引导 LLM 用 `todo` 拆解为 3-6 个步骤
- **AND** 提示文本引导每步完成后调 `record_step`
- **AND** 提示文本引导不确定时直接问用户

#### Scenario: LLM 按指引拆解任务
- **WHEN** LLM 收到 goal_run 的提示文本
- **THEN** LLM 调用 `todo` 工具将目标拆解为具体步骤
- **AND** 每个步骤标记为 pending

#### Scenario: LLM 逐步执行并记录
- **WHEN** LLM 完成一个 todo 步骤（通过 browser_* 工具执行）
- **THEN** LLM 调用 `record_step` 将该步骤写入 pipeline
- **AND** 将该 todo 步骤标记为 completed
- **AND** 中间试探性操作（如"看看这个元素是什么"）不调 `record_step`

#### Scenario: LLM 遇到不确定情况
- **WHEN** LLM 在执行过程中遇到不确定的情况（如多个相似按钮、验证码）
- **THEN** LLM 输出文字描述当前情况和疑问
- **AND** 对话循环结束，等待用户回复
- **AND** 用户回复后 LLM 继续执行后续步骤

### Requirement: 操作失败恢复
系统 MUST 在 goal-execution skill 中提供操作失败时的恢复指引。

#### Scenario: 某步执行失败
- **WHEN** browser_* 工具返回错误
- **THEN** LLM 调 `browser_snapshot()` 确认当前页面状态
- **AND** 根据 snapshot 结果判断失败原因

#### Scenario: 元素不存在
- **WHEN** click/fill 操作因元素不存在而失败
- **THEN** LLM 检查选择器或用 `browser_get_element_by_number` 重新定位
- **AND** 可尝试换用其他选择器或方法重试 1-2 次

#### Scenario: 多次失败
- **WHEN** 同一操作重试 2 次后仍然失败
- **THEN** LLM 输出文字告诉用户当前情况
- **AND** 询问用户如何继续

### Requirement: 工具优先级指引
goal-execution skill MUST 提供清晰的工具选择优先级。

#### Scenario: 页面探索
- **WHEN** LLM 需要了解当前页面状态
- **THEN** 优先使用 `browser_snapshot()`（默认 interactive 模式，返回 @eN 列表）

#### Scenario: 查看原始 HTML
- **WHEN** LLM 需要查看完整页面结构
- **THEN** 使用 `browser_source()`（重数据自动写入 scratchpad）

#### Scenario: 查询元素详情
- **WHEN** LLM 需要获取某个 @eN 元素的详细信息
- **THEN** 使用 `browser_get_element_by_number(@eN)`

#### Scenario: 执行操作
- **WHEN** LLM 需要执行浏览器操作
- **THEN** 使用 `browser_click`、`browser_fill`、`browser_goto` 等工具
