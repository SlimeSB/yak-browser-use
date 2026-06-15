## 1. 后端 — LLM 流式调用

- [x] 1.1 重写 `engine/agent.py` 的 `_create_chat_llm_call`，接受 5 个可选回调：`on_stream_start`、`on_stream_end`、`on_text_delta`、`on_reasoning_delta`、`on_tool_generated`
- [x] 1.2 流式路径：通过 `llm.get_client()` 获取 `AsyncOpenAI`，调用 `chat.completions.create(stream=True)`
- [x] 1.3 流式路径：从 `llm` 实例读取模型参数，对推理模型（o1/o3/o4-mini/gpt-5 等）必须添加 `reasoning_effort` 并移除 `temperature` 和 `frequency_penalty`，与非流式 `ainvoke()` 行为一致
- [x] 1.4 流式路径：逐 chunk 解析 `delta.content`（回调 `on_text_delta`）、`delta.reasoning_content`（回调 `on_reasoning_delta`）、首次出现的工具名（回调 `on_tool_generated`）
- [x] 1.5 流式路径：按 index 累积 `delta.tool_calls` 的 id/name/arguments，流结束后组装完整 tool_calls 列表
- [x] 1.6 流式路径：返回具有 `.content` 和 `.tool_calls` 属性的响应对象（SimpleNamespace），与非流式路径返回形状兼容
- [x] 1.7 非流式路径：无回调时保持原有 `llm.ainvoke()` 行为，返回 `ChatInvokeCompletion`
- [x] 1.8 消息转换中增加 `role: "tool"` 的处理：流式路径转为 OpenAI 原生格式 `{"role": "tool", "content": ..., "tool_call_id": ...}`；非流式路径保持现有 `UserMessage` 包装
- [x] 1.9 流式模式：在闭包内部流式调用前调用 `on_stream_start()`，结束后调用 `on_stream_end(has_tool_calls)`；并设置一个标记（如闭包变量 `_streaming_active`）告知调用方当前处于流式模式

## 2. 后端 — WebSocket 事件绑定与 chat.message 抑制

- [x] 2.1 在 `api/routes.py` 的 `POST /api/chat` 路由中，利用现有 `service` 实例构建 5 个回调闭包，并通过闭包捕获 `turn_index`（当前消息列表长度，即 HTTP 响应将要追加的消息位置）
- [x] 2.2 `on_stream_start` → 调用 `service._push_event({"type": "chat.stream_start", "turn_index": turn_index})`
- [x] 2.3 `on_text_delta(text)` → 调用 `service._push_event({"type": "chat.text_chunk", "content": text, "turn_index": turn_index})`
- [x] 2.4 `on_reasoning_delta(text)` → 调用 `service._push_event({"type": "chat.think_chunk", "content": text, "turn_index": turn_index})`
- [x] 2.5 `on_tool_generated(name)` → 调用 `service._push_event({"type": "chat.tool_generated", "tool_name": name, "turn_index": turn_index})`
- [x] 2.6 `on_stream_end(has_tool_calls)` → 调用 `service._push_event({"type": "chat.stream_end", "has_tool_calls": has_tool_calls, "turn_index": turn_index})`
- [x] 2.7 将回调绑定后的 `llm_call` 传入 `service.process_chat_message()`
- [x] 2.8 流式模式下抑制 `chat.message` 事件：在路由层 `service._push_event` 的包装闭包中检查 `_streaming_active` 标记（由 `_create_chat_llm_call` 闭包设置），当标记为 `True` 时拦截 `type: "chat.message"` 事件不广播到前端

## 3. 前端 — 类型扩展

- [x] 3.1 在 `electron/src/renderer/types.ts` 的 `ChatMessage` 接口中新增 `reasoning?: string` 字段

## 4. 前端 — WebSocket 事件处理（turn_index 匹配 + 原地更新 + 缓冲）

- [x] 4.1 新增 `chat.stream_start` 事件处理：以 `turn_index` 为 key 创建状态记录（`streamStates[turn_index] = { accumulating: "", reasoningParts: [], complete: false }`）
- [x] 4.2 新增 `chat.text_chunk` 事件处理：将 `content` 累积到 `streamStates[turn_index].accumulating`；若消息列表中 `[turn_index]` 位置已存在 assistant 消息（HTTP 已追加），则将其 `content` 原地替换为累积内容；若消息尚不存在，保持缓冲
- [x] 4.3 新增 `chat.think_chunk` 事件处理：将 `content` 追加到 `streamStates[turn_index].reasoningParts`；若对应消息已存在则同步更新 `reasoning` 字段
- [x] 4.4 新增 `chat.tool_generated` 事件处理：暂时在对应消息上标记"工具调用中"（不阻塞 UI，后续迭代可做更丰富渲染）
- [x] 4.5 新增 `chat.stream_end` 事件处理：标记 `streamStates[turn_index].complete = true`；若 HTTP 已响应则清除该 turn 的流式状态
- [x] 4.6 在 HTTP 响应追加 assistant 消息后，检查对应 `turn_index` 是否有缓冲的流式内容，有则立即应用（兜底：缓冲未消费时消息显示 HTTP response 原文）

## 5. 前端 — ChatTab 流式渲染与 think 块

- [x] 5.1 `ChatTab.handleSend` 中：**保留** HTTP 成功返回时 `result.response` 的追加（原有行为不变），作为流式未到达时的兜底
- [x] 5.2 `ChatTab.handleSend` 中：保留 HTTP 错误（`result.ok` 为 `false`）和异常（catch 分支）的 `Error: ...` 追加逻辑
- [x] 5.3 助手消息气泡渲染：当 `msg.reasoning` 非空时，在正文前渲染可折叠的 think 块
- [x] 5.4 think 块默认折叠，标题显示"思考过程"，点击可展开/收起
- [x] 5.5 think 块使用 CSS 样式区分于正文（左侧边框、浅色背景、小字号）

## 6. 前端 — CSS 样式

- [x] 6.1 在 `electron/src/renderer/styles/global.css` 中新增 think 块的 CSS 样式（折叠/展开箭头、淡色背景、字体差异）
- [x] 6.2 流式文本的光标闪烁效果（可选，提升视觉反馈）

## 7. 验证

- [ ] 7.1 启动项目，在聊天中输入"你好"，确认文字实时逐字显示
- [ ] 7.2 使用 DeepSeek-R1 模型发消息，确认 think 块正确展示并可折叠
- [ ] 7.3 发送需要工具调用的消息，确认工具事件正常展示，且文字流不被工具事件打断
- [ ] 7.4 确认非聊天场景（converter/compiler）功能不受影响
- [ ] 7.5 断开 WebSocket 后发送消息，确认 HTTP response 依然正常显示（兜底生效）
- [ ] 7.6 确认聊天消息不会出现重复显示
- [ ] 7.7 快速连续发送两条消息，确认第一条的流式内容不会污染第二条
