## 1. 砍 browser-use 依赖（最大风险，先做）

- [ ] 1.1 新增 `backend/llm/__init__.py`（空文件）、`backend/llm/messages.py`（`ToolCall`、`SystemMessage`、`UserMessage`、`AssistantMessage` 四个 dataclass）。`ToolCall.function` 为 `dict`（`field(default_factory=dict)`），无需 vendor `Function` 子类型——`agent.py:280-284` 的 `tc.function.name` 访问来自 OpenAI SDK 的 Pydantic 对象，不是 vendored `ToolCall`。vendored `ToolCall` 仅用于消息构造（`ToolCall(**tc_dict)`）和序列化（`serialize_messages` 访问 `tc.function["name"]`），`dict` 够用
- [ ] 1.2 新增 `backend/llm/client.py`（`LLMClient` 适配层 + `LLMResponse` dataclass + `_serialize_messages()` 函数）。`_serialize_messages()` 从 `OpenAIMessageSerializer.serialize_messages` port 过来（~30 行），作为 `client.py` 的模块级函数，不单独开文件。**关键要求：**
  - `LLMResponse` 必须有 `.model_name`（默认 `""`）、`.stop_reason`（默认 `""`）、`.usage`（dict | None），使 `response_logger.py:52-85` 不崩。**不要 `.completion` alias**——`generator.py:72` 和 `convert.py:109` 的 `hasattr(response, "completion")` 改为 `response.content or str(response)`，消费方适配
  - `LLMClient.ainvoke(messages, *, tools=None, **kwargs)` 签名兼容 `agent.py:178` 的 `llm.ainvoke(**kwargs)` 和 `generator.py:72` 的 `llm.ainvoke([msg])` 两种调用模式
  - **修复 ChatOpenAI 的 bug**：`tools` 必须显式传入 `client.chat.completions.create(tools=...)`——旧代码中 tools 进了 `**kwargs` 但未传给底层 API，非流式路径 LLM 永远看不到工具定义
  - 复制 `ChatOpenAI` 默认值：`temperature=0.2`、`frequency_penalty=0.3`、`max_completion_tokens=4096`、`max_retries=5`
  - 支持直接传 `api_key`/`base_url`/`model`（供 `routes.py:90` 用，不走 config）
  - `ainvoke` 内用 `serialize_messages()` 序列化消息后调 `AsyncOpenAI`
  - `get_client()` 暴露底层 client
  - 属性 passthrough（`.model`、`.temperature` 等）
  - reasoning 模型参数处理（`agent.py:218-223` 等价逻辑）
- [ ] 1.4 修改 `backend/utils/browser.py:39`：`create_llm()` 返回 `LLMClient(**kwargs)` 替代 `ChatOpenAI(**kwargs)`
- [ ] 1.5 修改 `backend/engine/agent.py:132-135`：将 `from browser_use.llm.messages import ...` 改为 `from llm.messages import ...`，`from browser_use.llm.openai.serializer import OpenAIMessageSerializer` 改为 `from llm.client import serialize_messages`，删 `from browser_use.llm.messages import ToolCall as BUMessageToolCall`（改为直接用 `ToolCall`）
- [ ] 1.6 修改 `backend/engine/agent.py:165`：`BUMessageToolCall(**tc)` 改为 `ToolCall(**tc)`
- [ ] 1.7 修改 `backend/engine/agent.py:184`：`OpenAIMessageSerializer.serialize_messages(converted)` 改为 `serialize_messages(converted)`
- [ ] 1.8 修改 `backend/engine/agent.py:339-340`（`create_pipeline_llm_call`）：同 1.5-1.6 的 import 和 `BUMessageToolCall` 替换
- [ ] 1.9 修改 `backend/api/routes.py:77-78`：`from browser_use.llm.openai.chat import ChatOpenAI` 改为 `from utils.browser import create_llm` 或 `from llm.client import LLMClient`；`from browser_use.llm.messages import UserMessage` 改为 `from llm.messages import UserMessage`
- [ ] 1.10 修改 `backend/compiler/generator.py:66`：`from browser_use.llm.messages import UserMessage` 改为 `from llm.messages import UserMessage`
- [ ] 1.11 修改 `backend/compiler/generator.py:72`：`response.completion if hasattr(response, "completion") else str(response)` 改为 `response.content or str(response)`（`.completion` alias 已移除，消费方适配）
- [ ] 1.12 修改 `backend/converter/convert.py:100,141`：两处 `from browser_use.llm.messages import UserMessage` 改为 `from llm.messages import UserMessage`
- [ ] 1.13 修改 `backend/converter/convert.py:109`：同 1.11 的 `.completion` → `.content` 替换
- [ ] 1.14 修改 `backend/pyproject.toml`：删除 `browser-use>=0.12.9` 依赖行
- [ ] 1.15 **验证 checkpoint**：`cd backend && uv lock && uv sync`，确认 `uv pip tree | grep browser-use` 无输出。`uv run python __main__.py serve --port 8765` 启动验证，`uv run pytest tests/ -x -q` 回归测试。不通过则停在此处修

