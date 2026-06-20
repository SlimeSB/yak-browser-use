## 背景

项目依赖 `browser-use>=0.12.9` 的实际用途仅限于 6 个符号：`UserMessage`、`SystemMessage`、`AssistantMessage`、`ToolCall`（来自 `browser_use.llm.messages`）、`ChatOpenAI`（来自 `browser_use.llm.openai.chat`）、`OpenAIMessageSerializer`（来自 `browser_use.llm.openai.serializer`）。该库拉入 20+ 传递依赖并自带 telemetry，是项目中最大的"寄生依赖"。

工具路由方面，`backend/engine/_harness/tool_executor.py` 的 `_execute_single_tool_call()` 使用 if-elif 链表分发约 15 种工具，而工具 schema 定义在 `backend/engine/_harness/tools.py` 的模块级常量中，handler 逻辑却分布在 `tool_executor.py` 各处——修改一个工具需要在两处同步。

`backend/engine/_harness/conversation_loop.py` 的 `run_conversation_loop()` 是 400 行的函数，拥有 12 个参数，内部状态（`turn_count`、`final_response`、`consecutive_llm_failures`、`interrupted`、`last_content_with_tools`）靠函数局部变量传递。stream_callback 事件 dict 中的 type 字符串（`"chat.tool_start"`、`"chat.tool_end"`、`"chat.error"`、`"turn_start"`、`"llm_turn"`）散落在 `conversation_loop.py` 和 `tool_executor.py` 两处，没有集中定义。

约束：前端 WebSocket 事件 shape 不能变；`start_chat_agent()` 和 `run_preset_loop()` 对外接口保持兼容；测试覆盖有限（当前无覆盖 `run_conversation_loop` 和 `_execute_single_tool_call` 的测试），必须谨慎。

## 目标 / 非目标

**目标：**
- 从 `pyproject.toml` 移除 `browser-use` 依赖，vendor 实际使用的 6 个符号
- 用 `ToolRegistry` 统一工具注册、schema 查询、分发路由，消除 if-elif 链
- 将 `run_conversation_loop()` 抽取为 `Agent` 类，状态从闭包变为属性
- 将 stream_callback 事件统一为 `_emit()` 方法，type 字符串集中定义

**非目标：**
- 不做 EventBus / plugin hooks（无多监听者场景）
- 不重构 eval_agent（76 行，职责单一）
- 不重构 step_machine / ToolContext / ops.py（不臭）
- 不做多 provider LLM 抽象（只有一个 provider）
- 不做 Message compaction（对话长度未到阈值）

## 关键决策

### 1. LLMClient 适配层而非裸调 AsyncOpenAI

直接替换 `ChatOpenAI` 为 `AsyncOpenAI` 会影响 5 处调用方。`ChatOpenAI` 暴露的 API 包括：
- `.ainvoke(messages, tools)` → 返回有 `.content`、`.tool_calls` 属性的响应对象
- `.get_client()` → 返回 OpenAI 客户端（流式路径用）
- `.model`、`.temperature`、`.max_completion_tokens`、`.frequency_penalty`、`.top_p`、`.seed`、`.reasoning_models`、`.reasoning_effort` 属性

`AsyncOpenAI` 的接口不同：`client.chat.completions.create()` 返回 `ChatCompletion`，通过 `response.choices[0].message.content` 访问内容。因此新增 `LLMClient` 作为适配层，封装 `AsyncOpenAI` 并暴露与 `ChatOpenAI` 兼容的接口。`agent.py` 的 `_create_chat_llm_call()` 非流式分支（`agent.py:178`）和流式分支（`agent.py:204`）的调用方式无需改动。

流式分支（`agent.py:238`）当前已经在调 `client.chat.completions.create(stream=True)`，`LLMClient.get_client()` 返回 `AsyncOpenAI` 后该路径不变。

`LLMResponse` 是新引入的响应 dataclass，替代 browser-use 的响应对象。必须暴露以下属性以兼容现有消费方：

