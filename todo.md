# TODO

> 从 `agent-harness-conversation-loop` 变更中延后的任务。

---

## 后端

### 多标签页管理

CDP 层已有基础原语（`Target.createTarget` / `Target.attachToTarget` / `_target_id`），需补齐：

| 步骤 | 位置 | 说明 |
|------|------|------|
| CDP 事件监听 | `cdp/daemon.py` | 监听 `Target.attachedToTarget` / `Target.detachedFromTarget`，暴露当前激活 tab 的 targetId |
| conversation_loop 绑定 | `engine/_harness/conversation_loop.py` | 从 daemon 读取 targetId，传给 tool_executor |
| tool_executor attach | `engine/_harness/tool_executor.py` | 每次 op 执行前调 `Target.attachToTarget` |
| 新会话开标签页 | session 管理 | 调 `Target.createTarget("about:blank")` |

### 集成测试

需要真实 CDP/浏览器环境，编写 chat → 浏览器操作 → 导出的端到端测试。

---

## 前端 (TypeScript/Electron)

### WebSocket 客户端 (IPC)

后端已就绪：`api/routes.py` 提供 `/ws/events` 端点，事件类型包括 `chat.message` / `chat.tool_start` / `chat.tool_end` / `chat.error` / `session.state`。

前端需在 `electron-app/` 中实现 WebSocket 连接、事件分发、断线重连。

### Chat UI

- 消息列表（用户消息 + Agent 响应 + 工具调用记录）
- 输入框 + 发送按钮
- 浏览器预览区域（headful 模式已可见，此为非必需）
