## Why

当前 chat 模式的 Agent 在执行多步骤任务时，只能靠对话历史隐式追踪进度。没有结构化的任务管理机制，Agent 在复杂场景（如"打开 Amazon → 搜索 coffee → 查价格 → 发邮件"）中容易出现步骤遗漏、重复执行或进度丢失的问题。用户也无法直观看到 Agent 当前在做什么、做到了哪一步。

引入 `todo` 工具可以让 Agent 自主创建、更新、追踪任务列表。这是轻量、非侵入的改进——不给 conversation_loop 加逻辑，不给 system prompt 加结构，只给 Agent 多一个"草稿纸"。Hermes Agent 的实践已证明这个模式有效。

## What Changes

- **新建** `tools/todo_store.py`：TodoStore 数据类，提供 CRUD + merge + 去重功能，每个 chat session 一个实例
- **新建** `tools/todo.py`：`todo()` 纯函数，被 `_execute_single_tool_call` 路由调用，不注册 `BaseTool`（`tool_registry` 属于 browser-use Agent 层，这里用不上）
- **修改** `api/state.py`：`_EngineState` 添加 `_service` 字段，使 `Service` 变为单例，确保 `SessionState` 跨请求存活
- **修改** `api/routes.py`：复用 `engine_state._service` 而非每次创建新 `Service`
- **修改** `api/service.py`：`SessionState` 添加 `todo_store` 字段；`process_chat_message` 中通过 ContextVar 传递 store（独立于浏览器连接）
- **修改** `engine/_harness/tools.py`：新增 `TODO_TOOL` definition（OpenAI tool format），在 `get_all_tools()` 中返回
- **修改** `engine/_harness/tool_executor.py`：`_execute_single_tool_call` 添加 `todo` 路由，通过 ContextVar 获取 store
- **修改** `prompts/chat/system`：（可选）追加一行引导文本，让 LLM 更主动使用 `todo`

## Capabilities

### New Capabilities

- `todo-tool`: Agent 可在 chat 会话中调用 `todo` 工具创建、读取、更新任务列表，支持 `merge=True` 按 id 部分更新
- `todo-store-lifecycle`: TodoStore 随 SessionState 跨请求存活，同一对话中的多次用户消息共享同一个任务列表

### Modified Capabilities

无

## Impact

- **代码层面**：修改 6 个文件，新建 2 个文件，总改动约 +230 行。`api/service.py` 需同时处理注入 + compile skip。`tests/test_harness_tools.py` 测试断言需更新（`len(tools) == 16` → 17，`len(tools) == 15` → 16）
- **API 层面**：新增 `todo` 工具的 OpenAI function schema 暴露给 LLM，不新增 HTTP endpoint。`/api/chat/reset` 后 TodoStore 自动清空
- **外部依赖**：无新增
- **流程层面**：需要先修复 Service 生命周期（前置修复），否则 TodoStore 跨消息不存活。`chat_reset`、`chat_cancel` 端点也需复用 Service 单例