| 属性 | 说明 | 消费方 |
|------|------|--------|
| `.content` | 文本回复 | `conversation_loop.py:157,184,208` |
| `.tool_calls` | 工具调用列表 | `conversation_loop.py:174`、`agent.py` |
| `.reasoning` | 推理内容（非流式） | `conversation_loop.py:156`：`getattr(response, 'reasoning', None) or getattr(response, 'thinking', None)` |

`conversation_loop.py:156` 用 `getattr` 兼容 `reasoning` / `thinking` 两种字段名——流式路径响应用 `SimpleNamespace(.thinking)`，`LLMResponse` 用 `.reasoning`，共存无需统一。

`LLMClient.__init__` 必须复制 `ChatOpenAI` 的默认值，否则 LLM 行为会改变：

| 参数 | ChatOpenAI 默认值 | 说明 |
|------|-------------------|------|
| `temperature` | `0.2` | |
| `frequency_penalty` | `0.3` | "avoids infinite generation of \\t for models like 4.1-mini" |
| `max_completion_tokens` | `4096` | |
| `max_retries` | `5` | 内部重试次数（LLMClient 可不实现，moved to `_call_llm_with_retry`） |

`LLMClient` 必须支持两种构造方式：
1. 通过 `create_llm()` 读取配置文件（`userdata/provider.json` 或环境变量）
2. 直接传参构造（`LLMClient(model=..., api_key=..., base_url=...)`），供 `routes.py:90` 的 provider test 使用——该路径不走 config 文件

**注意：ChatOpenAI.ainvoke() 在非流式路径静默丢弃 tools 参数。** `ChatOpenAI.ainvoke(messages, output_format=None, **kwargs)` 接收 `tools` 在 `**kwargs` 中，但内部调用 `client.chat.completions.create()` 时未展开 `**kwargs`，导致 tools 从未传给 OpenAI API。`LLMClient.ainvoke()` 补救：将 `tools` 作为显式参数接收并传入 `self._build_kwargs()`。

**`_build_assistant_message` 的 fallback：** 当前 `ChatInvokeCompletion` 没有 `.content` 属性（只有 `.completion`），`_build_assistant_message`（`conversation_loop.py:300`）的 `getattr(response, "content", "")` 返回空串，`conversation_loop.py:208-210` 的二次 fallback `getattr(response, "completion", "")` 才拿到实际文本。vendor 后 `LLMResponse` 有 `.content`，第一层直接命中，逻辑更干净。`generator.py:72` 和 `convert.py:109` 的 `response.completion if hasattr(response, "completion") else str(response)` 改为 `response.content or str(response)`——消费方知道自己要什么字段，没必要在 `LLMResponse` 上加 alias。

**`ToolCall.function` 字段澄清：** `agent.py:280-284` 的 `tc.function.name` 访问的对象来自 OpenAI 流式响应的 `delta.tool_calls`（OpenAI SDK Pydantic 对象），不是 vendored `ToolCall`。vendored `ToolCall` 只用于消息构造（`agent.py:165`）和序列化，`function: dict` 完全够用——`ToolCall(**{"function": {"name": "x", ...}})` 构造时 function 由 dict 传入。无需 vendor `Function` 子类型。

**`response_logger.py` 的兼容：** `_log_non_streaming_response`（`response_logger.py:52`）用 `getattr(response, "completion", "")` 访问 `.completion`。`LLMResponse` 没有 `.completion`，`getattr` 返回 `""` 默认值，日志降级（只记录 `model_name`、`stop_reason`、`usage` 等剩余字段）。不崩。后续 PR 可清理这个 getattr。

### 2. 消息序列化的归属 — 合并到 client.py，不单独成文件

`agent.py:156-172` 将对话 dict 转换为 vendored 消息对象（`SystemMessage(...)`、`UserMessage(content=...)`、`AssistantMessage(...)`），然后：
- 非流式路径通过 `llm.ainvoke(messages=converted)` 内部序列化
- 流式路径通过 `serialize_messages(converted)` 显式序列化

Vendor 后：
- `backend/llm/messages.py` 提供与 browser-use 相同 shape 的 dataclass
- `serialize_messages()` 函数作为 `client.py` 的私有方法（`_serialize_messages`）
- `LLMClient.ainvoke()` 内部调用 `_serialize_messages()` 序列化后再传给 `AsyncOpenAI`
- 流式路径从 `client` import `_serialize_messages`（Python 不强制私有，`_` 只是约定）

