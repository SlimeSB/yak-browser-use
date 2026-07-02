## ADDED Requirements

### Requirement: LLMClient 适配层接口兼容

`LLMClient` MUST 封装 `AsyncOpenAI` 并暴露与旧 `ChatOpenAI` 兼容的接口，使 `conversation_loop.py` 的调用方无需改动代码即可切换。

#### Scenario: ainvoke 非流式调用
- **WHEN** 调用 `await llm.ainvoke(messages=[msg1, msg2], tools=[...])`
- **THEN** 返回 `LLMResponse` 实例
- **AND** `response.content` 为模型文本回复
- **AND** 如果模型返回了 tool_calls，`response.tool_calls` 为对应的列表

#### Scenario: get_client 流式调用
- **WHEN** 调用 `client = llm.get_client()`
- **THEN** 返回 `AsyncOpenAI` 实例

### Requirement: ainvoke 自动序列化消息

`LLMClient.ainvoke()` MUST 在调用 OpenAI API 之前，将 vendored 消息对象序列化为 OpenAI 兼容的 dict 格式。序列化逻辑 MUST 使用 `serialize_messages()` 函数。

### Requirement: 消息类型 dataclass

项目 MUST 提供 vendored 的 LLM 消息类型，替代 `browser_use.llm.messages`。`SystemMessage`、`UserMessage`、`AssistantMessage`、`ToolCall` 四个 dataclass MUST 定义在 `backend/llm/messages.py` 中。

#### Scenario: 只定义必要的类
- **WHEN** 审视 `backend/llm/messages.py` 的内容
- **THEN** 文件中只包含 `ToolCall`、`SystemMessage`、`UserMessage`、`AssistantMessage` 四个 dataclass 定义
- **AND** 不包含继承关系或多余方法

### Requirement: serialize_messages 函数

MUST 提供 `serialize_messages(messages)` 函数，将 vendored 消息 dataclass 列表序列化为 OpenAI 兼容的 dict 列表。该函数 MUST 是 `OpenAIMessageSerializer.serialize_messages()` 的等价替代。

#### Scenario: 序列化各类型消息
- **WHEN** 调用 `serialize_messages([SystemMessage(content="..."), UserMessage(content="..."), AssistantMessage(content="", tool_calls=[ToolCall(...)])`
- **THEN** 返回对应的 OpenAI 格式 dict 列表

### Requirement: 流式 LLM 调用

`_create_chat_llm_call` MUST 在传入回调时使用 OpenAI API 的 `stream=True` 参数进行流式调用，逐 chunk 解析 delta 内容并通过回调实时推送。回调包括 `on_stream_start`、`on_stream_end`、`on_text_delta`、`on_reasoning_delta`、`on_tool_generated`。

#### Scenario: 流式模式 — 文字增量推送
- **WHEN** LLM 流式返回 `delta.content` 包含文本
- **THEN** 系统 MUST 调用 `on_text_delta(text)` 回调，将文本增量推送给调用方

#### Scenario: 流式模式 — 推理内容推送
- **WHEN** LLM 流式返回 `delta.reasoning_content` 包含推理文本
- **THEN** 系统 MUST 调用 `on_reasoning_delta(text)` 回调，将推理增量推送给调用方

#### Scenario: 流式模式 — 工具名推送
- **WHEN** LLM 流式返回工具调用且工具名称首次出现
- **THEN** 系统 MUST 调用 `on_tool_generated(name)` 回调，告知调用方工具已被调用

#### Scenario: 流式模式 — 累积工具调用参数
- **WHEN** LLM 流式返回 `delta.tool_calls`
- **THEN** 系统 MUST 按 index 累积每个工具调用的 id、name、arguments，在流式结束后组装为完整的 tool_calls 列表返回

#### Scenario: 流式模式 — 返回兼容的响应对象
- **WHEN** 流式传输完成
- **THEN** 系统 MUST 返回一个具有 `.content`（完整文字）和 `.tool_calls`（工具调用列表）属性的响应对象，与 `ainvoke()` 的返回形状兼容

#### Scenario: 非流式模式 — 无回调时保持原有行为
- **WHEN** `_create_chat_llm_call` 未传入任何回调
- **THEN** 系统 MUST 走原有 `llm.ainvoke()` 非流式路径，返回 `ChatInvokeCompletion` 对象

#### Scenario: 流式开始回调
- **WHEN** 流式调用即将开始（`stream=True` 请求发起前）
- **THEN** 系统 MUST 调用 `on_stream_start()` 回调

