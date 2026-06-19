## ADDED Requirements

### Requirement: ToolRegistry 注册与查询
`ToolRegistry` MUST 提供 `register(name, schema, handler)` 方法将工具注册到内部映射表，以及 `get_schemas()` 方法返回所有已注册工具的 OpenAI 兼容 schema 列表。

每个工具的 schema 以不含外层 `{"type": "function"}` 包装的格式存储，`get_schemas()` 返回时 MUST 自动添加 `{"type": "function", "function": schema}` 外层包装。

#### Scenario: 注册并获取 schema 列表
- **WHEN** 调用 `registry.register("browser_click", schema={"description": "...", "parameters": {...}}, handler=click_handler)`
- **AND** 调用 `registry.get_schemas()`
- **THEN** 返回的列表中包含 `{"type": "function", "function": {"name": "browser_click", "description": "...", "parameters": {...}}}`

### Requirement: ToolRegistry 分发路由
`ToolRegistry.dispatch(name, args, ctx)` MUST 根据工具名找到对应的 handler 并调用 `await handler(args, ctx)`，返回 handler 的结果 dict。

#### Scenario: 分发到已注册工具
- **WHEN** 调用 `await registry.dispatch("browser_click", {"selector": "#btn"}, ctx)`
- **AND** `browser_click` 已在 registry 中注册
- **THEN** 调用 `await click_handler({"selector": "#btn"}, ctx)`
- **AND** 返回 handler 的结果

#### Scenario: 分发到未注册工具
- **WHEN** 调用 `await registry.dispatch("unknown_tool", {}, ctx)`
- **AND** `unknown_tool` 未在 registry 中注册
- **THEN** 返回 `{"ok": False, "error": "Unknown tool: unknown_tool"}`

### Requirement: ToolRegistry.filter 筛选
`ToolRegistry.filter(allowed)` MUST 返回只包含 `allowed` 集合中工具名的 schema 列表，供 `eval_agent.get_restricted_tools()` 使用。

#### Scenario: 筛选子集
- **WHEN** 调用 `registry.filter({"browser_click", "browser_fill", "todo"})`
- **THEN** 返回的列表只包含 `browser_click`、`browser_fill`、`todo` 三个工具的 schema
- **AND** 列表中不包含其他已注册的工具

### Requirement: 工具定义迁移
现有的 `BROWSER_TOOLS`、`GOAL_RUN_TOOL`、`PIPELINE_TOOLS`、`TODO_TOOL`、`FILE_TOOLS`、`EVAL_AGENT_TOOL`、`SKILL_TOOLS`、`RECORD_STEP_TOOL` 等模块级常量 MUST 迁移为 `registry.register()` 调用，schema 和 handler 合并在同一处注册语句中。所有 40 个已知工具 MUST 在 registry 中有对应的 handler。用户自定义工具（不在已知 40 个之内）MUST 仍走 `execute_tool()` 动态 import fallback 路径。

#### Scenario: browser_click 迁移
- **WHEN** 审视迁移后的注册代码
- **THEN** `browser_click` 的 schema（description + parameters）和 handler（调用 `execute_browser_op("click", args, bridge)`）MUST 在同一处 `registry.register()` 中定义

#### Scenario: pipeline_load 迁移
- **WHEN** 调用 `registry.get_schemas()`
- **THEN** 返回的列表中包含 `pipeline_load` 工具定义
- **AND** 分发到 `pipeline_load` 时调用原有的 `pipeline_load(**args)` 函数

#### Scenario: record_step 迁移
- **WHEN** 分发 `record_step` 工具
- **THEN** handler 调用 `execute_tool(tool_name="record_step", params=args, tools_dir=ctx.tools_dir, cdp_helpers=ctx.cdp_helpers)`
- **AND** 不再作为未注册工具走 `else` fallback 路径

### Requirement: Handler 适配层
部分现有 handler 的签名和返回值与 registry 要求的 `async (args, ctx) -> dict` 不一致，MUST 提供适配 wrapper。

#### Scenario: skill_tools 同步→异步 wrapper
- **WHEN** 分发 `skill_list` 工具
- **THEN** wrapper 以 `async def` 包装同步的 `skill_list(**args)` 调用
- **AND** 返回 `dict` 结果