## 2. Tool 注册系统 + 分派映射表化（强耦合，一起做）

- [ ] 2.1 **替换** `backend/tools/registry.py`（当前 30 行死代码：class-based registry，全项目 0 import）为新的 `ToolDef` dataclass、`ToolContext` dataclass、`ToolRegistry` 类（`register` / `get_schemas` / `dispatch` / `get_names` / `filter` 方法）。同步删除 `backend/tools/base.py`（18 行死代码 `BaseTool` ABC，全项目 0 import）
- [ ] 2.2 新增 `build_registry()` 函数（在 `registry.py` 或 `tools.py` 中）：逐工具调用 `registry.register(name, schema=..., handler=...)`，将 `backend/engine/_harness/tools.py` 的 `BROWSER_TOOLS`、`GOAL_RUN_TOOL`、`PIPELINE_TOOLS`、`RECORD_STEP_TOOL`、`TODO_TOOL`、`SKILL_*_TOOL`、`FILE_*_TOOL`、`FORMAT_CONVERT_TOOL`、`EVAL_AGENT_TOOL` 等全部迁移为注册语句
- [ ] 2.3 为每个 browser_* handler 编写 `async (args, ctx) -> dict` 函数：从 `ctx.cdp_helpers` 获取 bridge，调用 `execute_browser_op(op_type, args, bridge)`。~20 个 browser op
- [ ] 2.4 为 pipeline_* handler 编写包装函数：调 `pipeline_tools.py` 的 `pipeline_load` / `pipeline_list` / `pipeline_update_step` / `pipeline_add_step` / `pipeline_remove_step` / `pipeline_create` / `pipeline_compile`。**注意**：pipeline_tools 返回 JSON 字符串（`str`，非 `dict`），handler 必须做 `json.loads(result_str)` 解析，并补 `result` key（`pipeline_load`、`pipeline_list`、`pipeline_compile` 返回的 dict 不含外层 `result`，需补充 `result_dict["result"] = json.dumps({...})`）。此逻辑与当前 `tool_executor.py:251-265` 一致
- [ ] 2.5 为 `goal_run` handler：返回 `{"ok": True, "result": "目标已设定: ..."}`
- [ ] 2.6 为 `todo` handler：调 `tools.todo.todo(todos=..., merge=..., store=current_store.get())`
- [ ] 2.7 为 `file_read` / `file_write` / `format_convert` handler：直接包装 `tools.file_read.file_read` / `tools.file_write.file_write` / `tools.format_convert.format_convert`
- [ ] 2.8 为 `skill_*` handler：包装 `engine._harness.skill_tools` 中的 `skill_list` / `skill_view` / `skill_create` / `skill_edit` / `skill_delete`。**注意**：skill_tools.py 中的函数都是同步 `def`（非 `async def`），handler 需要包一层 `async def wrapper(args, ctx) -> dict: return handler(**args)`，或 registry 支持同步 handler
- [ ] 2.9 为 `record_step` handler：`record_step` 当前走 `else → execute_tool()` 动态 import 路径，是唯一不显式处理的工具。需要注册显式 handler，内部调用 `execute_tool(tool_name="record_step", params=fn_args, tools_dir=ctx.tools_dir, cdp_helpers=ctx.cdp_helpers)`
- [ ] 2.10 为 `eval_agent` handler：包装 `_handle_eval_agent` 函数，通过 `ctx.llm_call` / `ctx.budget` / `ctx.interrupt_check` / `ctx.stream_callback` / `ctx.pipeline_name` 获取依赖。**注意**：`_handle_eval_agent` 内部实例化 `Agent`——必须在 Step 3（Agent 类）完成后才能迁移此 handler，或先让 handler 保留原有的 `run_conversation_loop()` 函数调用，待 Step 3 完成后再改为实例化 `Agent`
- [ ] 2.11 为 `pipeline_finish` handler：返回 `{"ok": True, "status": ..., "summary": ..., "_pipeline_finish": True}`。**`budget.exhaust()` 的归属**：当前代码在 handler 内部调用 `budget.exhaust()`（`tool_executor.py:222-223`）。迁移后两个选项：① handler 通过 `ctx.budget.exhaust()` 调用（保持现状，简单）；② wrapper 检查 `_pipeline_finish` 标记后调用（更"纯粹"但多一层绕路）。选 ①，因为 `budget` 已经在 `ctx` 里，handler 调 `ctx.budget.exhaust()` 语义清晰
- [ ] 2.12 修改 `backend/engine/_harness/tool_executor.py:174-394`：`_execute_single_tool_call()` 的 if-elif 链替换为 `return await tools_registry.dispatch(fn_name, fn_args, ctx)`。保留重试/CDP 重连/`_is_unrecoverable`/`_apply_heavy_data_filter`/scratchpad 缓存/auto-refresh highlight 等 wrapper 逻辑。**为未注册工具保留 `else → execute_tool()` fallback**：`registry.dispatch()` 找不到 handler 时走 `execute_tool()` 动态 import 路径（保留向后兼容）
- [ ] 2.13 修改 `backend/engine/_harness/tool_executor.py:50-171`：`execute_tool_calls_sequential()` 中构建 `ToolContext` 并传给 `_execute_single_tool_call()`。保留 `pipeline_finish` 信号检查（`result_dict.get("_pipeline_finish")`）
- [ ] 2.14 修改 `backend/engine/_harness/tools.py:1050-1075`：`get_all_tools()` 改为调用 `registry.get_schemas()` 或 `registry.filter()`；`include_goal_run` 参数行为保持一致
- [ ] 2.15 修改 `backend/engine/eval_agent.py`：`get_restricted_tools()` 改为调用 `registry.filter(allowed)` 替代当前从 `BROWSER_TOOLS` 手动拼接
- [ ] 2.16 修改 `backend/engine/executor.py:755` 的 `execute_tool_step()`：preset 模式通过此函数执行工具，当前内部调用 `execute_tool()` 动态 import。迁移后改为 `tools_registry.dispatch(tool_name, params, ctx)`，保留 output validation 逻辑（`_check_outputs`）在调用后