不单独开 `serializer.py`——30 行的函数不配一个文件。ponytail: 省一个文件。

### 3. ToolRegistry 设计：显式注册链，不用装饰器

**注意：** 现有 `backend/tools/registry.py`（30行）和 `backend/tools/base.py`（18行）是全项目 0 import 的死代码。前者是 class-based registry（注册 `BaseTool` 子类），与本次要建的函数式 registry（注册 `(name, schema, handler)` 三元组）设计不同。本次直接**替换**这两个文件，不保留旧代码。

`ToolRegistry` 是一个朴素的 dict 映射表：`name → ToolDef(schema, handler)`。

```python
@dataclass
class ToolDef:
    name: str
    schema: dict        # function schema（不含外层 {type, function} 包装）
    handler: Callable   # async (args: dict, ctx: ToolContext) -> dict

@dataclass
class ToolContext:
    cdp_helpers: object | None = None
    tools_dir: Path | None = None
    pipeline_name: str = ""
    budget: IterationBudget | None = None
    llm_call: Callable | None = None
    interrupt_check: Callable[[], bool] | None = None
    stream_callback: Callable[[dict], None] | None = None
```

**选择 `ToolContext` 打包依赖而非让 handler 自己 import：**当前 `_execute_single_tool_call()` 的 if-elif 链中不同分支需要不同的依赖（`browser_*` 需要 `cdp_helpers.bridge`，`eval_agent` 需要 `llm_call` + `budget` + `interrupt_check` + `stream_callback` + `pipeline_name`，`pipeline_finish` 需要 `budget`）。打包进 `ToolContext` 使所有 handler 签名统一为 `async (args, ctx) -> dict`。

**不用装饰器注册：**太魔法，且迫使 handler 必须定义在注册处能访问的模块里。当前很多 handler 是 `tool_executor.py` 里的闭包或 `pipeline_tools.py` 的函数。

**不在 `__init__.py` 自动注册：**import 时执行的副作用会带来测试隔离和循环导入风险。改为应用启动入口显式调用 `build_registry()`。测试中可用 `unittest.mock.patch` 隔离。

### 4. 横切关注点保留在 wrapper 层

`_execute_single_tool_call()` 当前的 if-elif 链中混入了横切逻辑：CDP 断连重试（3 次 exponential backoff + budget pause/resume）、Timeout 重试（1 次）、`_is_unrecoverable()` 检查、`_apply_heavy_data_filter()`、browser op 后 auto-refresh highlight。这些不属于工具逻辑本身，保留在 wrapper 层（改造后的 `_execute_single_tool_call()` 或 `execute_tool_calls_sequential()`），handler 保持纯（`args → result`）。

**Scratchpad 缓存**（`_try_scratchpad_element_lookup()` 和 `_try_scratchpad_source_read()`）依赖全局 scratchpad 状态，不属于 handler 自身可承载的逻辑，保留在 wrapper 层。

**`pipeline_finish` 信号**通过 `{"_pipeline_finish": True}` 边车属性在 handler 返回 dict 中传递，`execute_tool_calls_sequential()` 在 dispatch 后检查该标记——不改变信号机制，只是从 if-elif 中的代码提取为统一的检查点。`budget.exhaust()` 保留在 handler 内部通过 `ctx.budget.exhaust()` 调用（当前代码就在 handler 里，移到 wrapper 多一层绕路且无收益）。

**未注册工具 fallback：** `registry.dispatch()` 找不到 handler 时走 `else → execute_tool()` 动态 import 路径，保留向后兼容。`record_step` 作为已知工具注册显式 handler，但未知工具仍走 fallback。

**`record_step` 工具的 handler：** 当前 `record_step` 走 `else → execute_tool()` 动态 import 路径，是唯一未显式处理的工具。迁移后注册显式 handler：`async (args, ctx) → execute_tool(tool_name="record_step", ...)`。

