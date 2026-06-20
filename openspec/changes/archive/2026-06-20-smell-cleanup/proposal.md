## Why

项目目前寄生在 `browser-use` 这个庞大的第三方库上，实际只用到了其中的消息类型（`UserMessage`、`SystemMessage` 等）和 `ChatOpenAI` 封装。该库拉入了 20+ 个本项目用不到的依赖包，并自带 telemetry。同时，工具路由采用了大量的 if-elif 分派逻辑，分散在 `tool_executor.py` 的 `_execute_single_tool_call()` 函数中，schema 定义和 handler 分离在 `tools.py` 和 `tool_executor.py` 两个文件里，维护时需要在两处同步修改。`conversation_loop.py` 的 `run_conversation_loop()` 是一个 400 行的函数，状态靠闭包变量传递，难以理解边界。事件回调用 ad-hoc dict 散落在代码各处，type 字符串没有集中定义。

基于 ponytail 原则——不造未来需要的抽象、不重构不臭的模块、删除大于新增——本次变更清掉这些"面试官看到会皱眉"的异味。

## What Changes

1. **砍掉 `browser-use` 依赖**：vendor 6 个消息类型到 `backend/llm/messages.py`，新增 `LLMClient` 适配层替代 `ChatOpenAI`，vendor `OpenAIMessageSerializer.serialize_messages` 到 `backend/llm/serializer.py`，从 `pyproject.toml` 删除 `browser-use>=0.12.9`。
2. **新增 ToolRegistry 系统**：`backend/tools/registry.py` 提供统一的工具注册、schema 查询、分发路由，替代散装的 schema dict + if-elif 分派。
3. **工具分派映射表化**：`_execute_single_tool_call()` 的 if-elif 链路替换为 `registry.dispatch()`，横切逻辑（重试、重连、缓存、过滤器）保留在 wrapper 层。
4. **conversation_loop 抽取 Agent 类**：将 `run_conversation_loop()` 的闭包状态收拢为 `Agent` 类属性，`run_preset_loop()` 改为 `Agent` 的方法，对外接口保持兼容。
5. **stream_callback 事件结构化**：将散落在代码中的 ad-hoc 事件 dict 统一为 `Agent._emit()` 方法，事件类型集中定义。

## Capabilities

### New Capabilities
- `llm-messages`: vendor browser-use 的消息类型（UserMessage / SystemMessage / AssistantMessage / ToolCall），最小保留
- `llm-client`: LLMClient 适配层，封装 AsyncOpenAI 并提供与旧 ChatOpenAI 兼容的 .ainvoke() / .get_client() 接口（内含 `_serialize_messages`，替代 browser-use 的 OpenAIMessageSerializer）
- `tool-registry`: 统一工具注册表 ToolRegistry，替代散装 schema dict + if-elif 路由
- `agent-class`: 将 run_conversation_loop() 收拢为 Agent 类，状态变为属性
- `structured-events`: stream_callback 事件统一为 _emit() 方法，事件类型集中定义

### Modified Capabilities
- `tool-registration`: `get_all_tools()` 从手动拼接 schema 列表改为调用 `registry.get_schemas()`，工具定义从 `tools.py` 的模块级常量迁移至 `ToolRegistry.register()` 调用中，与 handler 合并。`eval_agent.get_restricted_tools()` 同步改为调用 `registry.filter(allowed)`。

## Impact

- **依赖**：从 `pyproject.toml` 删除 `browser-use>=0.12.9`，减少 20+ 传递依赖
- **新增文件**：`backend/llm/messages.py`、`backend/llm/client.py`、`backend/tools/registry.py`
- **修改文件**：`backend/utils/browser.py`、`backend/engine/agent.py`、`backend/engine/_harness/conversation_loop.py`、`backend/engine/_harness/tool_executor.py`、`backend/engine/_harness/tools.py`、`backend/engine/eval_agent.py`、`backend/api/routes.py`、`backend/compiler/generator.py`、`backend/converter/convert.py`
- **前端**：WebSocket 事件 shape 不变，无需改动
- **风险点**：Step 1（砍 browser-use）改动影响全项目 import chain，是最大风险点。`ChatOpenAI` 的 replace 影响 `agent.py` 的非流式/流式两条路径。验证 checkpoint 放在 Step 1 之后
- **不重构**：eval_agent（76 行，不臭）、step_machine（186 行，接口清晰）、ToolContext/ops.py（最好模块）、不做 EventBus / plugin hooks / 多 provider 抽象
