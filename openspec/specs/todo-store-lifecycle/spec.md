## ADDED Requirements

### Requirement: TodoStore 随 SessionState 跨消息存活

Service 实例 MUST 在 `engine_state` 上作为单例持有。同一对话（SessionState）的多次 `/api/chat` 请求 MUST 共享同一个 `TodoStore` 实例。

#### Scenario: 跨消息读取 todo
- **WHEN** 用户在第一条消息中让 Agent 创建任务列表，Agent 调用 `todo(todos=[{"id": "1", "content": "任务一"}])`
- **AND** 用户再发第二条消息
- **THEN** Agent 在新消息的 loop 中调用 `todo()` 时，MUST 仍能读到 `[{"id": "1", "content": "任务一", "status": "pending"}]`

### Requirement: TodoStore 通过 ContextVar 传递给路由

`tools/todo_store.py` 中 MUST 定义一个 `contextvars.ContextVar`（名 `current_store`），`api/service.py` 在调用 `run_conversation_loop` 前 set 当前 session 的 `todo_store`，路由端在需要时 get。ContextVar 不依赖浏览器连接，纯文本场景下同样可用。

#### Scenario: 正常传递
- **WHEN** `process_chat_message` 将要调用 `run_conversation_loop`
- **THEN** 系统将 `current_store` 设为 `session.todo_store`

#### Scenario: 浏览器未连接时 todo 仍可用
- **WHEN** `chrome_daemon` 为 None（浏览器未连接）
- **AND** `process_chat_message` 收到文本消息
- **THEN** `current_store` 仍被正确设置，Agent 可正常调用 `todo` 工具

### Requirement: Tool definition 对 LLM 可见

`todo` 工具的 OpenAI function schema MUST 包含在 `get_all_tools()` 的返回值中，LLM 才能知道该工具的存在。

#### Scenario: get_all_tools 包含 todo
- **WHEN** 系统调用 `get_all_tools()`
- **THEN** 返回的工具列表中包含 name 为 `"todo"` 的条目
- **AND** 该条目的 `function.parameters` 包含 `todos`（array）和 `merge`（boolean）参数

### Requirement: 调用 `reset_session()` 时 TodoStore 被清空

用户调用 reset 时，MUST 创建全新的 `SessionState`，对应的 `TodoStore` 也为新实例，之前的所有 todo 条目丢失。

#### Scenario: reset 后 todo 列表为空
- **WHEN** Agent 已有任务列表 `[{"id": "1", "content": "任务一"}]`
- **AND** 用户调用 `/api/chat/reset`
- **AND** 用户新发消息让 Agent 检查任务
- **THEN** Agent 调用 `todo()` 返回 `[]`

### Requirement: `compile_session_to_preset` 跳过 todo 调用

将 session 编译为 pipeline preset 时，`todo` 工具调用 MUST 被跳过，不生成 pipeline step（类似 `edit_pipeline` 的处理方式）。

#### Scenario: todo 调用不出现在 pipeline 中
- **WHEN** session 的 assistant 消息中包含 `tool_calls` 且其中某条 `function.name = "todo"`
- **THEN** `compile_session_to_preset` 跳过该 tool_call，不生成对应 step

### Requirement: routing 通过硬编码分发而非热加载

`todo` 工具 MUST 不走 `execute_tool()` 的热加载路径，而是在 `_execute_single_tool_call` 中通过 `elif fn_name == "todo"` 硬编码路由，以确保 `store` 参数能被注入。

#### Scenario: todo 路由正常分发
- **WHEN** `_execute_single_tool_call` 收到 `fn_name = "todo"`
- **THEN** 路由通过 `current_store.get()` 获取 store
- **AND** 调用 `todo(todos=..., merge=..., store=store)` 并返回结果