**skill 工具的同步/异步：** `skill_tools.py` 的函数都是同步 `def`（非 `async def`），`tool_executor.py:338` 直接 `return handler(**fn_args)`。Registry handler 期望 `async (args, ctx) → dict`，需包一层 `async def wrapper(args, ctx): return handler(**args)` 适配。

**pipeline 工具的返回值类型：** `pipeline_tools.py` 返回 JSON 字符串（`str`），`tool_executor.py:251-253` 在 dispatch 后手动 `json.loads(result_str)`。Registry handler 需做同样的 JSON 解析和 `result` key 补全。

**preset 模式的 `execute_tool_step()` 也需要迁移：** `backend/engine/executor.py:755` 的 `execute_tool_step()` 内部调用 `execute_tool()` 动态 import 工具模块——该函数不走 `_execute_single_tool_call()`。迁移后改为 `tools_registry.dispatch(tool_name, params, ctx)`，保留 output validation（`_check_outputs`）在调用后。

### 5. Agent 类的边界

`Agent` 类只收敛 `run_conversation_loop()` 的职责：

```python
class Agent:
    def __init__(self, *, llm_call, system_prompt, tools_registry, ...):
        self._llm_call = llm_call
        self._system_prompt = system_prompt
        self._tools = tools_registry
        self._messages: list[dict] = []
        self._budget = IterationBudget(max_total=50)
        self._guardrail_state = ToolCallGuardrailState()
        self._state = AgentRunState()  # turn_count, interrupted, last_content_with_tools

    async def run(self) -> ConversationResult: ...
    async def _step(self) -> bool: ...
    async def _execute_tool(self, fn_name, fn_args) -> dict: ...
    def _emit(self, event_type: str, **data): ...
```

`rules` 不在 `__init__` 里初始化（当前在 `run_conversation_loop()` 中由 `guardrail_config` 注入并赋值给 `guardrail_state.config`），作为 `run()` 的参数或在 `run()` 入口处理。

### 6. 事件系统最小化

不建 EventBus 或类型化 Event 类，只做两件事：
1. 所有 emit 调用统一通过 `self._emit(event_type, **data)`
2. 事件 type 字符串集中在事件类型表中定义，消除散落的字符串

前端 WebSocket 事件 shape 不变（`{"type": "...", "tool_name": ..., "ok": ...}`）。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| Step 1 改动影响全项目 import chain | 启动即报错 `ImportError` | Step 1 后设验证 checkpoint：`uv lock && uv sync` + `pytest` + serve 启动，不通过即停 |
| `LLMClient.ainvoke()` 返回值与旧 `ChatOpenAI.ainvoke()` 不完全对齐 | `response_logger` 的 usage 日志丢失数据（`LLMResponse.usage` 是 dict，logger 当 object 读） | 不崩，仅日志降级。`getattr(dict, "prompt_tokens")` 返回 `None` |
| ToolRegistry 全局实例在测试间共享 | 测试隔离困难 | `build_registry()` 显式初始化，测试用 `patch.object` 隔离 |
| ToolRegistry import-time 副作用 | 循环导入风险 | 不在 `__init__.py` 注册，只在 app 入口触发 |
| Agent 类重构改变闭包状态执行顺序 | 运行时行为差异 | 保持变量名和赋值顺序与旧代码一致，逐段迁移 |

## 迁移计划

1. **Step 1 first**：砍 browser-use 是最大风险点，必须先做。通过 checkpoint 验证后再继续。
2. **Step 2-3 一起**：ToolRegistry + if-elif 替换强耦合，一起做。
3. **Step 4 独立**：Agent 类抽取可独立进行，改完立刻回归测试。
4. **Step 5 最后**：事件结构化纯整理，不改行为。
5. **回滚**：每个 step 在独立分支，不合并即可回滚。`browser-use` 依赖可以随时加回 `pyproject.toml`。

## 待确认问题

- `backend/llm/serializer.py` 的 `serialize_messages()` 实现需要阅读 `browser_use.llm.openai.serializer` 源码后确定。计划预留 ~30 行。
- `response_logger.py` 的 usage 兼容修复是否放入本 PR：影响小（只影响日志），可以让后续 PR 单独处理。