#### Scenario: 流式结束回调
- **WHEN** 流式传输完成（所有 chunk 已处理）
- **THEN** 系统 MUST 调用 `on_stream_end(has_tool_calls)` 回调，传入是否为工具调用的布尔值

#### Scenario: 模型参数保持一致
- **WHEN** 流式调用创建 OpenAI 请求参数
- **THEN** 系统 MUST 从 `ChatOpenAI` 实例读取 `temperature`、`frequency_penalty`、`max_completion_tokens` 等参数
- **AND** 对于推理模型（o1/o3/o4-mini/gpt-5 等），系统 MUST 添加 `reasoning_effort` 参数并移除 `temperature` 和 `frequency_penalty`，与非流式 `ainvoke()` 的行为一致

### Requirement: 流式模式下抑制 chat.message 事件

当流式回调已激活时，`conversation_loop` 产生的冗余 `chat.message` 事件 MUST NOT 被广播到前端，避免内容重复。

#### Scenario: 流式模式下不发送 chat.message
- **WHEN** `_create_chat_llm_call` 已通过流式回调发送了所有文字内容
- **THEN** `conversation_loop` 在最终文本返回时 MUST NOT 再通过 `stream_callback` 发送 `chat.message` 事件

### Requirement: tool 消息格式兼容

流式路径 MUST 将 `role: "tool"` 消息直接转为 OpenAI 原生格式 `{"role": "tool", "content": ..., "tool_call_id": ...}`，而非走 `browser_use` 的 `UserMessage` 包装。

#### Scenario: tool 消息序列化
- **WHEN** 消息列表中包含 `role: "tool"` 的消息
- **THEN** 流式路径 MUST 将其保持为 OpenAI 原生 tool 消息格式
- **AND** 非流式路径保持现有行为（转为 `UserMessage`）

### Requirement: WebSocket 流式事件推送

`POST /api/chat` 路由 MUST 在创建 LLM 调用时将 `service._push_event()` 绑定为流式回调（包括 `on_stream_start`、`on_stream_end`、`on_text_delta`、`on_reasoning_delta`、`on_tool_generated`），确保流式内容通过现有 WebSocket 通道推送到前端。所有流式事件 MUST 包含 `turn_index` 字段，用于前端将流式内容匹配到正确的消息。

#### Scenario: 流式开始事件
- **WHEN** `on_stream_start()` 回调被调用
- **THEN** 系统 MUST 通过 WebSocket 推送 `{"type": "chat.stream_start", "turn_index": <当前消息序号>}` 事件

#### Scenario: 文字增量事件
- **WHEN** `on_text_delta(text)` 回调被调用
- **THEN** 系统 MUST 通过 WebSocket 推送 `{"type": "chat.text_chunk", "content": text, "turn_index": <序号>}` 事件

#### Scenario: 推理内容事件
- **WHEN** `on_reasoning_delta(text)` 回调被调用
- **THEN** 系统 MUST 通过 WebSocket 推送 `{"type": "chat.think_chunk", "content": text, "turn_index": <序号>}` 事件

#### Scenario: 工具生成事件
- **WHEN** `on_tool_generated(name)` 回调被调用
- **THEN** 系统 MUST 通过 WebSocket 推送 `{"type": "chat.tool_generated", "tool_name": name, "turn_index": <序号>}` 事件

#### Scenario: 流式结束事件
- **WHEN** `on_stream_end(has_tool_calls)` 回调被调用
- **THEN** 系统 MUST 通过 WebSocket 推送 `{"type": "chat.stream_end", "has_tool_calls": has_tool_calls, "turn_index": <序号>}` 事件

#### Scenario: turn_index 一致性
- **WHEN** 同一轮 LLM 调用产生多个流式事件
- **THEN** 所有事件 MUST 携带相同的 `turn_index` 值，与 HTTP 响应追加的消息在列表中的索引一致

### Requirement: reasoning 模型参数处理

`LLMClient.ainvoke()` MUST 在检测到 reasoning 模型时自动设置 `reasoning_effort` 并移除 `temperature`。

### Requirement: LLMResponse 兼容属性

`LLMResponse` MUST 提供 `.completion`（alias to `.content`）、`.reasoning`（默认 None）、`.usage`（默认 None）、`.model_name`（默认 ""）、`.stop_reason`（默认 ""）属性，使 `response_logger` 不崩。
