## 背景

当前 LLM 调用链路为：`api/routes.py` → `service.process_chat_message()` → `run_conversation_loop()` → `_call_llm_with_retry()` → `_create_chat_llm_call()` → `ChatOpenAI.ainvoke()`。整个链路使用非流式 `ainvoke()`，等完整响应后才返回。

已存在的基础设施：
- WebSocket (`/ws/events`) 已正常运行，`service._push_event()` 可向所有 WS 客户端广播事件
- `conversation_loop` 已有 `stream_callback` 参数，当前仅用于工具事件（`tool_start`、`tool_end`、`chat.error`）
- `ChatMessage` 类型定义在 `types.ts`，前端 ChatTab 通过 `messages` prop 接收并渲染消息列表

约束条件：
- `conversation_loop` 是阻塞式 async 函数，不可改成 generator（改动量大、风险高）
- `browser_use` 是第三方依赖，不应直接修改其 `ChatOpenAI` 源码
- 非聊天场景（converter/compiler）直接调用 `utils/browser.create_llm()`，与本次变更无关；但 `_create_chat_llm_call` 本身也在 agent.py 中被 `start_chat_agent` 等使用，非流式路径必须保持兼容

## 目标 / 非目标

**目标：**
- 聊天模式下 LLM 响应以流式推送到前端，用户可实时看到文字生成
- 支持 DeepSeek-R1 等模型的 `reasoning_content`，前端展示为可折叠 think 块
- 流式通道统一走现有 WebSocket，不引入额外连接
- 非聊天场景（converter/compiler）保持原有非流式行为，零影响

**非目标：**
- 不支持 SSE 双通道架构
- 不在服务端做 think 标签 scrub（模型 API 返回的数据已经干净）
- 不改造 `conversation_loop.py` 的结构（保持其 awaitable 接口）
- 不支持 `converter/convert.py` 和 `compiler/generator.py` 的流式化

## 关键决策

### 决策 1：WebSocket 单通道 vs SSE 双通道

**选择**：WebSocket 单通道。

**原因**：
- SSE 要求 HTTP 响应是 async generator，但 `conversation_loop` 是完整 awaitable，拆成 generator 改动巨大、容易引入 bug
- WebSocket 已存在且稳定运行（工具事件已走 WS），前端只需增加事件处理 case
- 单通道避免前端管理多个连接和时序同步的复杂性

**备选方案**：SSE（被排除，原因如上）。

### 决策 2：`_create_chat_llm_call` 用 OpenAI SDK 直调 vs 扩展 `ChatOpenAI`

**选择**：在 `_create_chat_llm_call` 内部通过 `llm.get_client()` 获取 `AsyncOpenAI` 实例，直接调用 `chat.completions.create(stream=True)`。

**原因**：
- `ChatOpenAI` 是第三方 dataclass，扩展或 monkey-patch 都不可靠
- `llm.get_client()` 已正确设置了 api_key、base_url 等参数，可直接复用
- 模型参数（temperature、frequency_penalty、reasoning_effort 等）可从 `llm` 实例的属性中读取，保持行为一致

### 决策 3：5 个独立回调 vs 单个 `stream_callback`

**选择**：5 个独立回调 `on_stream_start()`、`on_text_delta(text)`、`on_reasoning_delta(text)`、`on_tool_generated(name)`、`on_stream_end(has_tool_calls)`。

**原因**：
- `on_stream_start` / `on_stream_end` 用于流式生命周期管理，与内容回调职责分离
- 类型更安全、意图更清晰（每个回调只接收一种数据）
- 前端处理更简单（不需要根据 event type 做分支路由，回调本身就是路由）

### 决策 4：流式事件类型与 turn_index

**选择**：WebSocket 推送以下事件类型，每个事件均携带 `turn_index` 用于跨回合匹配。

| 事件 | 触发时机 | 数据 |
|------|---------|------|
| `chat.stream_start` | 每次 LLM 调用开始 | `{"turn_index": N}` |
| `chat.think_chunk` | 收到 `reasoning_content` | `{"content": "...", "turn_index": N}` |
| `chat.text_chunk` | 收到 `delta.content` | `{"content": "...", "turn_index": N}` |
| `chat.tool_generated` | 工具名首次出现 | `{"tool_name": "...", "turn_index": N}` |
| `chat.stream_end` | 流式结束 | `{"has_tool_calls": bool, "turn_index": N}` |