## 3. conversation_loop 抽取 Agent 类

- [ ] 3.1 在 `backend/engine/_harness/conversation_loop.py` 中新增 `Agent` 类：`__init__` 接收 `llm_call`、`system_prompt`、`tools_registry` 等构造参数，初始化 `_messages`、`_budget`、`_guardrail_state`、`_state` 属性
- [ ] 3.2 新增 `AgentRunState` dataclass：`turn_count`、`interrupted`、`last_content_with_tools`、`final_response`、`consecutive_llm_failures` 等状态字段
- [ ] 3.3 实现 `Agent.run()`：入口方法。处理 guardrail config 注入（chat 模式默认宽松配置）、tool strategy guidance 注入（`load_prompt("guidance/tool_strategy")`）、进入 `_step()` 循环
- [ ] 3.4 实现 `Agent._step()`：单轮 LLM call + tool dispatch。将 `run_conversation_loop()` 第 114-235 行的 while 循环逻辑搬入，引用改为 `self._*`
- [ ] 3.5 实现 `Agent._emit(event_type, **data)`：条件调用 `self._on_event({...})`，事件 type 在前。将 `run_conversation_loop()` 中所有 `stream_callback({...})` 调用改为 `self._emit(...)`
- [ ] 3.6 修改 `run_conversation_loop()`（接口兼容层）：内部改为实例化 `Agent` 并调用 `agent.run()`，返回相同 `ConversationResult`
- [ ] 3.7 修改 `run_preset_loop()`：同 3.6，改为用 `Agent` 实例，设置 `preset_mode=True`
- [ ] 3.8 验证 `run_chat_loop()`（`backend/engine/runner.py:26-84`）和 `run_pipeline()`（`backend/engine/runner_preset.py`）行为不变

## 4. stream_callback 事件结构化

- [ ] 4.1 在 `Agent` 类中定义事件类型常量（`EVENT_TURN_START` / `EVENT_LLM_TURN` / `EVENT_TOOL_START` / `EVENT_TOOL_END` / `EVENT_ERROR`）
- [ ] 4.2 将 `conversation_loop.py` 中所有裸字符串 `"turn_start"` / `"llm_turn"` / `"chat.error"` 替换为事件常量引用
- [ ] 4.3 修改 `tool_executor.py:90-96`、`tool_executor.py:157-168`、`tool_executor.py:388-391`：`stream_callback({"type": "chat.tool_start", ...})` 改为通过 `ToolContext.stream_callback` 调用或 `_emit` 等效方式。注意 line 388-391 的 CDP 重连失败错误事件也需替换
- [ ] 4.4 确认前端 WebSocket 收到的所有 `type` 值不变（如 `"chat.tool_start"` 仍为 `"chat.tool_start"`），`ChatTab` 无需改动

## 5. 全面验证

- [ ] 5.1 `cd backend && uv lock && uv sync`：确认 `browser-use` 不在依赖树
- [ ] 5.2 `cd backend && uv run python -c "from tools.registry import registry; assert len(registry.get_schemas()) > 20"`：确认工具注册数量
- [ ] 5.3 `cd backend && uv run pytest tests/ -x -q`：回归测试全部通过
- [ ] 5.4 `uv run python __main__.py serve --port 8765` + `curl http://127.0.0.1:8765/api/status`：serve 可用
- [ ] 5.5 Electron 启动验证：`cd electron && npm start`，chat 发送消息确认端到端可用
