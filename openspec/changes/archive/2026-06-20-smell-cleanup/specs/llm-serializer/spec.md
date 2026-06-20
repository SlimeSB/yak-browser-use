## ADDED Requirements

### Requirement: serialize_messages 函数
`backend/llm/client.py` MUST 提供 `serialize_messages(messages)` 模块级函数，将 vendored 消息 dataclass 列表序列化为 OpenAI 兼容的 dict 列表。该函数 MUST 是 `browser_use.llm.openai.serializer.OpenAIMessageSerializer.serialize_messages()` 的等价替代。

该函数作为 `client.py` 的模块级函数存在（不是 `LLMClient` 的方法），`agent.py` 通过 `from llm.client import serialize_messages` 导入。

#### Scenario: 序列化 SystemMessage
- **WHEN** 调用 `serialize_messages([SystemMessage(content="系统提示")])`
- **THEN** 返回 `[{"role": "system", "content": "系统提示"}]`

#### Scenario: 序列化 UserMessage
- **WHEN** 调用 `serialize_messages([UserMessage(content="用户消息")])`
- **THEN** 返回 `[{"role": "user", "content": "用户消息"}]`

#### Scenario: 序列化 AssistantMessage 含 tool_calls
- **WHEN** 调用 `serialize_messages([AssistantMessage(content="", tool_calls=[ToolCall(id="c1", function={"name": "x", "arguments": "{}"})])])`
- **THEN** 返回的 dict 包含 `"role": "assistant"` 和 `"tool_calls"` 键
- **AND** tool_calls 格式为 OpenAI API 期望的 shape

### Requirement: 流式路径导入兼容
`agent.py:184` 的 `OpenAIMessageSerializer.serialize_messages(converted)` 调用 MUST 替换为 `from llm.client import serialize_messages` 后等价。

#### Scenario: 流式路径序列化
- **WHEN** `_create_chat_llm_call()` 的流式路径执行 `serialize_messages(converted)`
- **THEN** 返回的 `openai_messages` 列表与旧 `OpenAIMessageSerializer.serialize_messages()` 返回的一致
- **AND** `agent.py:193-202` 的 tool message 替换逻辑仍然正常工作

### Requirement: 最小实现
`serialize_messages` 函数 MUST 只 port `OpenAIMessageSerializer.serialize_messages` 这一个静态方法，不搬运 `OpenAIMessageSerializer` 的完整类。实现 MUST 在 30 行以内。

#### Scenario: 非完整搬运
- **WHEN** 审视 `serialize_messages` 的实现
- **THEN** 函数中只包含序列化逻辑和必要的 import
- **AND** 不包含类定义或不相关的序列化方法
