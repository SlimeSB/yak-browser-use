## ADDED Requirements

### Requirement: LLMClient 适配层接口兼容
`LLMClient` MUST 封装 `AsyncOpenAI` 并暴露与旧 `ChatOpenAI` 兼容的接口，使 `agent.py` 和 `conversation_loop.py` 的调用方无需改动代码即可切换。

具体兼容要求：
- `.ainvoke(messages, tools)` MUST 返回 `LLMResponse`，其 `.content` 和 `.tool_calls` 属性与旧响应对象对齐
- `.get_client()` MUST 返回 `AsyncOpenAI` 实例（供流式路径使用）
- `.model`、`.temperature`、`.max_completion_tokens`、`.frequency_penalty`、`.top_p`、`.seed`、`.reasoning_models`、`.reasoning_effort` 属性 MUST 可读，与 `ChatOpenAI` 同名属性对齐

#### Scenario: ainvoke 非流式调用
- **WHEN** 调用 `await llm.ainvoke(messages=[msg1, msg2], tools=[...])`
- **THEN** 返回 `LLMResponse` 实例
- **AND** `response.content` 为模型文本回复
- **AND** 如果模型返回了 tool_calls，`response.tool_calls` 为对应的列表
- **AND** `agent.py:178` 的 `response = await llm.ainvoke(**kwargs)` 模式无需改动
- **AND** `tools` 被显式传给 OpenAI API（修复 `ChatOpenAI.ainvoke()` 将 tools 放入 `**kwargs` 后因未展开而静默丢弃的 bug）

#### Scenario: get_client 流式调用
- **WHEN** 调用 `client = llm.get_client()`
- **THEN** 返回 `AsyncOpenAI` 实例
- **AND** `agent.py:204` 的 `client = llm.get_client()` 模式无需改动
- **AND** 后续 `client.chat.completions.create(**create_kwargs)` 可正常工作

### Requirement: ainivoke 自动序列化消息
`LLMClient.ainvoke()` MUST 在调用 OpenAI API 之前，将 vendored 消息对象（`SystemMessage`、`UserMessage`、`AssistantMessage` dataclass 实例）序列化为 OpenAI 兼容的 dict 格式。序列化逻辑 MUST 使用 `backend/llm/serializer.py` 的 `serialize_messages()` 函数。

#### Scenario: 消息自动序列化
- **WHEN** 调用 `await llm.ainvoke(messages=[SystemMessage(content="..."), UserMessage(content="...")])`
- **THEN** `ainvoke` 内部先调用 `serialize_messages(messages)` 将消息转为 OpenAI dict
- **AND** 序列化后的消息列表传给 `AsyncOpenAI.chat.completions.create()`

### Requirement: reasoning 模型参数处理
`LLMClient.ainvoke()` MUST 在检测到 reasoning 模型时自动设置 `reasoning_effort` 并移除 `temperature`。该逻辑 MUST 与当前 `agent.py:218-223` 的行为一致。

#### Scenario: reasoning 模型移除 temperature
- **WHEN** `llm.model` 匹配 `llm.reasoning_models` 中的某个模式
- **THEN** 请求参数中 MUST 包含 `reasoning_effort`
- **AND** 请求参数中 MUST NOT 包含 `temperature` 和 `frequency_penalty`

### Requirement: LLMResponse.completion alias
`LLMResponse` MUST 提供 `.completion` 属性，其值与 `.content` 相同。`generator.py:72` 和 `convert.py:109` 使用 `response.completion if hasattr(response, "completion") else str(response)` 模式读取响应文本，必须兼容。

#### Scenario: completion alias
- **WHEN** 代码调用 `response.completion`
- **THEN** 返回与 `response.content` 相同的值

### Requirement: ChatOpenAI 默认值保留
`LLMClient.__init__` MUST 复制 `ChatOpenAI` 的关键默认值，使 LLM 行为与重构前一致。

| 参数 | 默认值 |
|------|--------|
| `temperature` | `0.2` |
| `frequency_penalty` | `0.3` |
| `max_completion_tokens` | `4096` |
| `max_retries` | `5`（可选，`_call_llm_with_retry` 已处理重试） |

