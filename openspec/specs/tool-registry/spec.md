## ADDED Requirements

### Requirement: ToolRegistry 注册与查询
`ToolRegistry` MUST 提供 `register(name, schema, handler)` 方法将工具注册到内部映射表，以及 `get_schemas()` 方法返回所有已注册工具的 OpenAI 兼容 schema 列表。

每个工具的 schema 以不含外层 `{"type": "function"}` 包装的格式存储，`get_schemas()` 返回时 MUST 自动添加 `{"type": "function", "function": schema}` 外层包装。

#### Scenario: 注册并获取 schema 列表
- **WHEN** 调用 `registry.register("browser_click", schema={...}, handler=click_handler)`
- **AND** 调用 `registry.get_schemas()`
- **THEN** 返回的列表中包含 `{"type": "function", "function": {"name": "browser_click", ...}}`

### Requirement: ToolRegistry 分发路由
`ToolRegistry.dispatch(name, args, ctx)` MUST 根据工具名找到对应的 handler 并调用 `await handler(args, ctx)`，返回 handler 的结果 dict。

#### Scenario: 分发到未注册工具
- **WHEN** 调用 `await registry.dispatch("unknown_tool", {}, ctx)`
- **THEN** 返回 `{"ok": False, "error": "Unknown tool: unknown_tool"}`

### Requirement: ToolRegistry.filter 筛选
`ToolRegistry.filter(allowed)` MUST 返回只包含 `allowed` 集合中工具名的 schema 列表。

### Requirement: build_registry 显式初始化
`registry.register()` MUST NOT 在模块 import 时自动执行。应用启动入口 MUST 显式调用 `build_registry()` 完成注册。

### Requirement: 工具注册方式
所有 browser_* 工具通过 `_BROWSER_OPS` 列表循环注册，每个工具的 schema 定义在 `_BROWSER_SCHEMAS` 字典中。特殊工具（`browser_source`, `browser_eval_js`, `format_convert`, `data_browse`, `data_keys`, `todo`, `pipeline_*`, `skill_*`, `file_*`, `eval_agent` 等）通过独立的 async handler 函数注册。

#### Scenario: browser_* 工具统一注册
- **WHEN** `build_registry()` 执行
- **THEN** `_BROWSER_OPS` 中每个 op_type 注册为 `browser_{op_type}` 工具
- **AND** handler 调用 `execute_browser_op(op, args, bridge)`

#### Scenario: 特殊工具独立注册
- **WHEN** `build_registry()` 执行
- **THEN** `browser_source` 注册为独立 handler（写入 shared_store）
- **AND** `browser_eval_js` 注册为独立 handler（从文件加载 JS）
- **AND** `format_convert` 注册为独立 handler（xlsx/csv/json 转换）

### Requirement: ToolContext 定义
`ToolContext` MUST 包含以下字段：
- `cdp_helpers: object | None` — 浏览器 CDP helpers 实例
- `tools_dir: Path | None` — 工具模块目录
- `pipeline_name: str` — 当前 pipeline 名
- `budget: IterationBudget | None` — 迭代预算
- `llm_call: Callable | None` — LLM 调用回调
- `interrupt_check: Callable[[], bool] | None` — 中断检查回调
- `stream_callback: Callable[[dict], None] | None` — 事件流回调
- `shared_store: dict | None` — 共享数据存储

### Requirement: get_all_tools 统一入口
`get_all_tools()` MUST 调用 `registry.get_schemas()` 获取工具列表，不再通过手动拼接模块级常量构建。函数签名 MUST NOT 包含 `include_goal_run` 参数。
