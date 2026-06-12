## ADDED Requirements

### Requirement: API Service 层
系统 SHALL 提供 `api/service.py` 作为业务逻辑的 service 层，封装以下操作：
- Session 管理（创建、恢复、保存）
- Pipeline 管理（编译、保存、列出预设）
- Chat 消息处理（转发到 conversation_loop）
- 事件推送（执行状态 → WebSocket）

#### Scenario: chat 消息处理
- **WHEN** 用户发送消息
- **THEN** service 层将消息转发到 conversation_loop
- **THEN** 执行结果通过回调/事件推回

### Requirement: IPC 通信
Electron 前端与后端之间 SHALL 通过 WebSocket + REST 双通道通信：
- REST: 预设管理、会话列表、设置
- WebSocket: chat 消息、执行事件推送、状态更新

WebSocket 事件类型 SHALL 包括：
- `chat.message` — Agent 文本响应（推送到前端 chat 界面）
- `chat.tool_start` — tool call 开始执行 {tool_name, args}
- `chat.tool_end` — tool call 执行完成 {tool_name, duration_ms, ok, error?}
- `chat.screenshot` — 浏览器截图定时推送 {screenshot_base64}
- `chat.error` — 不可恢复错误（CDP 断连、Chrome 崩溃）
- `session.state` — 会话状态变更（running/paused/completed/cancelled）

#### Scenario: WebSocket 推送执行进度
- **WHEN** conversation_loop 执行浏览器操作
- **THEN** 事件（tool_call 开始/结束、状态更新）通过 WebSocket 推送到前端
