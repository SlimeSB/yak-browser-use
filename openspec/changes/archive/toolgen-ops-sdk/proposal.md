## Why

当前 `_PH-` 工具生成流程存在严重断裂：pipeline 遇到不存在的 `_PH-` 工具时直接终端失败（`TOOL_NOT_GENERATED`），需要用户手动介入生成代码后再重新运行。同时，LLM 生成的 Python 代码无任何约束——可以任意调用 Playwright/CDP 底层接口、导入危险模块、产生不可控的副作用。此外，`backend/tools/` 目录下的 `extract.py`、`data.py`、`adapters.py` 各自实现了 `_save_output`、`_resolve_input_files`、`_load_records` 等重复辅助函数，`ToolCDPHelpers` 与 `CDPHelpers` 之间的类型不匹配导致现有 `_PH-` 路径的浏览器工具实际不可用。

本次变更将 `_PH-` 从「手动介入的断裂流程」改造为「Ops SDK 约束 + Inline 自动生成 + 失败重试 + 自动注册」的一步到位方案，同时通过 `ToolContext` 统一抽象层消除重复代码和类型 bug。

## What Changes

- **新增** `ToolContext` 类（`backend/engine/ops.py`）：统一的浏览器/数据操作 SDK，封装 `PlaywrightBridge` 的浏览器 ops、文件 I/O 的数据 ops、CDP 逃逸口，以及域名白名单和熔断器安全机制
- **新增** inline 生成流程：`_PH-` 工具不存在时自动捕获页面状态 → 调 LLM 生成代码 → AST 安全检查 → 语法校验 → 写入磁盘 → 执行 → 重试（≤3 次），覆盖 preset 模式和 chat 模式
- **新增** schema 自动注册：rename 后自动解析函数签名构建 OpenAI function schema，加入动态注册表
- **新增** AST 安全检查：拒绝 `os`、`subprocess`、`sys`、`shutil`、`socket`、`ctypes`、`signal`、`multiprocessing`、`threading`、`importlib` 等危险模块的导入
- **新增** prompt 模板（`backend/prompts/tool_gen/generate.md`）：含 ToolContext API 文档、few-shot 示例、错误反馈格式
- **修改** `runner_preset.py`：`_execute_tool_step_with_guardian` 新增 `llm_call` 参数，`TOOL_NOT_GENERATED` 路径改为 inline 生成
- **修改** `tool_executor.py`：chat 模式 `else` 分支遇到 `_PH-` 工具时触发 inline 生成
- **修改** `extract.py`/`data.py`/`adapters.py`：迁移至 ToolContext，删除重复辅助函数
- **删除** `backend/tools/base.py`、`registry.py`、`schemas.py`：三个 1.0 时代遗留的废弃文件
- **标注 deprecated** `backend/utils/tool_cdp.py`：allowed_domains + circuit breaker 已迁移到 ToolContext

## Capabilities

### New Capabilities
- `tool-context-sdk`: 统一的浏览器/数据操作 API，封装 PlaywrightBridge 的浏览器 ops（wait/evaluate/click/fill/snapshot/screenshot/source）、文件 I/O 的数据 ops（save_json/load_json/save_csv/load_csv/save_bytes）、CDP 逃逸口，以及域名白名单和连续失败熔断器
- `ph-inline-generation`: _PH- 工具不存在时自动捕获页面状态、调 LLM 生成代码、AST 安全检查、语法校验、写入磁盘、执行、失败重试（≤3 次）的完整流程，覆盖 preset 模式和 chat 模式
- `tool-schema-registration`: 生成的工具 rename 后自动解析函数签名和 docstring，构建 OpenAI function schema，加入动态注册表，`get_all_tools()` 返回时合并静态工具和动态工具
- `tool-safety-check`: 对 LLM 生成的代码执行 AST 遍历，拒绝 `os`、`subprocess`、`sys`、`ctypes`、`signal`、`multiprocessing`、`threading`、`importlib` 等危险模块的导入

## Impact

- **代码影响**：新增 2 个文件（`ops.py`、`generate.md`），修改 8 个文件（`runner_preset.py`、`tool_runner.py`、`tools.py`、`tool_executor.py`、`extract.py`、`adapters.py`、`data.py`、`tool_cdp.py`），删除 3 个文件（`base.py`、`registry.py`、`schemas.py`）
- **接口影响**：`_execute_tool_step_with_guardian` 新增 `llm_call` 参数，`ToolRunner.load_and_call` 新增 ToolContext 路径，`get_all_tools()` 新增 `pipeline_name` 可选参数和动态注册表合并逻辑
- **依赖影响**：无新增外部依赖，ToolContext 依赖已有的 `PlaywrightBridge`
- **流程影响**：pipeline 执行 `_PH-` 步骤时不再终端失败，改为自动生成并执行；chat 模式同样支持
- **兼容性**：旧工具（extract/data/adapters）内部重构但外部行为不变；`ToolCDPHelpers` 保留兼容但标注 deprecated；`execute_tool` 的 `CAPABILITIES` 检查保留兼容
