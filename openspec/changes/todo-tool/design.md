## 背景

当前 chat 模式下，Agent 通过 `conversation_loop` 与 LLM 交互，使用 `get_all_tools()` 定义的 16 个工具（browser_*, goal_run, pipeline_*, record_step）。这层是 harness 层——独立于 browser-use Agent 内部的 `ToolRegistry` 体系。

Agent 执行多步骤任务时缺乏显式的任务追踪手段，只能依赖对话历史的隐式记忆。

本次设计涉及两个子系统的边界：
- **Harness 层（conversation_loop）**：负责调度工具、维护会话状态
- **API 层（api/）**：负责 service 生命周期、事件推送

跨层数据流：`SessionState.todo_store` → `ContextVar.set()` → `_execute_single_tool_call` 中 `ContextVar.get()` 读取。

## 目标 / 非目标

**目标：**
- Agent 能通过 `todo` 工具创建、读取、更新任务列表
- 同一对话中，todo 列表跨多次用户消息存活
- 最小侵入：不修改 `conversation_loop`、不碰 `system prompt`（可选引导除外）

**非目标：**
- 不实现 todo 持久化（进程重启后丢失，与现有 SessionState 保持一致）
- 不实现并发 session 支持（当前 FastAPI 为单进程顺序模型）
- 不给 browser-use Agent（`goal_run` 内部）注册 todo 工具

## 关键决策

### 决策 1：Service 单例化

**问题：** `api/routes.py` 每次 `/api/chat` 请求都新建 `Service(engine_state)`，`SessionState` 跨请求丢失。如果不修复，TodoStore 只存活于单次请求内的多轮 LLM turn 之间，用户发下一条消息就清空。

**方案：** `_EngineState` 添加 `_service` 字段，路由层懒初始化并复用。

**备选：** 用 Redis 或文件持久化 SessionState。否决，因为当前无持久化需求，且与现有设计不一致。

### 决策 2：store 通过 ContextVar 传递

**问题：** `_execute_single_tool_call` 需要访问 `TodoStore`，但它的签名只有 `cdp_helpers`、`tools_dir` 等参数，没有 session 上下文。而且 `cdp_helpers` 在浏览器未连接时为 `None`，不能作为传递通道。

**方案：** `tools/todo_store.py` 定义 `contextvars.ContextVar`，`api/service.py` 在调用 `run_conversation_loop` 前 set，路由端 get。ContextVar 是 async-safe 的线程局部存储，不依赖任何外部对象。

**备选：** 
- `cdp_helpers._todo_store`（否决：浏览器未连接时不可用）
- `run_conversation_loop` 新增参数（否决：改签名链路太长）
- `engine_state` 反向 import（否决：harness 层不应依赖 api 层）

### 决策 3：不走热加载

**问题：** `execute_tool()` 的文件热加载路径无法注入 `store` 参数——它只传递 LLM 提供的 `fn_args`。

**方案：** 在 `_execute_single_tool_call` 中添加 `todo` 特殊路由，与 `pipeline_*`、`goal_run` 同级别。

### 决策 4：不注册 `BaseTool` / `ToolRegistry`

`tool_registry` 只被 browser-use Agent（`engine/agent.py`）消费。`todo` 是 harness 层工具，注册了也无人调用。

## 风险 / 权衡

| 风险 | 概率 | 缓解 |
|------|------|------|
| ContextVar 在嵌套 context 中隔离：`goal_run` 内部若也读取同一 ContextVar，会读到外层 store（安全问题） | 低 | `goal_run` 不走 `_execute_single_tool_call` 的 `todo` 路由，不会误读；且路由只在 `fn_name == "todo"` 时读取 |
| `_EngineState._service` 循环引用：`_EngineState._service → Service._engine_state → _EngineState` | 无影响 | Python GC 可处理；但 `_EngineState` 职责从"Chrome + 事件"扩展到"Service 宿主"，注意后续拆分 |
| Service 单例在并发请求下的线程安全 | 低 | 当前请求模型是顺序的；后续若需并发，改用 session_id → TodoStore 的 dict |
| LLM 不理解 `merge=True` 语义 | 中 | tool description 中写明示例场景；可选在 system prompt 加一行引导 |

## 迁移计划

1. 前置修复：Service 单例化（改 `api/state.py`、`api/routes.py`）
   - 注意 `/api/chat/reset` 和 `/api/chat/cancel` 端点也需复用单例
2. 新建 `tools/todo_store.py` 和 `tools/todo.py`
   - TodoStore 内部处理 `todos` 类型校验（非 list 时忽略）、`merge` 类型校验（非 bool 时视为 False）
3. 注册 tool definition（改 `engine/_harness/tools.py`）
4. 集成 TodoStore 到 SessionState（改 `api/service.py`）
5. 注册路由（改 `engine/_harness/tool_executor.py`）
6. 在 `compile_session_to_preset` 中跳过 todo 调用（改 `api/service.py`，与 `edit_pipeline` 同级）
7. （可选）追加 `prompts/chat/system` 引导文本
8. 更新测试断言：`tests/test_harness_tools.py` 的 `assert len(tools) == 16` → 17，`assert len(tools) == 15` → 16
9. 验证：单元测试 + 手动 chat 测试

**回滚策略：** 所有改动互相独立，可逐文件回退，无数据迁移。

## 待确认问题

- prompts/chat/system 是否需加引导？目前保留可选，实施时按需决定。