#### Scenario: pipeline_tools str→dict 转换
- **WHEN** 分发 `pipeline_load` 工具
- **THEN** wrapper 调用 `await pipeline_load(**args)` 获取 JSON 字符串
- **AND** wrapper 对返回值执行 `json.loads(result_str)` 转为 dict
- **AND** 如果缺少 `"result"` key，补全 `result_dict["result"] = json.dumps({...})`（与当前 `tool_executor.py:260-264` 行为一致）

### Requirement: pipeline_finish budget 处理
`pipeline_finish` handler MUST 通过 `ctx.budget.exhaust()` 消耗预算，wrapper 层 MUST 检查 `result_dict.get("_pipeline_finish")` 标记并终止循环。

#### Scenario: pipeline_finish 消耗预算
- **WHEN** 分发 `pipeline_finish` 工具且 `ctx.budget` 不为 None
- **THEN** handler 调用 `ctx.budget.exhaust()`
- **AND** 返回 `{"ok": True, "status": ..., "summary": ..., "_pipeline_finish": True}`
- **AND** wrapper 层检查 `_pipeline_finish` 标记后 break 循环

### Requirement: build_registry 显式初始化
`registry.register()` MUST NOT 在模块 import 时自动执行（不在 `__init__.py` 中注册）。应用启动入口（如 `build_registry()` 函数）MUST 显式调用注册逻辑。

#### Scenario: 避免 import 时副作用
- **WHEN** 其他模块 import `backend.tools.registry`
- **THEN** 不会自动触发工具注册
- **AND** 只在调用 `build_registry()` 后才完成注册

### Requirement: Handler 签名统一
所有注册到 `ToolRegistry` 的 handler MUST 遵循签名 `async (args: dict, ctx: ToolContext) -> dict`，不直接访问 `cdp_helpers`、`budget`、`llm_call` 等外部依赖——这些通过 `ctx` 传递。

#### Scenario: 浏览器工具 handler
- **WHEN** 分发 `browser_click` 工具
- **THEN** handler 从 `ctx.cdp_helpers` 获取 PlaywrightBridge
- **AND** handler 不直接 import `cdp_helpers` 模块

#### Scenario: eval_agent handler
- **WHEN** 分发 `eval_agent` 工具
- **THEN** handler 从 `ctx.llm_call`、`ctx.budget`、`ctx.interrupt_check`、`ctx.stream_callback`、`ctx.pipeline_name` 获取依赖
- **AND** handler 不通过闭包或全局变量获取这些依赖

### Requirement: ToolContext 定义
`ToolContext` MUST 是一个 dataclass，包含以下可选字段：
- `cdp_helpers: object | None` — 浏览器 CDP helpers 实例
- `tools_dir: Path | None` — 工具模块目录
- `pipeline_name: str` — 当前 pipeline 名
- `budget: IterationBudget | None` — 迭代预算
- `llm_call: Callable | None` — LLM 调用回调
- `interrupt_check: Callable[[], bool] | None` — 中断检查回调
- `stream_callback: Callable[[dict], None] | None` — 事件流回调

#### Scenario: 构建 ToolContext
- **WHEN** 创建 `ToolContext(cdp_helpers=helpers, budget=budget, stream_callback=cb)`
- **THEN** 所有指定字段可正常访问
- **AND** 未指定字段为默认值（`None` 或对应类型默认值）

### Requirement: preset 模式 execute_tool_step 迁移
`backend/engine/executor.py:755` 的 `execute_tool_step()` MUST 改为通过 `tools_registry.dispatch(tool_name, params, ctx)` 执行工具，不再通过 `execute_tool()` 动态 import。output validation（`_check_outputs`）逻辑 MUST 保留在 dispatch 调用之后。

#### Scenario: preset 工具执行
- **WHEN** preset 模式执行一个 tool step
- **THEN** `execute_tool_step()` 构建 `ToolContext` 后调用 `await registry.dispatch(tool_name, params, ctx)`
- **AND** 如果返回 `ok: true`，检查 output files 是否存在
- **AND** 如果返回 `ok: false`，标记 step 为 failed