#### Scenario: 默认值生效
- **WHEN** 创建 `LLMClient(model="gpt-4o")` 未指定 `temperature`
- **THEN** `llm.temperature` 为 `0.2`
- **AND** `llm.frequency_penalty` 为 `0.3`
- **AND** `llm.max_completion_tokens` 为 `4096`

### Requirement: 支持直接传参构造
`LLMClient.__init__` MUST 支持通过 `model`、`api_key`、`base_url` 参数直接构造，不依赖配置文件。`routes.py:90` 的 provider test 路径用 `ChatOpenAI(model=..., api_key=..., base_url=...)` 构造，不走 `create_llm()`，`LLMClient` 必须兼容此用法。

#### Scenario: 直接传参构造
- **WHEN** 调用 `LLMClient(model="gpt-4o", api_key="sk-xxx", base_url="https://...")`
- **THEN** `llm.model` 为 `"gpt-4o"`
- **AND** `llm.ainvoke(...)` 可用指定的 api_key 和 base_url
- **AND** 不读取 `userdata/provider.json` 或环境变量

### Requirement: ainvoke 签名兼容 **kwargs 展开
`LLMClient.ainvoke(messages, *, tools=None, **kwargs)` MUST 兼容 `agent.py:178` 和 `agent.py:378` 的 `await llm.ainvoke(**kwargs)` 调用模式，其中 `kwargs = {"messages": converted, "tools": tools_dict}`。`generator.py:72` 和 `convert.py:108` 的 `await llm.ainvoke([UserMessage(...)])`（无 tools）模式也必须兼容。

#### Scenario: **kwargs 展开
- **WHEN** 调用 `await llm.ainvoke(**{"messages": [msg1], "tools": [tool1]})`
- **THEN** 与 `await llm.ainvoke(messages=[msg1], tools=[tool1])` 等价

#### Scenario: 无 tools 的位置参数调用
- **WHEN** 调用 `await llm.ainvoke([UserMessage(content="prompt")])`
- **THEN** `tools` 默认为 `None`
- **AND** 底层 API 请求不包含 tools 字段

### Requirement: 非流式路径显式传递 tools
`LLMClient.ainvoke()` MUST 将 `tools` 参数显式传入 `client.chat.completions.create()` 的 `tools` 字段。当前 `ChatOpenAI.ainvoke()` 因 `**kwargs` 未展开导致 tools 被静默丢弃——非流式路径下 LLM 永远看不到工具定义。`LLMClient` 必须修复此 bug。

#### Scenario: tools 传入 OpenAI API
- **WHEN** 调用 `await llm.ainvoke(messages=[...], tools=[{"type": "function", ...}])`
- **THEN** 底层 `client.chat.completions.create()` 的请求包含 `"tools": [...]` 字段
- **AND** LLM 可以返回 tool_calls

### Requirement: LLMResponse 兼容 response_logger
`LLMResponse` MUST 提供以下属性使 `response_logger.py:52-85` 的 `_log_non_streaming_response()` 通过 `getattr` 访问时不崩：

| 属性 | 消费方 | 兼容方式 |
|------|--------|---------|
| `.completion` | `response_logger.py:58` | alias `.content`（已有） |
| `.reasoning` | `conversation_loop.py:156` | 新增字段，默认 `None`（`getattr(response, 'reasoning', None)`） |
| `.usage` | `response_logger.py:61` | `dict` 传入时 `getattr(dict, "prompt_tokens")` 返回 `None`，日志降级不崩 |
| `.model_name` | `response_logger.py:72` | 新增字段，默认 `""` |
| `.stop_reason` | `response_logger.py:74` | 新增字段，默认 `""` |

`.id`（`response_logger.py:71`）返回 `None` 即可，当前 `ChatOpenAI` 也不设置此值。

#### Scenario: response_logger 不崩
- **WHEN** `_log_non_streaming_response(persist_id, turn, response, summary)` 被调用且 `response` 是 `LLMResponse`
- **THEN** 不抛出 `AttributeError`
- **AND** usage 统计数据可能为空（已知降级，后续 PR 可改为 `isinstance(usage, dict)` 分支）
