## ADDED Requirements

### Requirement: 流式消息渲染

ChatTab 助手消息气泡 MUST 支持实时增量更新：HTTP 响应追加初始消息文本后，WebSocket 流式事件对该消息进行原地更新（文字替换为流式内容、追加推理内容），流式正常时用户看到实时打字效果，流式异常时保留 HTTP 响应文本作为兜底。

#### Scenario: HTTP 响应追加初始消息

- **WHEN** `handleSend` 收到 HTTP 成功响应（`result.ok` 为 `true`）
- **THEN** 系统 MUST 将 `result.response` 追加为一条 `assistant` 角色消息（保留原有行为）

#### Scenario: 文字增量原地更新

- **WHEN** 前端收到 `chat.text_chunk` WebSocket 事件
- **THEN** 系统 MUST 根据 `turn_index` 定位到消息列表中对应该轮的消息，将其 `content` 替换为流式累积的完整文字

#### Scenario: 推理内容追加

- **WHEN** 前端收到 `chat.think_chunk` WebSocket 事件
- **THEN** 系统 MUST 根据 `turn_index` 定位对应消息，将 `content` 追加到该消息的 `reasoning` 字段末尾

#### Scenario: 流式结束 — 标记完成

- **WHEN** 前端收到 `chat.stream_end` WebSocket 事件
- **THEN** 系统 MUST 根据 `turn_index` 定位对应消息并标记为已完成

#### Scenario: 新的流式开始 — 准备新占位

- **WHEN** 前端收到 `chat.stream_start`（LLM retry 场景）
- **THEN** 系统 MUST 根据 `turn_index` 将对应消息的流式状态重置，准备接收新内容

#### Scenario: 流式事件早于 HTTP 响应到达

- **WHEN** `chat.text_chunk` 或 `chat.think_chunk` 到达时对应 `turn_index` 的消息尚未被 HTTP 响应追加
- **THEN** 系统 MUST 将流式内容缓冲在对应 `turn_index` 的缓存中，待 HTTP 响应追加该消息后立即应用所有缓存内容

#### Scenario: 工具调用提示展示

- **WHEN** 前端收到 `chat.tool_generated` WebSocket 事件
- **THEN** 系统 MUST 根据 `turn_index` 在对应消息上展示工具调用提示（如 "[正在调用 browser_click...]"），后续由 `chat.tool_start`/`chat.tool_end` 替换为详细工具状态

### Requirement: Think 块折叠展示

助手消息气泡中的 `reasoning` 内容 MUST 渲染为可折叠的思考块，用户可以点击展开/收起查看模型的推理过程。

#### Scenario: 存在推理内容时默认折叠

- **WHEN** 助手消息的 `reasoning` 字段非空
- **THEN** 系统 MUST 在消息气泡中渲染一个折叠的思考块（默认收起），显示"思考过程"标题和展开/收起箭头

#### Scenario: 点击展开推理内容

- **WHEN** 用户点击折叠的思考块标题
- **THEN** 系统 MUST 展开并显示 `reasoning` 的完整文本内容

#### Scenario: 不存在推理内容时不展示

- **WHEN** 助手消息的 `reasoning` 字段为空
- **THEN** 系统 MUST NOT 渲染思考块，直接显示消息正文

### Requirement: ChatMessage 类型扩展

`ChatMessage` 接口 MUST 新增 `reasoning` 字段，用于存储模型的推理/思考内容。

#### Scenario: reasoning 字段类型

- **WHEN** 定义 `ChatMessage` 接口
- **THEN** `reasoning` 字段 MUST 为可选的字符串类型（`reasoning?: string`）

### Requirement: HTTP 响应兜底

当 WebSocket 未连接或流式事件未到达时，HTTP 响应必须作为兜底继续正常工作。

#### Scenario: 错误场景保留 HTTP 错误处理

- **WHEN** `handleSend` 收到 HTTP 失败响应（`result.ok` 为 `false`）或发生网络异常
- **THEN** 系统 MUST 保留原有的错误消息追加逻辑（`Error: ...`）

#### Scenario: 流式事件未到达时保留 HTTP 文本

- **WHEN** WebSocket 断开导致流式事件未到达
- **THEN** HTTP 响应已追加的初始消息文本保持显示，用户仍然能看到 AI 回复
