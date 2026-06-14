## 1. 准备与基础改造

- [x] 1.1 **前置修复：Service 单例化** — `api/state.py` 中 `_EngineState` 添加 `_service` 字段；`api/routes.py` 中 `/api/chat` 端点复用该单例而非每次新建 `Service(engine_state)`
- [x] 1.2 **同步修复 `/api/chat/reset` 和 `/api/chat/cancel`** — 这两个端点当前也创建 `Service(engine_state)`，改为复用 `engine_state._service`
- [x] 1.3 **确认无循环导入** — `api/service.py` 的 `from tools.todo_store import TodoStore` 在路由层触发时是否正常；如有问题，改为延迟导入

## 2. 核心实现

- [x] 2.1 **新建 `tools/todo_store.py`** — TodoStore 数据类，实现 CRUD + merge + dedup + cap + uuid 自动生成；`write()` 中校验 `todos` 类型（非 list 时返回当前列表）、`merge` 类型（非 bool 时视为 `False`）
- [x] 2.2 **新建 `tools/todo.py`** — `todo()` 异步纯函数，接收 `todos`、`merge`、`store` 参数
- [x] 2.3 **注册 tool definition** — `engine/_harness/tools.py` 添加 `TODO_TOOL`（OpenAI function schema），在 `get_all_tools()` 中返回
- [x] 2.4 **集成到 SessionState** — `api/service.py` 顶部 import `TodoStore`，`SessionState` 添加 `todo_store: TodoStore = field(default_factory=TodoStore)`
- [x] 2.5 **注入 store 到 ContextVar** — `tools/todo_store.py` 模块级添加 `current_store = contextvars.ContextVar("todo_store", default=None)`；`api/service.py` 在调用 `run_conversation_loop` 前 `current_store.set(session.todo_store)`，完毕后 `reset`
- [x] 2.6 **注册路由** — `engine/_harness/tool_executor.py` 的 `_execute_single_tool_call` 中添加 `elif fn_name == "todo"` 分支，通过 `current_store.get()` 获取 store，调用 `todo(todos=..., merge=..., store=store)`
- [x] 2.7 **跳过 compile 中的 todo 调用** — `api/service.py` 的 `compile_session_to_preset` 中，在 `if tool_name == "edit_pipeline": continue` 同级添加 `tool_name == "todo"` 的跳过逻辑
- [x] 2.8 **（可选）追加 system prompt 引导** — `prompts/chat/system` 末尾追加一行，提示 LLM 对多步骤任务使用 `todo` 工具

## 3. 验证与收尾

- [x] 3.1 **单元测试：TodoStore** — `tests/test_todo_store.py` 覆盖 `test_write_read`、`test_merge`、`test_dedupe`、`test_cap_content`、`test_invalid_status`
- [x] 3.2 **更新测试断言** — `tests/test_harness_tools.py` 中 `assert len(tools) == 16` 改为 `17`，`assert len(tools) == 15` 改为 `16`
- [x] 3.3 **单元测试：tool definition** — `tests/test_harness_tools.py` 中验证 `get_all_tools()` 返回的列表包含 `"todo"`
- [ ] 3.4 **手动验证** — 在 chat 模式下发消息要求 Agent 创建多步骤任务，验证 Agent 能调 `todo` 创建/更新列表，下一条消息仍能读到；点击 reset 后再发消息，验证 todo 列表为空
- [x] 3.5 **运行现有测试** — `pytest tests/ -v` 确保现有测试通过
