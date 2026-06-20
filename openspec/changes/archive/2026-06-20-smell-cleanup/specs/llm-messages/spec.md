## ADDED Requirements

### Requirement: 消息类型 dataclass
项目 MUST 提供 vendored 的 LLM 消息类型，替代 `browser_use.llm.messages`，其 shape 与原有类型兼容，使 `agent.py` 的消息转换逻辑（`agent.py:156-172`）无需改动。

`SystemMessage`、`UserMessage`、`AssistantMessage`、`ToolCall` 四个 dataclass MUST 定义在 `backend/llm/messages.py` 中，字段名和默认值与 browser-use 的同名类一致。

#### Scenario: SystemMessage 构造
- **WHEN** 代码调用 `SystemMessage(content="系统提示")`
- **THEN** 返回 `content` 为 `"系统提示"` 的 `SystemMessage` 实例

#### Scenario: UserMessage 构造
- **WHEN** 代码调用 `UserMessage(content="用户消息")`
- **THEN** 返回 `content` 为 `"用户消息"` 的 `UserMessage` 实例

#### Scenario: AssistantMessage 无 tool_calls
- **WHEN** 代码调用 `AssistantMessage(content="回复内容")`
- **THEN** 返回 `content` 为 `"回复内容"`、`tool_calls` 为 `None` 的 `AssistantMessage` 实例

#### Scenario: AssistantMessage 含 tool_calls
- **WHEN** 代码调用 `AssistantMessage(content="", tool_calls=[ToolCall(...)])`
- **THEN** 返回包含指定 `tool_calls` 列表的 `AssistantMessage` 实例

#### Scenario: ToolCall 从 dict 构造
- **WHEN** 代码调用 `ToolCall(**{"id": "call_1", "type": "function", "function": {"name": "browser_click", "arguments": "{}"}})`
- **THEN** 返回字段与输入 dict 一致的 `ToolCall` 实例
- **AND** `agent.py:165` 的 `BUMessageToolCall(**tc)` 模式无需改动即可工作

### Requirement: 消息类型最小保留
`backend/llm/messages.py` MUST NOT 搬运 browser-use 的完整消息模块。只保留四个 dataclass，不引入继承链、缓存控制、`BaseMessage` 基类、序列化方法等用不到的部分。

#### Scenario: 只定义必要的类
- **WHEN** 审视 `backend/llm/messages.py` 的内容
- **THEN** 文件中只包含 `ToolCall`、`SystemMessage`、`UserMessage`、`AssistantMessage` 四个 dataclass 定义
- **AND** 不包含继承关系或多余方法
