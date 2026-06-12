## ADDED Requirements

### Requirement: 会话持久化
系统 SHALL 自动保存每次 chat 会话的完整历史，包括用户消息、Agent 响应、工具调用记录和执行结果。

#### Scenario: 会话自动保存
- **WHEN** 用户关闭应用
- **THEN** 当前会话被持久化到本地存储
- **THEN** 下次打开时可恢复会话历史

### Requirement: 预设保存
完成一次操作后，用户 SHALL 可以选择将操作步骤保存为预设（预设格式为 agent.md）。

#### Scenario: 保存为预设
- **WHEN** 用户点击「保存为预设」
- **THEN** conversation_loop 的执行历史被编译为 agent.md
- **THEN** 保存到预设目录
- **THEN** 预设出现在预设列表中

### Requirement: 预设回放
用户 SHALL 可以从预设列表中选择一个预设，系统将其编译为 conversation_loop 的 task 描述并执行。

#### Scenario: 回放预设
- **WHEN** 用户选择一个预设
- **THEN** compiler 解析预设的 agent.md → StepDef[]
- **THEN** PipelineTaskAdapter 转为 TaskDescriptor
- **THEN** conversation_loop 执行（可中途通过 chat 干预）
