## ADDED Requirements

### Requirement: 事件类型集中定义
项目 MUST 将 stream_callback 事件类型集中定义在 `Agent` 类中，不再在代码各处散落裸字符串（`"chat.tool_start"`、`"chat.tool_end"` 等）。事件 type 常量值 MUST 与旧代码一致，确保前端无需改动。

| 常量名 | type 值 | emit 时机 |
|--------|---------|----------|
| `EVENT_TURN_START` | `"turn_start"` | loop 每次迭代开始 |
| `EVENT_LLM_TURN` | `"llm_turn"` | LLM 响应返回后 |
| `EVENT_TOOL_START` | `"chat.tool_start"` | 每次工具调用开始 |
| `EVENT_TOOL_END` | `"chat.tool_end"` | 每次工具调用结束 |
| `EVENT_ERROR` | `"chat.error"` | 不可恢复错误 |

#### Scenario: 所有 emit 走 _emit 方法
- **WHEN** 审查 conversation_loop.py 和 tool_executor.py 的改动
- **THEN** 所有 `stream_callback({"type": "...", ...})` 形式的调用 MUST 改为 `self._emit(EVENT_XXX, ...)` 或等效的统一入口
- **AND** 代码中不存在裸的 `"chat.tool_start"` 等字符串字面量

### Requirement: 事件 shape 向前兼容
`_emit()` 发出的 dict shape MUST 与旧 stream_callback 一致，前端 WebSocket 收到的 message 不因重构而变化。`_emit(event_type, **data)` 内部 MUST 构造 `{"type": event_type, **data}`。

#### Scenario: tool_start 事件 shape 不变
- **WHEN** `browser_click` 工具开始执行
- **THEN** `_emit(EVENT_TOOL_START, tool_name="browser_click", args={...}, id="call_1")` 产生的 dict 为
  `{"type": "chat.tool_start", "tool_name": "browser_click", "args": {...}, "id": "call_1"}`
- **AND** 前端 `App.tsx:173` 的 `et === 'chat.tool_start'` 处理逻辑无需改动

#### Scenario: tool_end 事件 shape 不变
- **WHEN** `browser_click` 工具执行完成
- **THEN** `_emit(EVENT_TOOL_END, tool_name="browser_click", ok=True, duration_ms=150, error=None, id="call_1")` 产生的 dict 包含所有旧有字段
- **AND** 前端 `App.tsx:182` 的 `et === 'chat.tool_end'` 处理逻辑无需改动

#### Scenario: error 事件 shape 不变
- **WHEN** LLM 调用连续失败
- **THEN** `_emit(EVENT_ERROR, message="LLM 调用连续失败...")` 产生的 dict 为 `{"type": "chat.error", "message": "LLM 调用连续失败..."}`
- **AND** 前端 `App.tsx:200` 的 `et === 'chat.error'` 处理逻辑无需改动

### Requirement: tool_executor 复用 _emit
`tool_executor.py` 中的 `execute_tool_calls_sequential()` MUST NOT 直接构造事件 dict，而 MUST 通过 `Agent._emit()` 或等效的统一事件发送接口发出工具事件。`_execute_single_tool_call()` 的 CDP 重连错误事件（`tool_executor.py:388-391`）同样 MUST 通过统一入口发送。

#### Scenario: tool_executor 使用统一 emit
- **WHEN** `execute_tool_calls_sequential()` 中需要发送 `tool_start` 事件
- **THEN** 调用方式为 `stream_callback(EVENT_TOOL_START, tool_name=..., args=..., id=...)`（通过 `ToolContext.stream_callback` 或函数参数传入），而非裸字符串 `stream_callback({"type": "chat.tool_start", ...})`

#### Scenario: CDP 重连错误走统一 emit
- **WHEN** `_execute_single_tool_call()` 中 CDP 重连达到最大次数
- **THEN** 错误事件通过 `ctx.stream_callback` 或 `_emit` 发送
- **AND** 事件 dict 为 `{"type": "chat.error", "message": "浏览器连接丢失，请检查 Chrome 是否运行"}`