`turn_index` 由路由层在发起 LLM 调用前计算（当前消息列表长度，即 HTTP 响应将要追加的消息位置），通过闭包捕获传入所有回调。同一轮 LLM 调用的所有事件携带相同的 `turn_index`。

### 决策 5：HTTP 响应与流式内容的协作

**选择**：前端 `ChatTab.handleSend` **保留** HTTP 响应中 `result.response` 的追加。WebSocket 流式事件对该消息进行**原地更新**（替换 `content`、追加 `reasoning`），而非创建独立的新消息。

**原因**：
- HTTP 追加的文本作为兜底：WebSocket 断开或流式事件未到达时，用户仍能看到完整回复
- 流式正常时，HTTP 文本瞬间被第一条 `text_chunk` 覆盖，用户看到的是实时流式内容
- 避免"跳过 HTTP"方案的脆弱性——不需要判断 WebSocket 连接状态

**备选方案**：跳过 HTTP 追加（被排除，因为 WebSocket 断开时会丢失全部回复）。

### 决策 6：`chat.message` 事件抑制

**选择**：流式模式下，`conversation_loop.py` 发送的 `chat.message` 事件必须被抑制。通过 `_create_chat_llm_call` 闭包内的 `_streaming_active` 标记实现：路由层在 `service._push_event` 的包装中检查该标记，当标记为 `True` 时丢弃 `chat.message` 事件。

**原因**：
- `chat.message` 与流式 `chat.text_chunk` 内容完全重复
- 标记由 callable 闭包管理，生命周期与 LLM 调用一一对应，无竞态问题
- 比路由层猜测过滤更精确（只有流式激活的 LLM 调用才需抑制）

### 决策 7：`turn_index` 跨回合匹配

**选择**：路由层发起 LLM 调用前计算 `turn_index = len(messages)`（即 HTTP 响应将要追加的消息位置），通过闭包捕获传入所有 5 个回调。前端根据 `turn_index` 精确匹配消息，而非"找最后一条 assistant"。

**原因**：
- 防止跨回合污染：用户快速连续发消息时，前一轮的流式事件不会覆盖后一轮的消息
- 支持缓冲：`chat.text_chunk` 先于 HTTP 响应到达时，按 `turn_index` 缓存，待 HTTP 追加后立即应用
- 支持 retry：同一 `turn_index` 的多次 `stream_start` 自然覆盖旧状态

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| 流式中断（网络波动、API 超时） | 前端显示不完整消息，当前 `_call_llm_with_retry` 重试 3 次后放弃 | 重试机制无需修改，流式失败时异常由 retry 层捕获，逐次重试时前端会收到新的 `stream_start`，自然覆盖上次内容 |
| 回调在 retry 过程中重复调用 | 同一轮 LLM 调用重试时，前端收到多组 stream_start/end 事件，同一 turn_index 状态被写入多次 | 前端 `stream_start` 按 turn_index 重置状态，最后一次成功的流式内容生效；失败的中间尝试被自然覆盖 |
| `ChatTab.handleSend` 跳过 response 后错误信息无法展示 | 流式失败时 HTTP 返回 `{ok: false, error: ...}` | 采用原地更新模式后不存在此风险——HTTP 响应总是追加消息，流式仅做原地更新。HTTP error 分支保留原有 `Error: ...` 追加 |
| 非聊天场景误受回调影响 | converter/compiler 不传回调，走原有 `ainvoke` 路径 | 零影响 |
| `chat.message` 事件与流式内容重复 | conversation_loop 在流式结束后发出重复的 `chat.message` | 流式模式下抑制 `chat.message` 事件发送

## 迁移计划

1. 无需数据迁移，纯代码变更
2. 上线步骤：
   - 部署新版本后端（`_create_chat_llm_call` 支持回调，未传回调时走原路径）
   - 部署新版本前端（WS 处理器加新事件 case，ChatTab 增加流式渲染逻辑）
3. 回滚：重新部署旧版本即可，前端不处理新事件类型不会出错
4. 兼容性：后端向前兼容（未传回调 = 原有行为），前端向后兼容（未收到流式事件 = 原有展示）

## 待确认问题

- 无。所有技术决策已与用户对齐确认。
