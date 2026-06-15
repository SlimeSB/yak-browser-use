## Why

当前聊天功能在发送消息后，LLM 调用走 `ChatOpenAI.ainvoke()` 非流式路径，用户必须等待完整响应返回后才能看到内容。对于包含工具调用的复杂任务，等待时间可能长达数十秒，期间用户界面无任何反馈，体验较差。

同时 DeepSeek-R1、GLM 等支持推理展示的模型，其 `reasoning_content` 仅在流式模式下返回，非流式调用会丢失模型的思考过程，用户无法观察到 AI 的推理链路。

引入流式传输可以让用户实时看到文字生成过程（打字效果），并通过可折叠的 think 块展示模型推理内容，显著提升交互体验和可观测性。

## What Changes

- **新增**：`_create_chat_llm_call` 支持流式模式，接受 5 个回调（`on_stream_start/end`、`on_text_delta`、`on_reasoning_delta`、`on_tool_generated`），通过 OpenAI SDK 的 `stream=True` 直调 API，逐 chunk 解析并实时回调
- **新增**：5 个 WebSocket 流式事件类型（`chat.stream_start`、`chat.think_chunk`、`chat.text_chunk`、`chat.tool_generated`、`chat.stream_end`），每个事件携带 `turn_index` 用于前端跨回合消息匹配，通过现有 WebSocket 通道推送
- **新增**：前端 App.tsx WebSocket 处理器增加对上述 5 个事件的处理逻辑
- **新增**：ChatTab 助手消息气泡支持增量文本显示和可折叠的 think 块渲染
- **修改**：`ChatMessage` 类型增加 `reasoning` 字段用于存储模型推理内容
- **修改**：`POST /api/chat` 路由在创建 LLM 调用时将 Service 的推送方法作为流式回调传入
- **修改**：`ChatTab.handleSend` 保留 HTTP 响应追加，WebSocket 流式事件对末尾消息进行原地更新（替换 `content`、追加 `reasoning`），HTTP 文本作为流式未到达时的兜底

## Capabilities

### New Capabilities

- `llm-streaming`: LLM 响应通过 WebSocket 实时流式推送到前端，支持文字逐字显示和推理内容展示

### Modified Capabilities

- `chat-conversation`: 聊天助手消息的渲染方式从一次性展示改为支持增量更新和 think 块折叠

## Impact

- **后端文件**：`engine/agent.py`（`_create_chat_llm_call` 重写）、`api/routes.py`（回调绑定）
- **前端文件**：`App.tsx`（WS 事件处理）、`ChatTab.tsx`（流式渲染）、`types.ts`（类型扩展）
- **不涉及**：`service.py`、`utils/browser.py`、非聊天场景（converter/compiler）
- **需关注**：`conversation_loop.py` 在流式结束后仍会发送 `chat.message` 事件，需在后端抑制该事件以免与流式内容冲突
- **兼容性**：非流式路径保留，converter/compiler 等场景不受影响
